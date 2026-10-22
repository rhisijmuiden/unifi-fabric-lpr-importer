from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _other_active_admins(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active, User.id != user_id)
    ) or 0


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> User:
    if db.scalar(select(User).where(User.username == body.username.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    user = User(
        username=body.username.strip(),
        display_name=body.display_name,
        email=body.email,
        role=body.role,
        language=body.language,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    audit.record(db, "user.created", user=admin, target=user.username, details={"role": user.role}, request=request)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    changes = body.model_dump(exclude_unset=True)
    demotes = changes.get("role", "admin") != "admin" or changes.get("is_active") is False
    if user.role == "admin" and demotes and _other_active_admins(db, user.id) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "last_admin")
    if "password" in changes:
        if user.auth_source != "local":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "sso_account")
        user.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "***"
    for field, value in changes.items():
        if field != "password":
            setattr(user, field, value)
    db.commit()
    audit.record(db, "user.updated", user=admin, target=user.username, details=changes, request=request)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_delete_self")
    if user.role == "admin" and _other_active_admins(db, user.id) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "last_admin")
    db.delete(user)
    db.commit()
    audit.record(db, "user.deleted", user=admin, target=user.username, request=request)
