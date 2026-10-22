import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, require_admin, require_operator, user_actor
from ..models import Console, ConsolePlate, User
from ..schemas import ConsoleIds, ConsoleIn, ConsoleTestIn
from ..security import decrypt, encrypt
from ..services import jobs, sync
from ..services.access import AccessError, client_for

router = APIRouter(prefix="/api/consoles", tags=["consoles"])


def clean_host(value: str) -> str:
    """Accept a pasted URL such as https://10.0.0.1:12445/ and keep only the host."""
    host = re.sub(r"^[a-z]+://", "", value.strip(), flags=re.I).split("/")[0]
    if host.startswith("["):  # IPv6 literal
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def to_dict(db: Session, console: Console) -> dict:
    plates = db.scalar(select(func.count()).select_from(ConsolePlate).where(ConsolePlate.console_id == console.id)) or 0
    return {
        "id": console.id,
        "name": console.name,
        "location": console.location,
        "host": console.host,
        "port": console.port,
        "verify_tls": console.verify_tls,
        "is_active": console.is_active,
        "sort_order": console.sort_order,
        "api_token_set": bool(console.api_token),
        "last_test_at": console.last_test_at,
        "last_test_ok": console.last_test_ok,
        "last_test_message": console.last_test_message,
        "last_scan_at": console.last_scan_at,
        "plates": plates,
    }


def _probe(console: Console, token: str) -> dict:
    try:
        with client_for(console, token) as client:
            return {"ok": True, **client.probe()}
    except AccessError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}


@router.get("")
def list_consoles(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    return [to_dict(db, c) for c in db.scalars(select(Console).order_by(Console.sort_order, Console.name))]


def _apply(console: Console, body: ConsoleIn) -> None:
    console.name = body.name.strip()
    console.location = body.location.strip()
    console.host = clean_host(body.host)
    console.port = body.port
    console.verify_tls = body.verify_tls
    console.is_active = body.is_active
    console.sort_order = body.sort_order
    if body.api_token is not None:
        console.api_token = encrypt(body.api_token.strip()) if body.api_token.strip() else ""


@router.post("", status_code=201)
def create_console(body: ConsoleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    if db.scalar(select(Console).where(Console.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    if not (body.api_token or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token_required")
    console = Console()
    _apply(console, body)
    db.add(console)
    db.commit()
    audit.record(db, "console.created", user=admin, target=console.name, details={"host": console.host, "location": console.location}, request=request)
    return to_dict(db, console)


@router.put("/{console_id}")
def update_console(console_id: int, body: ConsoleIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    console = db.get(Console, console_id)
    if console is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    other = db.scalar(select(Console).where(Console.name == body.name.strip(), Console.id != console_id))
    if other:
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken")
    _apply(console, body)
    db.commit()
    details = {"host": console.host, "location": console.location, "active": console.is_active, "token_changed": body.api_token is not None}
    audit.record(db, "console.updated", user=admin, target=console.name, details=details, request=request)
    return to_dict(db, console)


@router.delete("/{console_id}", status_code=204)
def delete_console(console_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> None:
    """Removes the console from this app only; nothing changes on the console itself."""
    console = db.get(Console, console_id)
    if console is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    db.delete(console)
    db.commit()
    audit.record(db, "console.deleted", user=admin, target=console.name, request=request)


@router.post("/test")
def test_connection(body: ConsoleTestIn, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    """Test address and token before saving. Without a token the stored token of console_id is used."""
    token = (body.api_token or "").strip()
    if not token and body.console_id:
        stored = db.get(Console, body.console_id)
        token = decrypt(stored.api_token) or "" if stored and stored.api_token else ""
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token_required")
    probe = Console(host=clean_host(body.host), port=body.port, verify_tls=body.verify_tls)
    return _probe(probe, token)


@router.post("/{console_id}/test")
def test_console(console_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    console = db.get(Console, console_id)
    if console is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    result = _probe(console, decrypt(console.api_token) or "")
    console.last_test_at = datetime.now(timezone.utc)
    console.last_test_ok = result["ok"]
    console.last_test_message = "" if result["ok"] else result["message"]
    db.commit()
    audit.record(db, "console.tested", user=user, target=console.name, success=result["ok"], message=console.last_test_message, request=request)
    return result


@router.post("/scan", status_code=202)
def scan(body: ConsoleIds, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    """Read all users and plates from the consoles (all active ones when no ids are given)."""
    job = jobs.start(db, "scan", user_actor(user, request), body.model_dump(), lambda ctx: sync.scan(ctx, body.console_ids))
    return jobs.to_dict(job, with_log=False)
