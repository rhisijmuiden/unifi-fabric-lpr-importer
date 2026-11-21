"""First-run setup in the web interface, and the web address / HTTPS settings.

The installer only creates the first admin account. On the first sign-in that admin goes
through the setup: own password, web address and HTTPS, release channel, restore or start fresh.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, require_admin
from ..models import User
from ..security import SESSION_COOKIE, hash_password, revoke_sessions, session_id
from ..services import updater, webconfig
from ..settings_store import get_section, update_section

router = APIRouter(tags=["setup"])


class WebIn(BaseModel):
    mode: str = Field(pattern="^(http|selfsigned|own|keep)$")
    host: str = Field(default="", max_length=253)
    cert_pem: str = Field(default="", max_length=200_000)
    key_pem: str = Field(default="", max_length=200_000)


class SetupAccountIn(BaseModel):
    new_password: str = Field(min_length=10)
    email: str = Field(default="", max_length=255)
    language: str = Field(default="en", pattern="^(en|nl)$")


class SetupCompleteIn(BaseModel):
    web: WebIn | None = None
    channel: str = Field(default="", pattern="^(|main|test)$")


def _pending(db: Session) -> bool:
    return bool(get_section(db, "setup")["pending"])


def _require_pending(db: Session) -> None:
    if not _pending(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "setup_done")


@router.get("/api/setup/status")
def setup_status(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    pending = _pending(db) and user.role == "admin"
    out: dict = {"pending": pending}
    if pending:
        out["web"] = webconfig.info()
        out["channel"] = updater.local_info().get("channel")
    return out


@router.put("/api/setup/account", status_code=204)
def setup_account(body: SetupAccountIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> None:
    """Replace the installer's generated password; no current password needed during the setup."""
    _require_pending(db)
    if admin.auth_source != "local":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_local")
    admin.password_hash = hash_password(body.new_password)
    if body.email:
        if "@" not in body.email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_email")
        admin.email = body.email.strip()
    admin.language = body.language
    db.commit()
    revoke_sessions(db, admin.id, keep=session_id(request.cookies.get(SESSION_COOKIE)))
    audit.record(db, "user.password_changed", user=admin, target=admin.username, details={"setup": True}, request=request)


@router.post("/api/setup/complete")
def setup_complete(body: SetupCompleteIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    _require_pending(db)
    web = body.web or WebIn(mode="keep")
    current_channel = updater.local_info().get("channel")
    channel = body.channel if body.channel and body.channel != current_channel else ""
    # Check everything before the setup is marked done.
    try:
        if web.host:
            webconfig.validate_host(web.host)
        if web.mode == "own":
            webconfig.validate_certificate(web.cert_pem, web.key_pem)
    except webconfig.WebConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    update_section(db, "setup", {"pending": False, "completed_at": datetime.now(timezone.utc).isoformat(), "completed_by": admin.username})
    applied = True
    message = ""
    try:
        # Also without changes: this removes the first password from the server console.
        webconfig.request_change(mode=web.mode, host=web.host, cert_pem=web.cert_pem, key_pem=web.key_pem, finish_setup=True, channel=channel)
    except webconfig.WebConfigError as exc:
        applied = False
        message = str(exc)
    audit.record(
        db, "system.setup_completed", user=admin, request=request, success=applied, message=message,
        details={"mode": web.mode, "host": web.host, "channel": channel or current_channel},
    )
    return {
        "applied": applied,
        "message": message,
        "restart": applied and (web.mode != "keep" or bool(web.host)),
        "base_url": webconfig.new_base_url(web.mode, web.host),
        "channel_switch": bool(channel) and applied,
    }


@router.get("/api/system/web")
def get_web(_: User = Depends(require_admin)) -> dict:
    return webconfig.info()


@router.put("/api/system/web", status_code=202)
def put_web(body: WebIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    try:
        webconfig.request_change(mode=body.mode, host=body.host, cert_pem=body.cert_pem, key_pem=body.key_pem)
    except webconfig.WebConfigError as exc:
        audit.record(db, "system.web_changed", user=admin, request=request, success=False, message=str(exc), details={"mode": body.mode, "host": body.host})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    audit.record(db, "system.web_changed", user=admin, request=request, details={"mode": body.mode, "host": body.host})
    return {"status": "started", "base_url": webconfig.new_base_url(body.mode, body.host)}


@router.get("/api/system/web-status")
def web_status(_: User = Depends(require_admin)) -> dict:
    return webconfig.read_status()
