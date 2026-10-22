from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import AuditLog, Console, ConsolePlate, User, Vehicle

router = APIRouter(prefix="/api/stats", tags=["statistics"])

ACTIVITY = ("access.plate_assigned", "access.plate_removed")


@router.get("")
def stats(db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    def grouped(col) -> list[dict]:
        rows = db.execute(select(col, func.count()).group_by(col).order_by(func.count().desc(), col))
        return [{"name": name or "", "count": count} for name, count in rows]

    managed = set(db.scalars(select(Vehicle.plate_key)))
    consoles = []
    for console in db.scalars(select(Console).order_by(Console.sort_order, Console.name)):
        keys = set(db.scalars(select(ConsolePlate.plate_key).where(ConsolePlate.console_id == console.id)))
        consoles.append({
            "id": console.id,
            "name": console.name,
            "location": console.location,
            "is_active": console.is_active,
            "present": len(managed & keys),
            "missing": len(managed - keys),
            "unmanaged": len(keys - managed),
            "last_scan_at": console.last_scan_at,
        })

    since = datetime.now(timezone.utc) - timedelta(days=30)
    activity: dict[str, dict[str, int]] = {}
    rows = db.execute(
        select(AuditLog.created_at, AuditLog.action).where(AuditLog.action.in_(ACTIVITY), AuditLog.success, AuditLog.created_at >= since)
    )
    for created_at, action in rows:
        day = activity.setdefault(created_at.date().isoformat(), {"added": 0, "removed": 0})
        day["added" if action == "access.plate_assigned" else "removed"] += 1

    return {
        "vehicles": len(managed),
        "departments": grouped(Vehicle.department),
        "locations": grouped(Vehicle.location),
        "groups": grouped(Vehicle.group_name),
        "sources": grouped(Vehicle.source),
        "consoles": consoles,
        "activity": [{"day": d, **v} for d, v in sorted(activity.items())],
        "totals_30d": {
            "added": sum(d["added"] for d in activity.values()),
            "removed": sum(d["removed"] for d in activity.values()),
        },
    }
