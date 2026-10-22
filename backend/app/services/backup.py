"""Full and incremental backups to remote locations, and restore from them.

A backup is one encrypted file per run and target:

    lpr_20261022T020000Z_full.lprbak
    lpr_20261023T020000Z_incr_20261022T020000Z.lprbak   (parent in the name)

The file is a gzipped tar with manifest.json, secrets.json (the secret key that
encrypts passwords and tokens in the database) and one JSON file per table,
encrypted with AES-256-GCM using a key derived from the backup passphrase
(scrypt). A full backup holds every row; an incremental backup holds the rows
added or changed since the previous backup on that target and the keys of the
rows deleted since then. Restoring replays the chain from its full backup.

What changed is tracked per target in the state directory (row hashes of the
last backup), so every target has its own complete chain. A new full backup is
made automatically when that state is missing, the parent is gone from the
target, the database schema changed or the passphrase changed.
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import secrets as pysecrets
import socket
import tarfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import Connection, DateTime, MetaData, Table, select, text
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_engine
from ..models import BackupTarget, utcnow
from ..security import ENCRYPTED_COLUMNS, decrypt, encrypt
from ..settings_store import SECRET_FIELDS, get_section
from . import remote as remote_mod
from .jobs import JobContext
from .mailer import send_mail

log = logging.getLogger(__name__)

FORMAT = 1
MAGIC = b"LPRBAK1\n"
SUFFIX = ".lprbak"
# Never part of a backup: sign-in sessions, the job history (a restore runs as a job)
# and the schema version (stored in the manifest instead).
SKIPPED_TABLES = {"user_sessions", "jobs", "alembic_version"}
NAME_RE = re.compile(r"^lpr_(\d{8}T\d{6}Z)_(full|incr)(?:_(\d{8}T\d{6}Z))?\.lprbak$")
STAMP = "%Y%m%dT%H%M%SZ"
KINDS = ("full", "incremental")
MIN_PASSPHRASE = 12

_lock = threading.Lock()


class BackupError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------- names


@dataclass
class BackupName:
    name: str
    kind: str  # full | incr
    stamp: str
    parent: str | None

    @property
    def created_at(self) -> datetime:
        return datetime.strptime(self.stamp, STAMP).replace(tzinfo=timezone.utc)


def parse_name(name: str) -> BackupName | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    stamp, kind, parent_stamp = m.groups()
    if kind == "incr" and not parent_stamp:
        return None
    parent = None
    if parent_stamp:
        # The parent of an incremental backup is the full or incremental one with that stamp.
        parent = parent_stamp
    return BackupName(name, kind, stamp, parent)


def _new_stamp(after: str | None = None) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if after:
        floor = datetime.strptime(after, STAMP).replace(tzinfo=timezone.utc) + timedelta(seconds=1)
        now = max(now, floor)
    return now.strftime(STAMP)


def make_name(kind: str, parent: BackupName | None = None, existing: list[str] | None = None) -> str:
    """A new backup name, later than its parent and every backup already on the target
    (stamps identify backups, so two runs in the same second must not collide)."""
    stamps = [p.stamp for p in _index(existing or []).values()] + ([parent.stamp] if parent else [])
    stamp = _new_stamp(max(stamps) if stamps else None)
    if kind == "full":
        return f"lpr_{stamp}_full{SUFFIX}"
    assert parent is not None
    return f"lpr_{stamp}_incr_{parent.stamp}{SUFFIX}"


def _index(names: list[str]) -> dict[str, BackupName]:
    """Backups on a target by stamp (stamps are unique per target)."""
    return {p.stamp: p for p in (parse_name(n) for n in names) if p}


def chain_of(name: str, names: list[str]) -> list[BackupName] | None:
    """The backups needed to restore `name`, full backup first; None when one is missing."""
    by_stamp = _index(names)
    current = parse_name(name)
    if current is None or current.stamp not in by_stamp:
        return None
    chain = [current]
    while current.kind == "incr":
        current = by_stamp.get(current.parent or "")
        if current is None or len(chain) > 10000:
            return None
        chain.append(current)
    return list(reversed(chain))


def catalog(files: list[remote_mod.RemoteFile]) -> list[dict[str, Any]]:
    names = [f.name for f in files]
    sizes = {f.name: f.size for f in files}
    by_stamp = _index(names)
    items = []
    for p in sorted(by_stamp.values(), key=lambda p: p.stamp, reverse=True):
        chain = chain_of(p.name, names)
        items.append(
            {
                "name": p.name,
                "kind": "full" if p.kind == "full" else "incremental",
                "created_at": p.created_at.isoformat(),
                "parent": by_stamp[p.parent].name if p.parent in by_stamp else None,
                "size": sizes.get(p.name),
                "restorable": chain is not None,
                "chain_length": len(chain) if chain else 0,
            }
        )
    return items


def plan_prune(names: list[str], keep_full: int) -> list[str]:
    """Backups to delete so that the newest `keep_full` full backups and their incremental
    backups remain. Incomplete chains older than the oldest kept full backup go too."""
    by_stamp = _index(names)
    fulls = sorted((p for p in by_stamp.values() if p.kind == "full"), key=lambda p: p.stamp, reverse=True)
    keep = {p.stamp for p in fulls[: max(1, keep_full)]}
    if not keep:
        return []
    oldest_kept = min(keep)

    def root(p: BackupName) -> str | None:
        seen = 0
        while p.kind == "incr":
            parent = by_stamp.get(p.parent or "")
            if parent is None or seen > 10000:
                return None
            p, seen = parent, seen + 1
        return p.stamp

    delete = []
    for p in by_stamp.values():
        r = root(p)
        if r in keep or (r is None and p.stamp >= oldest_kept):
            continue
        delete.append(p.name)
    return sorted(delete)


# ---------------------------------------------------------------- encryption


def _derive(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def encrypt_blob(data: bytes, passphrase: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_derive(passphrase, salt)).encrypt(nonce, data, MAGIC)


def decrypt_blob(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        raise BackupError("not_a_backup", "This file is not a backup of this application")
    body = blob[len(MAGIC) :]
    salt, nonce, ciphertext = body[:16], body[16:28], body[28:]
    try:
        return AESGCM(_derive(passphrase, salt)).decrypt(nonce, ciphertext, MAGIC)
    except InvalidTag as exc:
        raise BackupError("wrong_passphrase", "Wrong passphrase, or the backup file is damaged") from exc


def _passphrase_id(passphrase: str) -> str:
    """Recognises a passphrase change without storing the passphrase itself."""
    salt = get_settings().secret_key.encode()
    return hashlib.sha256(salt + b"\0" + passphrase.encode()).hexdigest()[:24]


# ---------------------------------------------------------------- database snapshot


def _reflect(conn: Connection) -> list[Table]:
    meta = MetaData()
    meta.reflect(bind=conn)
    return [t for t in meta.sorted_tables if t.name not in SKIPPED_TABLES]


def _pk_columns(table: Table) -> list[str]:
    cols = [c.name for c in table.primary_key.columns]
    return cols or [c.name for c in table.columns]


def _pk(row: dict[str, Any], cols: list[str]) -> str:
    return "|".join(str(row.get(c)) for c in cols)


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:  # SQLite drops the timezone; the app stores UTC
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:24]


def current_revision(conn: Connection) -> str | None:
    from alembic.runtime.migration import MigrationContext

    return MigrationContext.configure(conn).get_current_revision()


@dataclass
class Snapshot:
    revision: str | None
    tables: dict[str, dict[str, Any]]  # name -> {"pk": [...], "rows": {pk: row}}


def take_snapshot(db: Session) -> Snapshot:
    conn = db.connection()
    tables: dict[str, dict[str, Any]] = {}
    for table in _reflect(conn):
        cols = _pk_columns(table)
        rows = {}
        for r in conn.execute(select(table).order_by(*[table.c[c] for c in cols])).mappings():
            row = {k: _encode(v) for k, v in r.items()}
            rows[_pk(row, cols)] = row
        tables[table.name] = {"pk": cols, "rows": rows}
    revision = current_revision(conn)
    db.commit()
    return Snapshot(revision, tables)


# ---------------------------------------------------------------- archives


def build_archive(manifest: dict[str, Any], tables: dict[str, Any], secrets: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:

        def add(name: str, payload: Any) -> None:
            data = json.dumps(payload, separators=(",", ":"), default=str).encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(datetime.now(timezone.utc).timestamp())
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))

        add("manifest.json", manifest)
        add("secrets.json", secrets)
        for name, payload in tables.items():
            add(f"tables/{name}.json", payload)
    return buf.getvalue()


def read_archive(data: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            files = {}
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                extracted = tar.extractfile(member)
                if extracted is not None:
                    files[member.name] = json.loads(extracted.read())
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise BackupError("damaged", f"The backup file is damaged: {exc}") from exc
    manifest = files.get("manifest.json")
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BackupError("unsupported_format", "Unsupported backup format")
    tables = {k[len("tables/") : -len(".json")]: v for k, v in files.items() if k.startswith("tables/")}
    return manifest, tables, files.get("secrets.json") or {}


# ---------------------------------------------------------------- local state


def _state_dir() -> Path:
    path = get_settings().state_dir / "backup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(target_id: int) -> Path:
    return _state_dir() / f"target-{target_id}.json"


def load_state(target_id: int) -> dict[str, Any] | None:
    try:
        return json.loads(_state_path(target_id).read_text())
    except (OSError, ValueError):
        return None


def _save_state(target_id: int, state: dict[str, Any]) -> None:
    path = _state_path(target_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.chmod(0o600)
    tmp.replace(path)


def clear_states() -> None:
    for path in _state_dir().glob("target-*.json"):
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------- targets


def ssh_key(db: Session) -> tuple[str, str]:
    """The application's SSH key pair for SCP targets (private PEM, public line).
    Created on first use."""
    from ..settings_store import update_section

    private = get_section(db, "backup").get("ssh_private_key") or ""
    if not private:
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()
        ).decode()
        update_section(db, "backup", {"ssh_private_key": private})
    key = serialization.load_ssh_private_key(private.encode(), password=None)
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return private, f"{public} lpr-importer@{socket.gethostname()}"


def target_config(db: Session, target: BackupTarget, **overrides: Any) -> remote_mod.TargetConfig:
    cfg = remote_mod.TargetConfig(
        protocol=target.protocol,
        host=target.host,
        port=target.port,
        username=target.username,
        password=decrypt(target.password) or "" if target.password else "",
        auth_method=target.auth_method,
        host_key=target.host_key,
        remote_path=target.remote_path,
        ftps_implicit=target.ftps_implicit,
        verify_tls=target.verify_tls,
        passive=target.passive,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    if cfg.protocol == "scp" and cfg.auth_method == "key":
        cfg.private_key = ssh_key(db)[0]
    return cfg


def connect(db: Session, target: BackupTarget) -> remote_mod.Remote:
    remote = remote_mod.connect(target_config(db, target))
    if target.protocol == "scp" and not target.host_key and remote.host_key:
        target.host_key = remote.host_key  # trust on first use, then pinned
        db.commit()
    return remote


# ---------------------------------------------------------------- backup


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(size)


def _payload(snapshot: Snapshot, previous: dict[str, dict[str, str]] | None) -> tuple[dict[str, Any], dict[str, dict[str, str]], int]:
    """Table payloads for a full (previous None) or incremental backup, the new row hashes
    and the number of rows stored."""
    payload: dict[str, Any] = {}
    hashes: dict[str, dict[str, str]] = {}
    stored = 0
    for name, table in snapshot.tables.items():
        rows = table["rows"]
        table_hashes = {pk: _row_hash(row) for pk, row in rows.items()}
        hashes[name] = table_hashes
        if previous is None:
            changed, deleted = list(rows.values()), []
        else:
            before = previous.get(name, {})
            changed = [rows[pk] for pk, h in table_hashes.items() if before.get(pk) != h]
            deleted = [pk for pk in before if pk not in rows]
        payload[name] = {"pk": table["pk"], "rows": changed, "deleted": deleted}
        stored += len(changed) + len(deleted)
    return payload, hashes, stored


def _backup_target(db: Session, ctx: JobContext, target: BackupTarget, kind: str, snapshot: Snapshot, passphrase: str, keep_full: int) -> str:
    remote = connect(db, target)
    try:
        names = [f.name for f in remote.list()]
        state = load_state(target.id)
        parent = None
        if kind == "incremental":
            last = state and parse_name(state.get("last", ""))
            usable = (
                last
                and state.get("revision") == snapshot.revision
                and state.get("passphrase") == _passphrase_id(passphrase)
                and chain_of(last.name, names) is not None
            )
            if usable:
                parent = last
            else:
                ctx.note(f"{target.name}: no usable previous backup on this target, making a full backup instead")
        name = make_name("incr" if parent else "full", parent, names)
        payload, hashes, stored = _payload(snapshot, state["hashes"] if parent and state else None)
        from .updater import local_info

        manifest = {
            "format": FORMAT,
            "name": name,
            "kind": "incremental" if parent else "full",
            "parent": parent.name if parent else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "revision": snapshot.revision,
            "app_version": local_info().get("version"),
            "hostname": socket.gethostname(),
            "rows": stored,
        }
        blob = encrypt_blob(build_archive(manifest, payload, {"secret_key": get_settings().secret_key}), passphrase)
        remote.upload(name, blob)
        _save_state(
            target.id,
            {"last": name, "revision": snapshot.revision, "passphrase": _passphrase_id(passphrase), "hashes": hashes},
        )
        ctx.step(True, f"{target.name}: {name} ({manifest['kind']}, {stored} rows, {_human(len(blob))})", target=target.name)
        for old in plan_prune([*names, name], keep_full):
            try:
                remote.delete(old)
                ctx.note(f"{target.name}: removed old backup {old}")
            except remote_mod.RemoteError as exc:
                ctx.note(f"{target.name}: could not remove {old}: {exc}", ok=False)
        return name
    finally:
        remote.close()


def run_backup(ctx: JobContext, kind: str, target_ids: list[int] | None = None) -> dict[str, Any]:
    """Make a backup on every enabled target (or the given ones). Runs as a job."""
    if kind not in KINDS:
        raise BackupError("invalid_kind")
    if not _lock.acquire(blocking=False):
        raise BackupError("busy", "Another backup or restore is running")
    db = ctx.db
    try:
        cfg = get_section(db, "backup")
        passphrase = cfg.get("passphrase") or ""
        if not passphrase:
            raise BackupError("no_passphrase", "Set a backup passphrase first")
        query = select(BackupTarget).order_by(BackupTarget.name)
        if target_ids:
            query = query.where(BackupTarget.id.in_(target_ids))
        else:
            query = query.where(BackupTarget.is_enabled.is_(True))
        targets = list(db.scalars(query))
        if not targets:
            raise BackupError("no_targets", "No backup location configured")
        ctx.add_total(len(targets))
        snapshot = take_snapshot(db)
        results = []
        for target in targets:
            try:
                name = _backup_target(db, ctx, target, kind, snapshot, passphrase, int(cfg.get("keep_full") or 4))
                target.last_status, target.last_message = "ok", ""
                target.last_backup_at, target.last_backup_name = utcnow(), name
                results.append({"target": target.name, "ok": True, "name": name})
            except (BackupError, remote_mod.RemoteError) as exc:
                db.rollback()
                target = db.get(BackupTarget, target.id)
                target.last_status, target.last_message = "failed", str(exc)
                ctx.step(False, f"{target.name}: {exc}", target=target.name, code=exc.code)
                results.append({"target": target.name, "ok": False, "error": str(exc)})
            db.commit()
        failed = [r for r in results if not r["ok"]]
        audit.record(
            db,
            "backup.run",
            actor_type=ctx.actor.type,
            actor=ctx.actor.name,
            ip=ctx.actor.ip,
            target=kind,
            details={"targets": results},
            success=not failed,
            message="; ".join(f"{r['target']}: {r['error']}" for r in failed),
        )
        notify(db, not failed, kind, results)
        return {"kind": kind, "targets": results}
    except BackupError as exc:
        notify(db, False, kind, [{"target": "-", "ok": False, "error": str(exc)}])
        raise
    finally:
        _lock.release()


def notify(db: Session, ok: bool, kind: str, results: list[dict[str, Any]]) -> None:
    cfg = get_section(db, "backup")
    mode, to = cfg.get("notify_on", "failure"), (cfg.get("notify_email") or "").strip()
    if not to or mode == "never" or (ok and mode != "always"):
        return
    smtp = get_section(db, "smtp")
    if not smtp.get("host"):
        return
    status = "succeeded" if ok else "FAILED"
    lines = [f"- {r['target']}: {r.get('name') or r.get('error')}" for r in results]
    body = (
        f"The {kind} backup {status} on {socket.gethostname()}.\n\n"
        + "\n".join(lines)
        + f"\n\nDe {'volledige' if kind == 'full' else 'incrementele'} back-up is "
        + ("gelukt" if ok else "MISLUKT")
        + ".\n"
    )
    try:
        asyncio.run(send_mail(smtp, to, f"Backup {status} - UniFi Fabric License Plate Importer", body))
    except Exception:  # a mail problem must never break the backup
        log.exception("could not send the backup notification")


# ---------------------------------------------------------------- restore


Fetch = Callable[[str], bytes]


@dataclass
class LoadedBackup:
    name: str
    revision: str | None
    tables: dict[str, dict[str, Any]]  # name -> {"pk": [...], "rows": {pk: row}}
    secret_key: str
    chain: list[str]


def load_backup(name: str, names: list[str], fetch: Fetch, passphrase: str, note: Callable[[str], None] = lambda m: None) -> LoadedBackup:
    """Download and decrypt the chain of `name` and replay it into the final table contents."""
    chain = chain_of(name, names)
    if chain is None:
        raise BackupError("chain_incomplete", f"A backup needed to restore {name} is missing")
    tables: dict[str, dict[str, Any]] = {}
    revision: str | None = None
    secret_key = ""
    for i, part in enumerate(chain):
        note(f"Downloading {part.name} ({i + 1}/{len(chain)})")
        manifest, payload, secrets = read_archive(decrypt_blob(fetch(part.name), passphrase))
        if manifest.get("name") != part.name:
            raise BackupError("damaged", f"{part.name} contains another backup ({manifest.get('name')})")
        if i and manifest.get("revision") != revision:
            raise BackupError("damaged", "The backups in this chain have different database versions")
        revision = manifest.get("revision")
        secret_key = secrets.get("secret_key") or secret_key
        for table, data in payload.items():
            entry = tables.setdefault(table, {"pk": data["pk"], "rows": {}})
            for pk in data.get("deleted", []):
                entry["rows"].pop(pk, None)
            for row in data.get("rows", []):
                entry["rows"][_pk(row, data["pk"])] = row
    return LoadedBackup(name, revision, tables, secret_key, [p.name for p in chain])


def _reencrypt(tables: dict[str, dict[str, Any]], old_key: str) -> int:
    """Re-encrypt secrets stored with another server's secret key. Returns the number of
    secrets that could not be read (they are cleared)."""
    current = get_settings().secret_key
    if not old_key or old_key == current:
        return 0
    lost = 0

    def convert(value: str) -> str:
        nonlocal lost
        if not value:
            return value
        plain = decrypt(value, old_key)
        if plain is None:
            lost += 1
            return ""
        return encrypt(plain, current)

    for row in tables.get("settings", {}).get("rows", {}).values():
        fields = SECRET_FIELDS.get(row.get("key"), set())
        value = row.get("value")
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            row["value"] = {k: convert(v) if k in fields and isinstance(v, str) else v for k, v in value.items()}
    for table, column in ENCRYPTED_COLUMNS:
        for row in tables.get(table, {}).get("rows", {}).values():
            if isinstance(row.get(column), str):
                row[column] = convert(row[column])
    return lost


def _decode(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for col in table.columns:
        if col.name not in row:
            continue
        value = row[col.name]
        if isinstance(value, str) and isinstance(col.type, DateTime):
            value = datetime.fromisoformat(value)
        out[col.name] = value
    return out


def _load_tables(conn: Connection, tables: dict[str, dict[str, Any]]) -> int:
    existing = _reflect(conn)
    for table in reversed(existing):
        conn.execute(table.delete())
    count = 0
    for table in existing:
        rows = [_decode(table, r) for r in tables.get(table.name, {}).get("rows", {}).values()]
        if rows:
            conn.execute(table.insert(), rows)
            count += len(rows)
    if conn.dialect.name == "postgresql":
        for table in existing:
            pk = list(table.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement in (True, "auto") and pk[0].type.python_type is int:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"COALESCE(MAX({pk[0].name}), 1), MAX({pk[0].name}) IS NOT NULL) FROM {table.name}"
                    )
                )
    return count


def _alembic_config():
    from alembic.config import Config

    cfg = Config()  # no ini file: keeps the application's logging setup
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return cfg


def _known_revision(revision: str) -> bool:
    from alembic.script import ScriptDirectory

    try:
        return ScriptDirectory.from_config(_alembic_config()).get_revision(revision) is not None
    except Exception:
        return False


SESSION_DETAILS = ("last_seen_at", "ip_address", "user_agent")


def _sessions(conn: Connection) -> list[dict[str, Any]]:
    meta = MetaData()
    sessions = Table("user_sessions", meta, autoload_with=conn)
    users = Table("users", meta, autoload_with=conn)
    extra = [sessions.c[name] for name in SESSION_DETAILS if name in sessions.c]
    query = select(sessions.c.id, sessions.c.created_at, sessions.c.expires_at, *extra, users.c.username).join_from(
        sessions, users, sessions.c.user_id == users.c.id
    )
    return [dict(r) for r in conn.execute(query).mappings()]


def _restore_sessions(conn: Connection, sessions: list[dict[str, Any]]) -> None:
    """Keep people signed in whose account (same username, active) is in the restored data."""
    conn.execute(text("DELETE FROM user_sessions"))
    users = {r.username: r.id for r in conn.execute(text("SELECT id, username, is_active FROM users")) if r.is_active}
    table = Table("user_sessions", MetaData(), autoload_with=conn)
    details = [name for name in SESSION_DETAILS if name in table.c]
    keep = [
        {"id": s["id"], "user_id": users[s["username"]], "created_at": s["created_at"], "expires_at": s["expires_at"], **{k: s[k] for k in details if k in s}}
        for s in sessions
        if s["username"] in users
    ]
    if keep:
        conn.execute(table.insert(), keep)


def apply_backup(backup: LoadedBackup, note: Callable[[str], None] = lambda m: None) -> dict[str, Any]:
    """Replace the database contents with the backup. Only sessions of accounts that also
    exist in the backup stay signed in."""
    from alembic import command

    tables = {k: {**v, "rows": dict(v["rows"])} for k, v in backup.tables.items()}
    lost = _reencrypt(tables, backup.secret_key)
    engine = get_engine()
    with engine.connect() as conn:
        db_revision = current_revision(conn)
        sessions = _sessions(conn)
    if backup.revision == db_revision:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM user_sessions"))
            rows = _load_tables(conn, tables)
            _restore_sessions(conn, sessions)
    else:
        if not backup.revision or not _known_revision(backup.revision):
            raise BackupError("backup_newer", "This backup was made by a newer version of the application. Update first.")
        note(f"Database version {db_revision} differs from the backup ({backup.revision}): rebuilding the schema")
        with engine.connect() as conn:
            jobs_table = Table("jobs", MetaData(), autoload_with=conn)
            job_rows = [dict(r) for r in conn.execute(select(jobs_table)).mappings()]
        meta = MetaData()
        meta.reflect(bind=engine)
        meta.drop_all(bind=engine)
        command.upgrade(_alembic_config(), backup.revision)
        with engine.begin() as conn:
            rows = _load_tables(conn, tables)
        command.upgrade(_alembic_config(), "head")
        with engine.begin() as conn:
            jobs_table = Table("jobs", MetaData(), autoload_with=conn)
            if job_rows:
                conn.execute(jobs_table.insert(), job_rows)
            _restore_sessions(conn, sessions)
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT setval(pg_get_serial_sequence('jobs', 'id'), COALESCE(MAX(id), 1)) FROM jobs"))
    clear_states()
    return {"name": backup.name, "chain": backup.chain, "rows": rows, "secrets_lost": lost}


def _safety_copy(db: Session, passphrase: str) -> str | None:
    """Store a full backup of the current data locally before a restore overwrites it."""
    if not passphrase:
        return None
    snapshot = take_snapshot(db)
    payload, _, _ = _payload(snapshot, None)
    name = make_name("full")
    manifest = {"format": FORMAT, "name": name, "kind": "full", "parent": None, "created_at": utcnow().isoformat(), "revision": snapshot.revision}
    folder = _state_dir() / "pre-restore"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_bytes(encrypt_blob(build_archive(manifest, payload, {"secret_key": get_settings().secret_key}), passphrase))
    path.chmod(0o600)
    for old in sorted(folder.glob(f"*{SUFFIX}"))[:-3]:
        old.unlink(missing_ok=True)
    return str(path)


def run_restore(ctx: JobContext, name: str, names: list[str], fetch: Fetch, passphrase: str | None, source: str) -> dict[str, Any]:
    """Restore `name` (and the backups it depends on). Runs as a job."""
    if not _lock.acquire(blocking=False):
        raise BackupError("busy", "Another backup or restore is running")
    db = ctx.db
    try:
        current_pass = get_section(db, "backup").get("passphrase") or ""
        passphrase = passphrase or current_pass
        if not passphrase:
            raise BackupError("no_passphrase", "Enter the passphrase of the backup")
        chain = chain_of(name, names) or []
        ctx.add_total(len(chain) + 1)
        backup = load_backup(name, names, fetch, passphrase, lambda m: ctx.step(True, m))
        safety = _safety_copy(db, current_pass)
        if safety:
            ctx.note(f"Copy of the current data saved to {safety}")
        db.commit()  # no open transaction may hold locks on the tables being replaced
        result = apply_backup(backup, ctx.note)
        db.expire_all()
        ctx.step(True, f"Restored {name}: {result['rows']} rows")
        if result["secrets_lost"]:
            ctx.note(f"{result['secrets_lost']} stored passwords or tokens could not be read and must be entered again", ok=False)
        audit.record(
            db,
            "backup.restore",
            actor_type=ctx.actor.type,
            actor=ctx.actor.name,
            ip=ctx.actor.ip,
            target=name,
            details={"source": source, "chain": result["chain"], "rows": result["rows"]},
        )
        return result
    finally:
        _lock.release()


def generate_passphrase() -> str:
    return "-".join(pysecrets.token_urlsafe(6) for _ in range(4))
