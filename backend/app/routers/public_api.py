"""REST API for external systems such as Lobster. See docs/api.md.

Authentication: `Authorization: Bearer lpr_...` (API keys are created under
Administration > API keys). Every change is audited with the key's name.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import api_actor, api_key
from ..models import ApiKey, Console, Job, Vehicle
from ..schemas import ApiVehiclesIn
from ..services import jobs, sync
from ..services.plates import plate_key
from ..services.vehicles import plan_import, run_import
from .vehicles import presence_map

router = APIRouter(prefix="/api/v1", tags=["external API (v1)"])


def _console_ids(db: Session, wanted: list[int | str] | None) -> list[int]:
    active = list(db.scalars(select(Console).where(Console.is_active)))
    if wanted is None:
        return [c.id for c in active]
    ids = []
    for value in wanted:
        match = next((c for c in active if c.id == value or c.name == value), None)
        if match is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown_console:{value}")
        ids.append(match.id)
    return ids


@router.get("/consoles")
def consoles(db: Session = Depends(get_db), _: ApiKey = Depends(api_key)) -> list[dict]:
    return [{"id": c.id, "name": c.name, "location": c.location} for c in db.scalars(select(Console).where(Console.is_active).order_by(Console.sort_order, Console.name))]


@router.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), _: ApiKey = Depends(api_key)) -> list[dict]:
    presence = presence_map(db)
    names = {c.id: c.name for c in db.scalars(select(Console))}
    return [
        {
            "plate": v.plate,
            "department": v.department,
            "location": v.location,
            "group": v.group_name,
            "description": v.description,
            "consoles": sorted(names[cid] for cid in presence.get(v.plate_key, {}) if cid in names),
        }
        for v in db.scalars(select(Vehicle).order_by(Vehicle.plate))
    ]


@router.post("/vehicles", status_code=202)
def push_vehicles(body: ApiVehiclesIn, request: Request, db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    """Add or update vehicles and register them on the consoles. With dry_run only the plan is returned."""
    if body.mode == "full" and not key.allow_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "delete_not_allowed")
    console_ids = _console_ids(db, body.consoles)
    rows = [r.model_dump() for r in body.vehicles]
    if body.dry_run:
        plan = plan_import(db, rows, console_ids, body.mode)
        return {"dry_run": True, "summary": plan["summary"], "consoles": plan["consoles"], "remove": plan["remove"],
                "invalid": [{"row": r["row"], "plate": r["plate"], "error": r["error"]} for r in plan["rows"] if r["error"]]}
    actor = api_actor(key, request)
    params = {"rows": len(rows), "console_ids": console_ids, "mode": body.mode, "source": "api"}
    audit.record(db, "import.started", details=params, **actor.audit())
    job = jobs.start(db, "import", actor, params, lambda ctx: run_import(ctx, rows, "api", console_ids, body.mode))
    return {"job_id": job.id, "status": job.status, "status_url": f"/api/v1/jobs/{job.id}"}


@router.delete("/vehicles/{plate}", status_code=202)
def delete_vehicle(plate: str, request: Request, db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    """Remove the plate from every console and delete the vehicle from the app."""
    if not key.allow_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "delete_not_allowed")
    k = plate_key(plate)
    if db.scalar(select(Vehicle).where(Vehicle.plate_key == k)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    job = jobs.start(db, "remove", api_actor(key, request), {"plate": plate}, lambda ctx: sync.remove(ctx, [k], None, delete_vehicles=True))
    return {"job_id": job.id, "status": job.status, "status_url": f"/api/v1/jobs/{job.id}"}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    job = db.get(Job, job_id)
    # A key only sees its own jobs.
    if job is None or job.actor_type != "api_key" or job.actor != key.name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return jobs.to_dict(job)
