from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .audit import client_ip
from .db import get_db
from .models import ApiKey, User
from .security import SESSION_COOKIE, resolve_api_key, resolve_session
from .services.jobs import Actor


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return user

    return checker


require_admin = require_role("admin")


require_operator = require_role("admin", "operator")


def user_actor(user: User, request: Request) -> Actor:
    return Actor("user", user.username, client_ip(request))


def api_key(request: Request, db: Session = Depends(get_db)) -> ApiKey:
    """Authenticate an external system by `Authorization: Bearer lpr_...`."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    key = resolve_api_key(db, token.strip()) if scheme.lower() == "bearer" else None
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_api_key", headers={"WWW-Authenticate": "Bearer"})
    return key


def api_actor(key: ApiKey, request: Request) -> Actor:
    return Actor("api_key", key.name, client_ip(request))
