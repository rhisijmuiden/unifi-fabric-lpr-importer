"""Scheduled imports: fetch a CSV file from a URL or a file server and import it.

The file goes through the same column mapping as the CSV wizard and the same
import path as the wizard and the REST API (`vehicles.run_import`). Safety rules
for unattended runs:
  - an unchanged file is skipped (optional),
  - a file without valid vehicles never starts a full sync,
  - a full sync that would remove more vehicles than `max_remove` stops without changes.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..models import Console, ImportSchedule
from ..security import decrypt
from . import backup, jobs, remote
from .csvfile import MAX_BYTES, CsvError, convert, read_csv
from .vehicles import plan_import, run_import

PROTOCOLS = ("url", "scp", "ftps", "ftp")
HTTP_TIMEOUT = 60


class ScheduleError(Exception):
    """A scheduled import cannot run. `code` is translated in the UI."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def remote_config(db: Session, sched: ImportSchedule) -> remote.TargetConfig:
    cfg = remote.TargetConfig(
        protocol=sched.protocol,
        host=sched.host,
        port=sched.port,
        username=sched.username,
        password=decrypt(sched.password) or "" if sched.password else "",
        auth_method=sched.auth_method,
        host_key=sched.host_key,
        remote_path=sched.remote_path,
        ftps_implicit=sched.ftps_implicit,
        verify_tls=sched.verify_tls,
        passive=sched.passive,
        create_dir=False,
    )
    if cfg.protocol == "scp" and cfg.auth_method == "key":
        cfg.private_key = backup.ssh_key(db)[0]
    return cfg


def _fetch_url(sched: ImportSchedule) -> bytes:
    url = sched.url.strip()
    if not url.lower().startswith(("https://", "http://")):
        raise ScheduleError("invalid_url", "The address must start with https://")
    password = decrypt(sched.password) or "" if sched.password else ""
    auth = (sched.username, password) if sched.username else None
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, verify=sched.verify_tls, follow_redirects=True, auth=auth) as client:
            with client.stream("GET", url) as response:
                if response.status_code in (401, 403):
                    raise ScheduleError("login_failed", f"HTTP {response.status_code}")
                if response.status_code == 404:
                    raise ScheduleError("not_found", "HTTP 404")
                if response.status_code >= 400:
                    raise ScheduleError("http_error", f"HTTP {response.status_code}")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ScheduleError("file_too_large")
                return bytes(data)
    except httpx.ConnectError as exc:
        code = "tls_verify_failed" if "CERTIFICATE_VERIFY_FAILED" in str(exc) else "connect_failed"
        raise ScheduleError(code, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ScheduleError("connect_failed", str(exc) or exc.__class__.__name__) from exc


def fetch(db: Session, sched: ImportSchedule) -> bytes:
    """Download the file. Pins the SSH host key of an SCP server on first use."""
    if sched.protocol == "url":
        return _fetch_url(sched)
    if sched.protocol not in PROTOCOLS:
        raise ScheduleError("invalid_protocol")
    try:
        conn = remote.connect(remote_config(db, sched))
        try:
            data = conn.download(sched.filename)
        finally:
            conn.close()
    except remote.RemoteError as exc:
        raise ScheduleError(exc.code, str(exc)) from exc
    if sched.protocol == "scp" and not sched.host_key and conn.host_key:
        sched.host_key = conn.host_key  # trust on first use, then pinned
        if sched.id is not None:
            db.commit()
    if len(data) > MAX_BYTES:
        raise ScheduleError("file_too_large")
    return data


def rows_of(sched: ImportSchedule, content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        headers, raw = read_csv(content)
    except CsvError as exc:
        raise ScheduleError(exc.code) from exc
    mapping = sched.mapping or {}
    missing = [h for h in mapping.values() if h and h not in headers]
    if missing:
        raise ScheduleError("column_missing", ", ".join(missing))
    return headers, convert(raw, mapping, sched.defaults or {}, sched.filter_locations, sched.filter_departments)


def console_ids(db: Session, sched: ImportSchedule) -> list[int]:
    stmt = select(Console.id).where(Console.is_active)
    if sched.console_ids is not None:
        stmt = stmt.where(Console.id.in_(sched.console_ids))
    return list(db.scalars(stmt))


def _finish(db: Session, sched: ImportSchedule, status: str, message: str) -> None:
    sched.last_run_at = datetime.now(timezone.utc)
    sched.last_status = status
    sched.last_message = message[:2000]
    db.commit()


def run(ctx: jobs.JobContext, schedule_id: int, forced: bool = False) -> dict[str, Any]:
    """Job body. `forced` (Run now) also imports a file that did not change."""
    db = ctx.db
    sched = db.get(ImportSchedule, schedule_id)
    if sched is None:
        raise ScheduleError("not_found", "The scheduled import no longer exists")
    sched.last_job_id = ctx.job.id
    db.commit()
    actor = ctx.actor.audit()
    try:
        content = fetch(db, sched)
        digest = hashlib.sha256(content).hexdigest()
        ctx.note(f"{sched.name}: {len(content)} bytes downloaded")
        if sched.skip_unchanged and not forced and digest == sched.last_hash:
            _finish(db, sched, "unchanged", "")
            ctx.note("The file has not changed since the last run; nothing to do")
            return {"schedule": sched.name, "unchanged": True}
        _, rows = rows_of(sched, content)
        ids = console_ids(db, sched)
        plan = plan_import(db, rows, ids, sched.mode)
        summary = plan["summary"]
        valid = summary["total"] - summary["invalid"]
        ctx.note(f"{summary['total']} rows: {summary['new']} new, {summary['changed']} changed, {summary['invalid']} invalid")
        if not valid:
            raise ScheduleError("no_vehicles", "The file holds no valid vehicles")
        if sched.mode == "full" and sched.max_remove and summary["remove"] > sched.max_remove:
            raise ScheduleError(
                "too_many_removals",
                f"The full sync would remove {summary['remove']} vehicles, more than the limit of {sched.max_remove}. Nothing was changed.",
            )
        audit.record(db, "import.started", details={"schedule": sched.name, "rows": len(rows), "mode": sched.mode, "source": "schedule"}, **actor)
        result = run_import(ctx, rows, "schedule", ids, sched.mode)
    except Exception as exc:
        db.rollback()
        sched = db.get(ImportSchedule, schedule_id)
        if sched is not None:
            _finish(db, sched, "failed", str(exc))
        audit.record(db, "import.schedule_failed", target=sched.name if sched else str(schedule_id), success=False, message=str(exc), **actor)
        raise
    sched.last_hash = digest
    _finish(db, sched, "ok" if not ctx.job.failed else "failed", f"{ctx.job.failed} changes failed" if ctx.job.failed else "")
    return {"schedule": sched.name, **result}


def start(db: Session, sched: ImportSchedule, actor: jobs.Actor, forced: bool = False) -> Any:
    params = {"schedule": sched.name, "schedule_id": sched.id, "mode": sched.mode, "source": "schedule", "scheduled": not forced}
    schedule_id = sched.id
    return jobs.start(db, "import", actor, params, lambda ctx: run(ctx, schedule_id, forced))
