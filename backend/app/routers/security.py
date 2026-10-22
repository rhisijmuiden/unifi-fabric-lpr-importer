"""Security settings and the signed-in sessions of all users (admin)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import require_admin
from ..models import User, UserSession
from ..schemas import SecuritySettingsIn
from ..security import SESSION_COOKIE, revoke_sessions, session_id
from ..settings_store import get_section, update_section
from .auth import session_dict

router = APIRouter(prefix="/api/security", tags=["security"])


def _settings(db: Session) -> dict:
    settings = get_settings()
    return {
        **get_section(db, "security"),
        # Read-only facts from the server configuration, shown on the page.
        "https": settings.base_url.lower().startswith("https://"),
        "cookie_secure": settings.cookie_secure,
        "secret_key_ok": settings.secret_key_ok,
    }


@router.get("/settings")
def get_security(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    return _settings(db)


@router.put("/settings")
def put_security(body: SecuritySettingsIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    update_section(db, "security", body.model_dump())
    audit.record(db, "settings.security_updated", user=admin, details=body.model_dump(), request=request)
    return _settings(db)


@router.get("/sessions")
def all_sessions(request: Request, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    current = session_id(request.cookies.get(SESSION_COOKIE))
    rows = [session_dict(s, current) for s in db.scalars(select(UserSession))]
    return sorted(rows, key=lambda s: str(s["last_seen_at"]), reverse=True)


@router.delete("/sessions/{sid}", status_code=204)
def end_session(sid: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    session = db.get(UserSession, sid)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    username = session.user.username
    db.delete(session)
    db.commit()
    audit.record(db, "auth.session_ended", user=admin, target=username, details={"ip": session.ip_address}, request=request)
    return Response(status_code=204)


@router.post("/users/{user_id}/end-sessions")
def end_user_sessions(user_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    keep = session_id(request.cookies.get(SESSION_COOKIE)) if user.id == admin.id else None
    ended = revoke_sessions(db, user.id, keep=keep)
    audit.record(db, "auth.sessions_ended", user=admin, target=user.username, details={"count": ended}, request=request)
    return {"ended": ended}
