from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, require_operator, user_actor
from ..models import Console, ConsolePlate, User, Vehicle
from ..schemas import AdoptIn, VehicleBulk, VehicleBulkEdit, VehicleIn, VehicleRemove, VehicleUpdate
from ..services import jobs, sync
from ..services.plates import format_plate, group_name, is_valid_plate, plate_key
from ..services.vehicles import upsert

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def presence_map(db: Session) -> dict[str, dict[int, dict]]:
    """plate_key -> console id -> what the console holds for it."""
    result: dict[str, dict[int, dict]] = {}
    for row in db.scalars(select(ConsolePlate)):
        result.setdefault(row.plate_key, {})[row.console_id] = {
            "user": f"{row.first_name} {row.last_name}".strip(),
            "groups": row.groups,
            "seen_at": row.seen_at.isoformat() if row.seen_at else None,
        }
    return result


def vehicle_dict(v: Vehicle, presence: dict[int, dict]) -> dict:
    return {
        "id": v.id,
        "plate": v.plate,
        "plate_key": v.plate_key,
        "department": v.department,
        "location": v.location,
        "group_name": v.group_name,
        "description": v.description,
        "source": v.source,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        "presence": {str(cid): info for cid, info in presence.items()},
    }


@router.get("")
def list_vehicles(
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
    q: str = "",
    department: str = "",
    location: str = "",
    group: str = "",
) -> dict:
    stmt = select(Vehicle).order_by(Vehicle.group_name, Vehicle.plate)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Vehicle.plate.ilike(like), Vehicle.plate_key.ilike(f"%{plate_key(q)}%"), Vehicle.description.ilike(like), Vehicle.group_name.ilike(like)))
    if department:
        stmt = stmt.where(Vehicle.department == department)
    if location:
        stmt = stmt.where(Vehicle.location == location)
    if group:
        stmt = stmt.where(Vehicle.group_name == group)
    presence = presence_map(db)
    consoles = db.scalars(select(Console).order_by(Console.sort_order, Console.name))
    return {
        "consoles": [{"id": c.id, "name": c.name, "location": c.location, "is_active": c.is_active, "last_scan_at": c.last_scan_at} for c in consoles],
        "items": [vehicle_dict(v, presence.get(v.plate_key, {})) for v in db.scalars(stmt)],
    }


@router.get("/filters")
def filters(db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    def distinct(col):
        return [v for v in db.scalars(select(col).distinct().order_by(col)) if v]

    return {"departments": distinct(Vehicle.department), "locations": distinct(Vehicle.location), "groups": distinct(Vehicle.group_name)}


@router.post("", status_code=201)
def create_vehicle(body: VehicleIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    if not is_valid_plate(body.plate):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_plate")
    if db.scalar(select(Vehicle).where(Vehicle.plate_key == plate_key(body.plate))):
        raise HTTPException(status.HTTP_409_CONFLICT, "plate_exists")
    row = {**body.model_dump(), "plate": format_plate(body.plate), "plate_key": plate_key(body.plate)}
    row["group_name"] = row["group_name"].strip() or group_name(body.department, body.location)
    [vid] = upsert(db, [row], "manual", user_actor(user, request))
    return vehicle_dict(db.get(Vehicle, vid), {})


def _edit(db: Session, vehicle: Vehicle, changes: dict, user: User, request: Request) -> None:
    changes = {k: v.strip() for k, v in changes.items() if v is not None}
    regroup = ("department" in changes or "location" in changes) and "group_name" not in changes
    for field, value in changes.items():
        setattr(vehicle, field, value)
    if regroup:
        changes["group_name"] = vehicle.group_name = group_name(vehicle.department, vehicle.location)
    if changes:
        audit.record(db, "vehicle.updated", user=user, target=vehicle.plate, details=changes, request=request, commit=False)


@router.patch("/{vehicle_id}")
def update_vehicle(vehicle_id: int, body: VehicleUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    _edit(db, vehicle, body.model_dump(exclude_unset=True), user, request)
    db.commit()
    return vehicle_dict(vehicle, presence_map(db).get(vehicle.plate_key, {}))


@router.post("/bulk-edit")
def bulk_edit(body: VehicleBulkEdit, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    """Set department, location or group for many vehicles at once (e.g. all of one location)."""
    changes = body.model_dump(exclude={"vehicle_ids"}, exclude_unset=True)
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.id.in_(body.vehicle_ids))))
    for vehicle in vehicles:
        _edit(db, vehicle, dict(changes), user, request)
    db.commit()
    return {"updated": len(vehicles)}


@router.post("/assign", status_code=202)
def assign(body: VehicleBulk, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    """Register vehicles on consoles per the naming convention (user, plate and group)."""
    job = jobs.start(db, "assign", user_actor(user, request), body.model_dump(), lambda ctx: sync.assign(ctx, body.vehicle_ids, body.console_ids))
    return jobs.to_dict(job, with_log=False)


@router.post("/remove", status_code=202)
def remove(body: VehicleRemove, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    """Remove the plates from consoles; optionally delete the vehicles from the app too."""
    keys = list(db.scalars(select(Vehicle.plate_key).where(Vehicle.id.in_(body.vehicle_ids))))
    job = jobs.start(db, "remove", user_actor(user, request), body.model_dump(), lambda ctx: sync.remove(ctx, keys, body.console_ids, body.delete_vehicles))
    return jobs.to_dict(job, with_log=False)


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> None:
    """Delete from this app only. Use /remove to take the plate off the consoles."""
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    db.delete(vehicle)
    db.commit()
    audit.record(db, "vehicle.deleted", user=user, target=vehicle.plate, request=request)


@router.get("/adopt")
def adopt_candidates(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    """Plates found on the consoles that this app does not manage yet."""
    return sync.adopt_candidates(db)


@router.post("/adopt")
def adopt(body: AdoptIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    rows = []
    for item in body.items:
        if not is_valid_plate(item.plate):
            continue
        rows.append({
            "plate": format_plate(item.plate),
            "plate_key": plate_key(item.plate),
            "department": item.department.strip(),
            "location": item.location.strip(),
            "group_name": item.group_name.strip() or group_name(item.department, item.location),
            "description": item.description.strip(),
        })
    ids = upsert(db, rows, "console", user_actor(user, request))
    return {"adopted": len(ids)}
