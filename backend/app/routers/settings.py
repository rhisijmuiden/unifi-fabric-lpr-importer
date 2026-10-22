import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import NotificationSettingsIn, SmtpSettingsIn, SsoSettingsIn, TestMailIn
from ..services import entra, notify
from ..services.mailer import MailError, send_mail
from ..settings_store import get_section, public_section, update_section

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/sso")
def get_sso(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return {**public_section(db, "sso"), "redirect_uri": entra.redirect_uri()}


@router.put("/sso")
def put_sso(body: SsoSettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    data = body.model_dump()
    if data["enabled"]:
        merged = {**get_section(db, "sso"), **{k: v for k, v in data.items() if v is not None}}
        missing = [f for f in ("tenant_id", "client_id", "client_secret") if not merged.get(f)]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"missing_fields:{','.join(missing)}")
        if not any(merged.get(f"{r}_group_id") for r in ("admin", "operator", "viewer")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing_group_mapping")
    update_section(db, "sso", data)
    audit.record(db, "settings.sso_updated", user=admin, details={"enabled": data["enabled"]}, request=request)
    return get_sso(db, admin)


@router.get("/smtp")
def get_smtp(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return public_section(db, "smtp")


@router.put("/smtp")
def put_smtp(body: SmtpSettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    update_section(db, "smtp", body.model_dump())
    audit.record(db, "settings.smtp_updated", user=admin, details={"host": body.host}, request=request)
    return public_section(db, "smtp")


@router.post("/smtp/test")
async def test_smtp(body: TestMailIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    cfg = get_section(db, "smtp")
    try:
        await send_mail(
            cfg,
            body.to,
            "Test message from UniFi Fabric License Plate Importer",
            "This is a test message. Your mail server settings work.\n\n"
            "Dit is een testbericht. Je mailserverinstellingen werken.",
        )
    except MailError as exc:
        audit.record(db, "settings.smtp_test", user=admin, target=body.to, request=request, success=False, message=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    audit.record(db, "settings.smtp_test", user=admin, target=body.to, request=request)
    return {"status": "sent"}


@router.get("/notifications")
def get_notifications(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return get_section(db, "notifications")


@router.put("/notifications")
def put_notifications(body: NotificationSettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    data = body.model_dump()
    bad = [r for r in notify.recipients(data) if "@" not in r]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid_address:{bad[0]}")
    update_section(db, "notifications", data)
    audit.record(db, "settings.notifications_updated", user=admin, details=data, request=request)
    return get_section(db, "notifications")


@router.post("/notifications/test")
def test_notifications(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    if not notify.recipients(get_section(db, "notifications")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_recipients")
    cfg = get_section(db, "smtp")
    to = ", ".join(notify.recipients(get_section(db, "notifications")))
    try:
        asyncio.run(send_mail(cfg, to, f"Test notification - {notify.APP}", "Notifications from this application reach you.\n\nMeldingen van deze applicatie komen bij je aan.\n"))
    except MailError as exc:
        audit.record(db, "settings.notifications_test", user=admin, target=to, request=request, success=False, message=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    audit.record(db, "settings.notifications_test", user=admin, target=to, request=request)
    return {"status": "sent", "to": to}
