import ipaddress
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .audit import client_ip
from .db import get_db
from .models import ApiKey, User
from .security import SESSION_COOKIE, resolve_api_key, resolve_session
from .services import ratelimit
from .services.jobs import Actor
from .settings_store import get_section

INVALID_KEYS_PER_MINUTE = 30


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
    ip = client_ip(request)
    bad_key = f"api-invalid:{ip}"
    # An address that keeps sending wrong keys is paused for a minute.
    if ratelimit.count(bad_key, 60) >= INVALID_KEYS_PER_MINUTE:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_requests", headers={"Retry-After": str(ratelimit.retry_after(bad_key, 60))})
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    key = resolve_api_key(db, token.strip()) if scheme.lower() == "bearer" else None
    if key is None:
        ratelimit.hit(bad_key, 60)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_api_key", headers={"WWW-Authenticate": "Bearer"})
    if key.allowed_ips and not ip_allowed(ip, key.allowed_ips):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ip_not_allowed")
    limit = int(get_section(db, "security")["api_requests_per_minute"])
    rate_key = f"api-key:{key.id}"
    if ratelimit.hit(rate_key, 60) > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_requests", headers={"Retry-After": str(ratelimit.retry_after(rate_key, 60))})
    return key


def ip_allowed(ip: str, networks: list[str]) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    for network in networks:
        try:
            if address in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def api_actor(key: ApiKey, request: Request) -> Actor:
    return Actor("api_key", key.name, client_ip(request))
