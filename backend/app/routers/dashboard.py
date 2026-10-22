"""Dashboard: status per location (console), recent syncs, scheduled imports and backups."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import AuditLog, BackupTarget, Console, ConsolePlate, ImportSchedule, Job, User, Vehicle
from ..services import jobs
from .import_schedules import schedule_dict

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

SYNC_KINDS = ("import", "assign", "remove", "scan")
WINDOW = timedelta(days=7)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:  # SQLite drops the timezone
        return value.replace(tzinfo=timezone.utc)
    return value


def _status(console: Console, missing: int, failures: int, scan_failed: bool) -> str:
    if not console.is_active:
        return "inactive"
    if console.last_test_ok is False or scan_failed:
        return "error"
    if console.last_scan_at is None:
        return "unknown"
    if missing or failures:
        return "warning"
    return "ok"


@router.get("")
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    now = datetime.now(timezone.utc)
    managed = set(db.scalars(select(Vehicle.plate_key)))

    # Console changes of the last week, newest first, grouped per console name.
    events: dict[str, list[AuditLog]] = {}
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.action.like("access.%"), AuditLog.created_at >= now - WINDOW)
        .order_by(AuditLog.created_at.desc())
        .limit(5000)
    )
    for row in rows:
        name = (row.details or {}).get("console")
        if name:
            events.setdefault(name, []).append(row)

    locations = []
    for console in db.scalars(select(Console).order_by(Console.sort_order, Console.name)):
        keys = set(db.scalars(select(ConsolePlate.plate_key).where(ConsolePlate.console_id == console.id)))
        last_scan = db.scalar(
            select(AuditLog).where(AuditLog.action == "console.scanned", AuditLog.target == console.name).order_by(AuditLog.created_at.desc()).limit(1)
        )
        scan_failed = last_scan is not None and not last_scan.success
        changes = events.get(console.name, [])
        recent_failures = [e for e in changes if not e.success and _aware(e.created_at) >= now - timedelta(hours=24)]
        last_ok = next((e for e in changes if e.success), None)
        last_failure = next((e for e in changes if not e.success), None)
        missing = len(managed - keys)
        locations.append({
            "id": console.id,
            "name": console.name,
            "location": console.location,
            "is_active": console.is_active,
            "status": _status(console, missing, len(recent_failures), scan_failed),
            "reachable": console.last_test_ok,
            "last_test_at": console.last_test_at,
            "last_scan_at": console.last_scan_at,
            "scan_error": last_scan.message if scan_failed else "",
            "present": len(managed & keys),
            "missing": missing,
            "unmanaged": len(keys - managed),
            "changes_7d": sum(1 for e in changes if e.success),
            "failures_24h": len(recent_failures),
            "last_change_at": last_ok.created_at if last_ok else None,
            "last_failure_at": last_failure.created_at if last_failure else None,
            "last_failure": last_failure.message if last_failure else "",
        })

    recent = db.scalars(select(Job).where(Job.kind.in_(SYNC_KINDS)).order_by(Job.created_at.desc()).limit(8))
    syncs = []
    for job in recent:
        data = jobs.to_dict(job, with_log=False)
        params = job.params or {}
        data["source"] = params.get("source", "")
        data["schedule"] = params.get("schedule", "")
        data["mode"] = params.get("mode", "")
        syncs.append(data)

    targets = list(db.scalars(select(BackupTarget).where(BackupTarget.is_enabled)))
    last_backup = max((t.last_backup_at for t in targets if t.last_backup_at), default=None, key=_aware)
    return {
        "vehicles": len(managed),
        "locations": locations,
        "syncs": syncs,
        "schedules": [
            {k: v for k, v in schedule_dict(s).items() if k in ("id", "name", "is_enabled", "mode", "next_run", "last_run_at", "last_status", "last_message")}
            for s in db.scalars(select(ImportSchedule).order_by(ImportSchedule.name))
        ],
        "backup": {
            "targets": len(targets),
            "failed": sum(1 for t in targets if t.last_status == "failed"),
            "last_backup_at": last_backup,
        },
    }
