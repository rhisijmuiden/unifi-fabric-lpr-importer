import platform
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, require_admin
from ..models import User
from ..schemas import UpdateIn
from ..services import updater

router = APIRouter(prefix="/api/system", tags=["system"])

_STARTED = time.time()


@router.get("/info")
def info(_: User = Depends(current_user)) -> dict:
    return {
        **updater.local_info(),
        "channels": updater.CHANNELS,
        "python": platform.python_version(),
        "uptime_seconds": int(time.time() - _STARTED),
    }


@router.post("/check-updates")
def check_updates(_: User = Depends(require_admin)) -> dict:
    try:
        return updater.check_for_updates()
    except updater.UpdateError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/update", status_code=202)
def start_update(body: UpdateIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    current = updater.local_info().get("channel")
    action = "system.update" if body.channel == current else "system.switch_channel"
    try:
        updater.request_update(body.channel, admin.username)
    except updater.UpdateError as exc:
        audit.record(db, action, user=admin, target=body.channel, request=request, success=False, message=str(exc))
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit.record(db, action, user=admin, target=body.channel, details={"from": current}, request=request)
    return {"status": "started"}


@router.get("/update-status")
def update_status(_: User = Depends(require_admin)) -> dict:
    return updater.read_status()
