import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_admin
from ..models import ApiKey, User
from ..schemas import AccessSettingsIn, ApiKeyIn, ApiKeyOut, ApiKeyUpdate
from ..security import new_api_key
from ..settings_store import get_section, update_section

router = APIRouter(prefix="/api", tags=["api keys"])


def _networks(values: list[str]) -> list[str]:
    """Normalise IP addresses and networks, e.g. `10.0.0.1/8` becomes `10.0.0.0/8`."""
    cleaned = []
    for value in (v.strip() for v in values):
        if not value:
            continue
        try:
            cleaned.append(str(ipaddress.ip_network(value, strict=False)))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid_network:{value}") from exc
    return cleaned


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_keys(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[ApiKey]:
    return list(db.scalars(select(ApiKey).order_by(ApiKey.name)))


@router.post("/api-keys", status_code=201)
def create_key(body: ApiKeyIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    """The key itself is returned once; only its hash is stored."""
    if db.scalar(select(ApiKey).where(ApiKey.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    key, prefix, key_hash = new_api_key()
    row = ApiKey(name=body.name.strip(), prefix=prefix, key_hash=key_hash, allow_delete=body.allow_delete, allowed_ips=_networks(body.allowed_ips), created_by=admin.username)
    db.add(row)
    db.commit()
    audit.record(db, "api_key.created", user=admin, target=row.name, details={"allow_delete": row.allow_delete, "allowed_ips": row.allowed_ips}, request=request)
    return {**ApiKeyOut.model_validate(row).model_dump(mode="json"), "key": key}


@router.patch("/api-keys/{key_id}", response_model=ApiKeyOut)
def update_key(key_id: int, body: ApiKeyUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> ApiKey:
    row = db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("allowed_ips") is not None:
        changes["allowed_ips"] = _networks(changes["allowed_ips"])
    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    audit.record(db, "api_key.updated", user=admin, target=row.name, details=changes, request=request)
    return row


@router.delete("/api-keys/{key_id}", status_code=204)
def delete_key(key_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> None:
    row = db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    db.delete(row)
    db.commit()
    audit.record(db, "api_key.deleted", user=admin, target=row.name, request=request)


@router.get("/settings/access")
def get_access(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return get_section(db, "access")


@router.put("/settings/access")
def put_access(body: AccessSettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    update_section(db, "access", body.model_dump())
    audit.record(db, "settings.access_updated", user=admin, details=body.model_dump(), request=request)
    return get_section(db, "access")
