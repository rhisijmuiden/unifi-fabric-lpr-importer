import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ApiKey, User, UserSession

SESSION_COOKIE = "lpr_session"

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return _password_hash.verify(password, hashed)


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=get_settings().session_hours)
    db.add(UserSession(id=_token_id(token), user_id=user.id, expires_at=expires))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return token


def resolve_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.get(UserSession, _token_id(token))
    if session is None:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:  # SQLite drops the timezone
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc) or not session.user.is_active:
        db.delete(session)
        db.commit()
        return None
    return session.user


def delete_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.get(UserSession, _token_id(token))
    if session is not None:
        db.delete(session)
        db.commit()


def _fernet() -> Fernet:
    digest = hashlib.sha256(("lpr-secrets:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


API_KEY_PREFIX = "lpr_"


def new_api_key() -> tuple[str, str, str]:
    """Return (key shown once, short prefix for the UI, hash stored in the database)."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:12], _token_id(key)


def resolve_api_key(db: Session, key: str) -> ApiKey | None:
    if not key.startswith(API_KEY_PREFIX):
        return None
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == _token_id(key)))
    if row is None or not row.is_active:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return row
