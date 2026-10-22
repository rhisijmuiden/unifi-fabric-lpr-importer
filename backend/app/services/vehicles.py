"""Vehicle records: validation, upsert and the shared import path.

The CSV wizard and the REST API (Lobster) both end up in `plan_import` and
`run_import`, so they convert and register vehicles the same way.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..models import Console, ConsolePlate, Vehicle
from . import sync
from .jobs import Actor, JobContext
from .plates import format_plate, group_name, is_valid_plate, plate_key

FIELDS = ("plate", "department", "location", "group_name", "description")


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Clean one incoming vehicle. Only plate and department are required."""
    plate = format_plate(str(raw.get("plate") or ""))
    department = " ".join(str(raw.get("department") or "").split())
    location = " ".join(str(raw.get("location") or "").split())
    row = {
        "plate": plate,
        "plate_key": plate_key(plate),
        "department": department,
        "location": location,
        "group_name": " ".join(str(raw.get("group_name") or "").split()) or group_name(department, location),
        "description": str(raw.get("description") or "").strip()[:255],
        "error": None,
    }
    if not is_valid_plate(plate):
        row["error"] = "invalid_plate"
    elif not department:
        row["error"] = "missing_department"
    return row


def _changed(vehicle: Vehicle, row: dict[str, Any]) -> dict[str, Any]:
    # An empty description in the source keeps the one entered in the app.
    fields = [f for f in FIELDS if f != "description" or row[f]]
    return {f: row[f] for f in fields if getattr(vehicle, f) != row[f]}


def plan_import(db: Session, raw_rows: list[dict[str, Any]], console_ids: list[int], mode: str = "upsert") -> dict[str, Any]:
    """Dry run: what an import would change, based on the last console scan."""
    existing = {v.plate_key: v for v in db.scalars(select(Vehicle))}
    seen: set[str] = set()
    rows = []
    for index, raw in enumerate(raw_rows):
        row = normalize(raw)
        row["row"] = index + 1
        if row["error"] is None and row["plate_key"] in seen:
            row["error"] = "duplicate"
        if row["error"]:
            row["status"] = "invalid"
        else:
            seen.add(row["plate_key"])
            vehicle = existing.get(row["plate_key"])
            row["status"] = "new" if vehicle is None else ("changed" if _changed(vehicle, row) else "unchanged")
        rows.append(row)

    valid = [r for r in rows if r["status"] != "invalid"]
    missing = _missing(existing.values(), valid) if mode == "full" else []
    consoles = []
    for console in db.scalars(select(Console).where(Console.is_active).order_by(Console.sort_order, Console.name)):
        present = set(db.scalars(select(ConsolePlate.plate_key).where(ConsolePlate.console_id == console.id)))
        consoles.append({
            "id": console.id,
            "name": console.name,
            "add": sum(1 for r in valid if r["plate_key"] not in present),
            "present": sum(1 for r in valid if r["plate_key"] in present),
            "selected": console.id in console_ids,
            "remove": sum(1 for v in missing if v.plate_key in present),
            "scanned_at": console.last_scan_at.isoformat() if console.last_scan_at else None,
        })
    groups = sorted({r["group_name"] for r in valid if r["group_name"]})
    return {
        "rows": rows,
        "summary": {
            "total": len(rows),
            "new": sum(r["status"] == "new" for r in rows),
            "changed": sum(r["status"] == "changed" for r in rows),
            "unchanged": sum(r["status"] == "unchanged" for r in rows),
            "invalid": sum(r["status"] == "invalid" for r in rows),
            "remove": len(missing),
            "groups": groups,
        },
        "remove": [v.plate for v in missing],
        "consoles": consoles,
    }


def _missing(vehicles: Any, valid: list[dict[str, Any]]) -> list[Vehicle]:
    """Full sync removes vehicles of the departments in the source that the source no longer lists."""
    keys = {r["plate_key"] for r in valid}
    departments = {r["department"] for r in valid}
    return [v for v in vehicles if v.department in departments and v.plate_key not in keys]


def upsert(db: Session, rows: list[dict[str, Any]], source: str, actor: Actor) -> list[int]:
    existing = {v.plate_key: v for v in db.scalars(select(Vehicle))}
    ids = []
    for row in rows:
        vehicle = existing.get(row["plate_key"])
        values = {f: row[f] for f in FIELDS}
        if vehicle is None:
            vehicle = Vehicle(plate_key=row["plate_key"], source=source, **values)
            db.add(vehicle)
            db.flush()
            existing[vehicle.plate_key] = vehicle
            audit.record(db, "vehicle.created", target=vehicle.plate, details={k: values[k] for k in ("department", "location", "group_name")}, commit=False, **actor.audit())
        else:
            changes = _changed(vehicle, row)
            if changes:
                for field, value in changes.items():
                    setattr(vehicle, field, value)
                audit.record(db, "vehicle.updated", target=vehicle.plate, details=changes, commit=False, **actor.audit())
        ids.append(vehicle.id)
    db.commit()
    return ids


def run_import(ctx: JobContext, rows: list[dict[str, Any]], source: str, console_ids: list[int], mode: str) -> dict[str, Any]:
    """Job body: store the vehicles, register them on the chosen consoles, and in full
    mode remove the missing ones from the app and from every console."""
    db = ctx.db
    valid = [r for r in (normalize(raw) for raw in rows) if r["error"] is None]
    unique: dict[str, dict[str, Any]] = {}
    for row in valid:  # the first row of a plate wins, like in the preview
        unique.setdefault(row["plate_key"], row)
    unique = list(unique.values())
    missing = [v.plate_key for v in _missing(db.scalars(select(Vehicle)), unique)] if mode == "full" else []
    ids = upsert(db, unique, source, ctx.actor)
    ctx.note(f"{len(ids)} vehicles stored")
    result: dict[str, Any] = {"vehicles": len(ids), "skipped": len(rows) - len(unique)}
    if console_ids:
        result["assign"] = sync.assign(ctx, ids, console_ids)
    if missing:
        result["remove"] = sync.remove(ctx, missing, None, delete_vehicles=True)
    return result
