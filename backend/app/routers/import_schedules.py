from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, require_admin, require_operator, user_actor
from ..models import ImportSchedule, User
from ..schemas import ImportScheduleIn, ImportScheduleTestIn
from ..security import encrypt
from ..services import import_schedules, jobs, remote, scheduler
from ..services.csvfile import CsvError, read_csv, suggest_mapping
from ..services.vehicles import plan_import
from .consoles import clean_host

router = APIRouter(prefix="/api/import/schedules", tags=["import"])

PORTS = {**remote.DEFAULT_PORTS, "url": 443}


def schedule_dict(s: ImportSchedule) -> dict:
    sched = s.schedule or {}
    return {
        "id": s.id,
        "name": s.name,
        "is_enabled": s.is_enabled,
        "protocol": s.protocol,
        "url": s.url,
        "host": s.host,
        "port": s.port,
        "username": s.username,
        "password_set": bool(s.password),
        "auth_method": s.auth_method,
        "host_key": s.host_key,
        "remote_path": s.remote_path,
        "filename": s.filename,
        "ftps_implicit": s.ftps_implicit,
        "verify_tls": s.verify_tls,
        "passive": s.passive,
        "mapping": s.mapping or {},
        "defaults": s.defaults or {},
        "filter_locations": s.filter_locations or [],
        "filter_departments": s.filter_departments or [],
        "console_ids": s.console_ids,
        "mode": s.mode,
        "max_remove": s.max_remove,
        "skip_unchanged": s.skip_unchanged,
        "schedule": sched,
        "next_run": scheduler.next_slot(sched, datetime.now()).isoformat() if s.is_enabled and sched.get("enabled") else None,
        "last_run_at": s.last_run_at,
        "last_status": s.last_status,
        "last_message": s.last_message,
        "last_job_id": s.last_job_id,
    }


def _get(db: Session, schedule_id: int) -> ImportSchedule:
    sched = db.get(ImportSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return sched


def _clean_list(values: list[str]) -> list[str]:
    return sorted({" ".join(v.split()) for v in values if v.strip()})


def _apply(s: ImportSchedule, body: ImportScheduleIn) -> None:
    host = clean_host(body.host) if body.protocol != "url" else ""
    if s.protocol != body.protocol or s.host != host:
        s.host_key = ""
    s.name = body.name.strip()
    s.is_enabled = body.is_enabled
    s.protocol = body.protocol
    s.url = body.url.strip() if body.protocol == "url" else ""
    s.host = host
    s.port = body.port or PORTS[body.protocol]
    s.username = body.username.strip()
    s.auth_method = body.auth_method
    s.remote_path = body.remote_path.strip()
    s.filename = body.filename.strip()
    s.ftps_implicit = body.ftps_implicit
    s.verify_tls = body.verify_tls
    s.passive = body.passive
    s.mapping = {k: v for k, v in body.mapping.items() if v}
    s.defaults = {k: v.strip() for k, v in body.defaults.items() if v.strip()}
    s.filter_locations = _clean_list(body.filter_locations)
    s.filter_departments = _clean_list(body.filter_departments)
    s.console_ids = body.console_ids
    s.mode = body.mode
    s.max_remove = body.max_remove
    s.skip_unchanged = body.skip_unchanged
    s.schedule = body.schedule.model_dump()
    if body.password is not None:
        s.password = encrypt(body.password) if body.password else ""
    if body.host_key is not None:
        s.host_key = body.host_key.strip()


def _validate(body: ImportScheduleIn) -> None:
    if body.protocol == "url":
        if not body.url.strip().lower().startswith(("https://", "http://")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_url")
    elif not body.host.strip() or not body.filename.strip() or "/" in body.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file_required")
    if not body.mapping.get("plate"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "plate_column_required")
    if not body.mapping.get("department") and not body.defaults.get("department", "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "department_required")


def _audit_details(s: ImportSchedule) -> dict:
    return {"protocol": s.protocol, "host": s.host or s.url, "mode": s.mode, "enabled": s.is_enabled}


@router.get("")
def list_schedules(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    return [schedule_dict(s) for s in db.scalars(select(ImportSchedule).order_by(ImportSchedule.name))]


@router.post("", status_code=201)
def create_schedule(body: ImportScheduleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    _validate(body)
    if db.scalar(select(ImportSchedule).where(ImportSchedule.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    sched = ImportSchedule(host_key="", password="")
    _apply(sched, body)
    db.add(sched)
    db.commit()
    audit.record(db, "import.schedule_created", user=admin, target=sched.name, details=_audit_details(sched), request=request)
    return schedule_dict(sched)


@router.put("/{schedule_id}")
def update_schedule(schedule_id: int, body: ImportScheduleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    _validate(body)
    sched = _get(db, schedule_id)
    if db.scalar(select(ImportSchedule).where(ImportSchedule.name == body.name.strip(), ImportSchedule.id != schedule_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    _apply(sched, body)
    sched.last_hash = ""  # new settings: import the next file even when it did not change
    db.commit()
    audit.record(db, "import.schedule_updated", user=admin, target=sched.name, details=_audit_details(sched), request=request)
    return schedule_dict(sched)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    sched = _get(db, schedule_id)
    name = sched.name
    db.delete(sched)
    db.commit()
    audit.record(db, "import.schedule_deleted", user=admin, target=name, request=request)
    return Response(status_code=204)


@router.post("/test")
def test_schedule(body: ImportScheduleTestIn, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    """Fetch the file with the settings in the form and show its columns and what an import would do.
    Nothing is changed."""
    stored = db.get(ImportSchedule, body.schedule_id) if body.schedule_id else None
    probe = ImportSchedule(host_key="", password="")
    _apply(probe, ImportScheduleIn(**{**body.model_dump(exclude={"schedule_id"}), "name": body.name or "test"}))
    if stored is not None:
        if body.password is None:
            probe.password = stored.password
        if body.host_key is None and stored.protocol == probe.protocol and stored.host == probe.host:
            probe.host_key = stored.host_key
    try:
        content = import_schedules.fetch(db, probe)
        try:
            headers, raw = read_csv(content)
        except CsvError as exc:
            raise import_schedules.ScheduleError(exc.code) from exc
    except import_schedules.ScheduleError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}
    host_key = probe.host_key if probe.protocol == "scp" else ""
    if stored is not None and host_key and not stored.host_key:
        stored.host_key = host_key
        db.commit()
    result: dict = {"ok": True, "bytes": len(content), "headers": headers, "sample": raw[:5], "suggested": suggest_mapping(headers), "host_key": host_key}
    if probe.mapping.get("plate"):
        missing = [h for h in probe.mapping.values() if h not in headers]
        if missing:
            result["missing_columns"] = missing
        else:
            _, rows = import_schedules.rows_of(probe, content)
            plan = plan_import(db, rows, import_schedules.console_ids(db, probe), probe.mode)
            result["summary"] = plan["summary"]
            result["consoles"] = plan["consoles"]
            result["remove"] = plan["remove"][:50]
    return result


@router.post("/{schedule_id}/run", status_code=202)
def run_now(schedule_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    sched = _get(db, schedule_id)
    audit.record(db, "import.schedule_run", user=user, target=sched.name, request=request)
    job = import_schedules.start(db, sched, user_actor(user, request), forced=True)
    return jobs.to_dict(job, with_log=False)
