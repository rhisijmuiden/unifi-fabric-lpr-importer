"""REST API for external systems such as Lobster. See docs/api.md.

Authentication: `Authorization: Bearer lpr_...` (API keys are created under
Administration > API keys). Every change is audited with the key's name.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import api_actor, api_key
from ..models import ApiKey, Console, Job, Vehicle
from ..schemas import ApiConsoleOut, ApiJobAccepted, ApiJobOut, ApiStatusOut, ApiVehicleOut, ApiVehiclesIn
from ..services import jobs, sync, updater
from ..services.plates import plate_key
from ..services.vehicles import plan_import, run_import
from .vehicles import presence_map

router = APIRouter(prefix="/api/v1", tags=["external API (v1)"])

# A retry with the same Idempotency-Key within this window returns the original job.
IDEMPOTENCY_WINDOW = timedelta(hours=24)

ERRORS = {
    401: {"description": "`invalid_api_key`: key missing, wrong or disabled"},
    403: {"description": "`ip_not_allowed` or `delete_not_allowed`"},
    429: {"description": "`too_many_requests`: rate limit of the key reached, or too many wrong keys from this address. Wait the number of seconds in the `Retry-After` header."},
}


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


def _accepted(job: Job, replayed: bool = False) -> dict:
    return {"job_id": job.id, "status": job.status, "status_url": f"/api/v1/jobs/{job.id}", "replayed": replayed}


def _replay(db: Session, key: ApiKey, idempotency_key: str | None) -> Job | None:
    if not idempotency_key:
        return None
    since = datetime.now(timezone.utc) - IDEMPOTENCY_WINDOW
    jobs_ = db.scalars(
        select(Job).where(Job.idempotency_key == idempotency_key, Job.actor_type == "api_key", Job.actor == key.name).order_by(Job.id.desc())
    )
    for job in jobs_:
        created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)
        if created >= since:
            return job
    return None


def _vehicle_out(v: Vehicle, consoles: list[str]) -> dict:
    return {
        "plate": v.plate,
        "department": v.department,
        "location": v.location,
        "group": v.group_name,
        "description": v.description,
        "source": v.source,
        "consoles": consoles,
        "updated_at": v.updated_at,
    }


@router.get("/status", response_model=ApiStatusOut, responses=ERRORS)
def api_status(db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    """Connection test: checks the key and returns its rights and the application version."""
    consoles = len(list(db.scalars(select(Console.id).where(Console.is_active))))
    return {"status": "ok", "version": updater.local_info()["version"], "key": key.name, "allow_delete": key.allow_delete, "consoles": consoles}


@router.get("/consoles", response_model=list[ApiConsoleOut], responses=ERRORS)
def consoles(db: Session = Depends(get_db), _: ApiKey = Depends(api_key)) -> list[dict]:
    """Active consoles that vehicles can be registered on."""
    return [{"id": c.id, "name": c.name, "location": c.location} for c in db.scalars(select(Console).where(Console.is_active).order_by(Console.sort_order, Console.name))]


@router.get("/vehicles", response_model=list[ApiVehicleOut], responses=ERRORS)
def list_vehicles(department: str | None = None, location: str | None = None, db: Session = Depends(get_db), _: ApiKey = Depends(api_key)) -> list[dict]:
    """All vehicles with the consoles they are present on, optionally filtered by department and location."""
    presence = presence_map(db)
    names = {c.id: c.name for c in db.scalars(select(Console))}
    query = select(Vehicle).order_by(Vehicle.plate)
    if department:
        query = query.where(Vehicle.department == department)
    if location:
        query = query.where(Vehicle.location == location)
    return [_vehicle_out(v, sorted(names[cid] for cid in presence.get(v.plate_key, {}) if cid in names)) for v in db.scalars(query)]


@router.get("/vehicles/{plate}", response_model=ApiVehicleOut, responses={**ERRORS, 404: {"description": "`not_found`"}})
def get_vehicle(plate: str, db: Session = Depends(get_db), _: ApiKey = Depends(api_key)) -> dict:
    """One vehicle, by plate in any notation."""
    k = plate_key(plate)
    vehicle = db.scalar(select(Vehicle).where(Vehicle.plate_key == k))
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    names = {c.id: c.name for c in db.scalars(select(Console))}
    return _vehicle_out(vehicle, sorted(names[cid] for cid in presence_map(db).get(k, {}) if cid in names))


@router.post(
    "/vehicles",
    status_code=202,
    response_model=ApiJobAccepted,
    responses={**ERRORS, 200: {"description": "Dry run: the plan, nothing changed. Or a replay of an earlier request with the same Idempotency-Key."}, 400: {"description": "`unknown_console:<name>`"}},
)
def push_vehicles(
    body: ApiVehiclesIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(api_key),
    idempotency_key: str | None = Header(default=None, max_length=100, description="Any unique value per delivery, e.g. a UUID. A retry with the same value within 24 hours returns the original job instead of starting a new one."),
) -> dict:
    """Add or update vehicles and register them on the consoles. With dry_run only the plan is returned."""
    if body.mode == "full" and not key.allow_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "delete_not_allowed")
    console_ids = _console_ids(db, body.consoles)
    rows = [r.model_dump() for r in body.vehicles]
    if body.dry_run:
        plan = plan_import(db, rows, console_ids, body.mode)
        invalid = [{"row": r["row"], "plate": r["plate"], "error": r["error"]} for r in plan["rows"] if r["error"]]
        return JSONResponse(jsonable_encoder({"dry_run": True, "summary": plan["summary"], "consoles": plan["consoles"], "remove": plan["remove"], "invalid": invalid}))
    previous = _replay(db, key, idempotency_key)
    if previous is not None:
        response.status_code = 200
        return _accepted(previous, replayed=True)
    actor = api_actor(key, request)
    params = {"rows": len(rows), "console_ids": console_ids, "mode": body.mode, "source": "api"}
    audit.record(db, "import.started", details=params, **actor.audit())
    job = jobs.start(db, "import", actor, params, lambda ctx: run_import(ctx, rows, "api", console_ids, body.mode), idempotency_key=idempotency_key)
    return _accepted(job)


@router.delete("/vehicles/{plate}", status_code=202, response_model=ApiJobAccepted, responses={**ERRORS, 404: {"description": "`not_found`"}})
def delete_vehicle(plate: str, request: Request, db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    """Remove the plate from every console and delete the vehicle from the app."""
    if not key.allow_delete:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "delete_not_allowed")
    k = plate_key(plate)
    if db.scalar(select(Vehicle).where(Vehicle.plate_key == k)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    job = jobs.start(db, "remove", api_actor(key, request), {"plate": plate, "source": "api"}, lambda ctx: sync.remove(ctx, [k], None, delete_vehicles=True))
    return _accepted(job)


@router.get("/jobs/{job_id}", response_model=ApiJobOut, responses={**ERRORS, 404: {"description": "`not_found`"}})
def get_job(job_id: int, db: Session = Depends(get_db), key: ApiKey = Depends(api_key)) -> dict:
    """Progress and report of a job started with this key."""
    job = db.get(Job, job_id)
    # A key only sees its own jobs.
    if job is None or job.actor_type != "api_key" or job.actor != key.name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return jobs.to_dict(job)



def v1_openapi(app) -> dict:
    """The OpenAPI document of /api/v1 only, for the supplier (docs/openapi-v1.json)."""
    full = app.openapi()
    paths = {p: ops for p, ops in full["paths"].items() if p.startswith("/api/v1/")}
    schemas = full.get("components", {}).get("schemas", {})
    wanted: set[str] = set()

    def collect(node) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in wanted:
                    wanted.add(name)
                    collect(schemas.get(name))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(paths)
    return {
        "openapi": full["openapi"],
        "info": {
            "title": "UniFi Fabric License Plate Importer: vehicle delivery API",
            "version": "1",
            "description": "REST API for systems such as Lobster that deliver company vehicles. Guide: docs/api.md (EN), docs/api.nl.md (NL).",
        },
        "components": {
            "schemas": {name: schemas[name] for name in sorted(wanted)},
            "securitySchemes": {"apiKey": {"type": "http", "scheme": "bearer", "description": "API key `lpr_...` from Administration > API keys"}},
        },
        "security": [{"apiKey": []}],
        "paths": paths,
    }
