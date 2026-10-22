from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog, User


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return ""
    return request.client.host


def record(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    actor_type: str | None = None,
    actor: str | None = None,
    target: str = "",
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    success: bool = True,
    message: str = "",
    ip: str = "",
    commit: bool = True,
) -> None:
    db.add(
        AuditLog(
            actor_type=actor_type or ("user" if user else "system"),
            actor=actor or (user.username if user else "system"),
            action=action,
            target=target,
            details=details or {},
            ip_address=client_ip(request) or ip,
            success=success,
            message=message,
        )
    )
    if commit:
        db.commit()
