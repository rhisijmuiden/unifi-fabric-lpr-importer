from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import LanguageIn, LoginIn, PasswordChange, UserOut
from ..audit import client_ip
from ..models import UserSession
from ..security import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    hash_password,
    revoke_sessions,
    session_hours,
    session_id,
    verify_password,
    verify_password_timed,
)
from ..services import entra, ratelimit
from ..settings_store import get_section

router = APIRouter(prefix="/api/auth", tags=["auth"])

SSO_FLOW_COOKIE = "lpr_sso_flow"


def _set_session_cookie(db: Session, response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=session_hours(db) * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/config")
def auth_config(db: Session = Depends(get_db)) -> dict:
    sso = get_section(db, "sso")
    return {"sso_enabled": bool(sso["enabled"]), "local_login": bool(sso["allow_local_login"] or not sso["enabled"])}


def _new_session(db: Session, user: User, request: Request) -> str:
    return create_session(db, user, client_ip(request), request.headers.get("user-agent", ""))


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    cfg = get_section(db, "security")
    window = int(cfg["login_lock_minutes"]) * 60
    limit = int(cfg["login_max_attempts"])
    username = body.username.strip()
    user_key = f"login-user:{username.lower()}"
    ip_key = f"login-ip:{client_ip(request)}"
    if ratelimit.count(user_key, window) >= limit or ratelimit.count(ip_key, window) >= limit * 4:
        audit.record(db, "auth.login_locked", actor_type="user", actor=username[:255], request=request, success=False)
        wait = max(ratelimit.retry_after(user_key, window), ratelimit.retry_after(ip_key, window))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts", headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.username == username))
    if not verify_password_timed(body.password, user.password_hash if user else None) or user is None or not user.is_active:
        ratelimit.hit(user_key, window)
        ratelimit.hit(ip_key, window)
        audit.record(db, "auth.login_failed", actor_type="user", actor=username[:255], request=request, success=False)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")
    sso = get_section(db, "sso")
    # With SSO enforced, only local admins (emergency access) may use a password.
    if sso["enabled"] and not sso["allow_local_login"] and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "local_login_disabled")
    ratelimit.clear(user_key)
    # A new session on every sign-in; an old cookie in this browser is ended.
    delete_session(db, request.cookies.get(SESSION_COOKIE))
    _set_session_cookie(db, response, _new_session(db, user, request))
    audit.record(db, "auth.login", user=user, request=request)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    delete_session(db, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.put("/me/language", response_model=UserOut)
def set_language(body: LanguageIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    user.language = body.language
    db.commit()
    return user


@router.put("/me/password", status_code=204)
def change_password(
    body: PasswordChange, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    if user.auth_source != "local" or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_password")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    # Sign out everywhere else: whoever knew the old password loses access.
    ended = revoke_sessions(db, user.id, keep=session_id(request.cookies.get(SESSION_COOKIE)))
    audit.record(db, "user.password_changed", user=user, target=user.username, details={"sessions_ended": ended}, request=request)


def session_dict(s: UserSession, current: str | None) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "username": s.user.username,
        "created_at": s.created_at,
        "last_seen_at": s.last_seen_at or s.created_at,
        "expires_at": s.expires_at,
        "ip_address": s.ip_address,
        "user_agent": s.user_agent,
        "current": s.id == current,
    }


@router.get("/sessions")
def my_sessions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    """The signed-in sessions of this account, newest activity first."""
    current = session_id(request.cookies.get(SESSION_COOKIE))
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id))
    return sorted((session_dict(s, current) for s in rows), key=lambda s: str(s["last_seen_at"]), reverse=True)


@router.delete("/sessions/{sid}", status_code=204)
def end_my_session(sid: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    session = db.get(UserSession, sid)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    db.delete(session)
    db.commit()
    audit.record(db, "auth.session_ended", user=user, target=user.username, details={"ip": session.ip_address}, request=request)


@router.post("/sessions/end-others")
def end_other_sessions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ended = revoke_sessions(db, user.id, keep=session_id(request.cookies.get(SESSION_COOKIE)))
    audit.record(db, "auth.sessions_ended", user=user, target=user.username, details={"count": ended}, request=request)
    return {"ended": ended}


@router.get("/sso/login")
def sso_login(db: Session = Depends(get_db)) -> RedirectResponse:
    cfg = get_section(db, "sso")
    if not cfg["enabled"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sso_disabled")
    try:
        key, url = entra.start(cfg)
    except entra.SsoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        SSO_FLOW_COOKIE, key, max_age=600, httponly=True, secure=get_settings().cookie_secure, samesite="lax", path="/"
    )
    return response


@router.get("/sso/callback")
def sso_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    cfg = get_section(db, "sso")
    params = dict(request.query_params)
    try:
        if not cfg["enabled"]:
            raise entra.SsoError("Single sign-on is disabled")
        claims = entra.finish(cfg, request.cookies.get(SSO_FLOW_COOKIE), params)
    except (entra.SsoError, ValueError) as exc:
        audit.record(db, "auth.sso_failed", request=request, success=False, message=str(exc))
        return RedirectResponse("/login?error=sso_failed", status_code=302)

    oid = claims.get("oid")
    username = claims.get("preferred_username") or claims.get("email") or oid
    role = entra.role_for_claims(cfg, claims)
    if not oid or role is None:
        audit.record(db, "auth.sso_denied", actor_type="user", actor=str(username), request=request, success=False)
        return RedirectResponse("/login?error=sso_no_role", status_code=302)

    user = db.scalar(select(User).where(User.entra_oid == oid))
    if user is None:
        user = db.scalar(select(User).where(User.username == username))
        if user is not None and user.auth_source == "local":
            # Never take over a local account by name.
            username = f"{username} (entra)"
            user = None
    if user is None:
        user = User(username=username, auth_source="entra", entra_oid=oid, role=role)
        db.add(user)
    if not user.is_active:
        return RedirectResponse("/login?error=account_disabled", status_code=302)
    user.role = role
    user.display_name = claims.get("name") or user.display_name
    user.email = claims.get("email") or claims.get("preferred_username") or user.email
    db.commit()

    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(SSO_FLOW_COOKIE, path="/")
    _set_session_cookie(db, response, _new_session(db, user, request))
    audit.record(db, "auth.login_sso", user=user, request=request)
    return response
