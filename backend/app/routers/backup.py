from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_admin, user_actor
from ..models import BackupTarget, User
from ..schemas import BackupRunIn, BackupSettingsIn, BackupTargetIn, BackupTargetTestIn, RestoreIn
from ..security import encrypt
from ..services import backup, jobs, remote, scheduler
from ..settings_store import public_section, update_section
from .consoles import clean_host

router = APIRouter(prefix="/api/backup", tags=["backup"])

MAX_UPLOAD = 512 * 1024 * 1024


def target_dict(t: BackupTarget) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "protocol": t.protocol,
        "host": t.host,
        "port": t.port,
        "username": t.username,
        "password_set": bool(t.password),
        "auth_method": t.auth_method,
        "host_key": t.host_key,
        "remote_path": t.remote_path,
        "ftps_implicit": t.ftps_implicit,
        "verify_tls": t.verify_tls,
        "passive": t.passive,
        "is_enabled": t.is_enabled,
        "last_backup_at": t.last_backup_at,
        "last_backup_name": t.last_backup_name,
        "last_status": t.last_status,
        "last_message": t.last_message,
    }


def _target(db: Session, target_id: int) -> BackupTarget:
    target = db.get(BackupTarget, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return target


def _settings(db: Session) -> dict:
    data = public_section(db, "backup")
    data.pop("ssh_private_key_set", None)
    data["ssh_public_key"] = backup.ssh_key(db)[1]
    now = datetime.now()
    data["next_runs"] = {
        kind: scheduler.next_slot(data[f"schedule_{kind}"], now).isoformat() if data[f"schedule_{kind}"].get("enabled") else None
        for kind in backup.KINDS
    }
    return data


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return _settings(db)


@router.put("/settings")
def put_settings(body: BackupSettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    data = body.model_dump()
    update_section(db, "backup", data)
    audit.record(
        db,
        "backup.settings_updated",
        user=admin,
        details={"passphrase_changed": body.passphrase is not None, "keep_full": body.keep_full},
        request=request,
    )
    return _settings(db)


@router.post("/settings/generate-passphrase")
def generate_passphrase(_: User = Depends(require_admin)) -> dict:
    return {"passphrase": backup.generate_passphrase()}


@router.post("/settings/ssh-key")
def new_ssh_key(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    update_section(db, "backup", {"ssh_private_key": ""})
    public = backup.ssh_key(db)[1]
    audit.record(db, "backup.ssh_key_replaced", user=admin, request=request)
    return {"ssh_public_key": public}


# ---------------------------------------------------------------- targets


@router.get("/targets")
def list_targets(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    return [target_dict(t) for t in db.scalars(select(BackupTarget).order_by(BackupTarget.name))]


def _apply(target: BackupTarget, body: BackupTargetIn) -> None:
    target.name = body.name.strip()
    if target.protocol != body.protocol or target.host != clean_host(body.host):
        target.host_key = ""
    target.protocol = body.protocol
    target.host = clean_host(body.host)
    target.port = body.port or remote.DEFAULT_PORTS[body.protocol]
    target.username = body.username.strip()
    target.auth_method = body.auth_method
    target.remote_path = body.remote_path.strip() or "lpr-importer"
    target.ftps_implicit = body.ftps_implicit
    target.verify_tls = body.verify_tls
    target.passive = body.passive
    target.is_enabled = body.is_enabled
    if body.password is not None:
        target.password = encrypt(body.password) if body.password else ""
    if body.host_key is not None:
        target.host_key = body.host_key.strip()


@router.post("/targets", status_code=201)
def create_target(body: BackupTargetIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    if db.scalar(select(BackupTarget).where(BackupTarget.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    target = BackupTarget(host_key="")
    _apply(target, body)
    db.add(target)
    db.commit()
    audit.record(db, "backup.target_created", user=admin, target=target.name, details={"protocol": target.protocol, "host": target.host}, request=request)
    return target_dict(target)


@router.put("/targets/{target_id}")
def update_target(target_id: int, body: BackupTargetIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    target = _target(db, target_id)
    other = db.scalar(select(BackupTarget).where(BackupTarget.name == body.name.strip(), BackupTarget.id != target_id))
    if other:
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    _apply(target, body)
    db.commit()
    audit.record(db, "backup.target_updated", user=admin, target=target.name, details={"protocol": target.protocol, "host": target.host}, request=request)
    return target_dict(target)


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    target = _target(db, target_id)
    name = target.name
    db.delete(target)
    db.commit()
    audit.record(db, "backup.target_deleted", user=admin, target=name, request=request)
    return Response(status_code=204)


@router.post("/targets/test")
def test_target(body: BackupTargetTestIn, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    """Connect with the settings in the form (stored password and pinned host key of
    `target_id` when not given), create the folder and write, read and delete a test file."""
    stored = db.get(BackupTarget, body.target_id) if body.target_id else None
    probe = BackupTarget(host_key="", password="")
    _apply(probe, BackupTargetIn(**{**body.model_dump(exclude={"target_id"}), "name": body.name or "test"}))
    if stored is not None:
        if body.password is None:
            probe.password = stored.password
        if body.host_key is None and stored.protocol == probe.protocol and stored.host == probe.host:
            probe.host_key = stored.host_key
    try:
        conn = remote.connect(backup.target_config(db, probe))
        try:
            files = conn.list()
            conn.upload(".lpr-write-test", b"ok")
            readable = conn.download(".lpr-write-test") == b"ok"
            conn.delete(".lpr-write-test")
        finally:
            conn.close()
    except remote.RemoteError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}
    if stored is not None and conn.host_key and not stored.host_key:
        stored.host_key = conn.host_key
        db.commit()
    backups = [f for f in files if backup.parse_name(f.name)]
    return {"ok": readable, "host_key": conn.host_key, "backups": len(backups), "code": None if readable else "transfer_failed"}


@router.get("/targets/{target_id}/backups")
def list_backups(target_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    target = _target(db, target_id)
    try:
        conn = backup.connect(db, target)
        try:
            files = conn.list()
        finally:
            conn.close()
    except remote.RemoteError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{exc.code}:{exc}") from exc
    return {"target": target_dict(target), "items": backup.catalog(files)}


@router.get("/targets/{target_id}/backups/{name}")
def download_backup(target_id: int, name: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    target = _target(db, target_id)
    if backup.parse_name(name) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        conn = backup.connect(db, target)
        try:
            data = conn.download(name)
        finally:
            conn.close()
    except remote.RemoteError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{exc.code}:{exc}") from exc
    audit.record(db, "backup.download", user=admin, target=name, details={"location": target.name}, request=request)
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- run and restore


@router.post("/run", status_code=202)
def run_backup(body: BackupRunIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    job = jobs.start(
        db,
        "backup",
        user_actor(admin, request),
        {"kind": body.kind, "target_ids": body.target_ids},
        lambda ctx: backup.run_backup(ctx, body.kind, body.target_ids),
    )
    return jobs.to_dict(job, with_log=False)


@router.post("/restore", status_code=202)
def restore(body: RestoreIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    if not body.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirm_required")
    target = _target(db, body.target_id)
    target_id, location = target.id, target.name

    def work(ctx: jobs.JobContext) -> dict:
        conn = backup.connect(ctx.db, ctx.db.get(BackupTarget, target_id))
        try:
            names = [f.name for f in conn.list()]
            return backup.run_restore(ctx, body.name, names, conn.download, body.passphrase, f"location:{location}")
        finally:
            conn.close()

    job = jobs.start(db, "restore", user_actor(admin, request), {"name": body.name, "location": location}, work)
    return jobs.to_dict(job, with_log=False)


@router.post("/restore/upload", status_code=202)
async def restore_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    name: str = Form(""),
    passphrase: str = Form(""),
    confirm: bool = Form(False),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Restore from backup files on this computer: a full backup, optionally with the
    incremental backups after it. `name` picks the one to restore (default: newest)."""
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirm_required")
    blobs: dict[str, bytes] = {}
    total = 0
    for upload in files:
        filename = (upload.filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if backup.parse_name(filename) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid_file:{filename}")
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "too_large")
        blobs[filename] = data
    names = sorted(blobs, key=lambda n: backup.parse_name(n).stamp)
    chosen = name or names[-1]
    if chosen not in blobs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_found")
    job = jobs.start(
        db,
        "restore",
        user_actor(admin, request),
        {"name": chosen, "location": "upload"},
        lambda ctx: backup.run_restore(ctx, chosen, names, blobs.__getitem__, passphrase or None, "upload"),
    )
    return jobs.to_dict(job, with_log=False)
