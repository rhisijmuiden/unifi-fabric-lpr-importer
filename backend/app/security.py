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


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:  # SQLite drops the timezone
        return value.replace(tzinfo=timezone.utc)
    return value


def session_hours(db: Session) -> int:
    from .settings_store import get_section

    return int(get_section(db, "security")["session_hours"])


def create_session(db: Session, user: User, ip: str = "", user_agent: str = "") -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=session_hours(db))
    db.add(UserSession(id=_token_id(token), user_id=user.id, expires_at=expires, last_seen_at=now, ip_address=ip[:64], user_agent=user_agent[:255]))
    user.last_login_at = now
    db.commit()
    return token


# Activity is written at most this often, not on every request.
SEEN_INTERVAL = timedelta(seconds=60)


def resolve_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.get(UserSession, _token_id(token))
    if session is None:
        return None
    from .settings_store import get_section

    now = datetime.now(timezone.utc)
    idle = int(get_section(db, "security")["idle_minutes"])
    seen = _aware(session.last_seen_at) or _aware(session.created_at)
    expired = _aware(session.expires_at) < now or (idle > 0 and seen is not None and seen + timedelta(minutes=idle) < now)
    if expired or not session.user.is_active:
        db.delete(session)
        db.commit()
        return None
    if seen is None or now - seen > SEEN_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session.user


def session_id(token: str | None) -> str | None:
    return _token_id(token) if token else None


def delete_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.get(UserSession, _token_id(token))
    if session is not None:
        db.delete(session)
        db.commit()


def revoke_sessions(db: Session, user_id: int, keep: str | None = None) -> int:
    """End every session of a user, except the session id `keep`. Returns the number ended."""
    sessions = [s for s in db.scalars(select(UserSession).where(UserSession.user_id == user_id)) if s.id != keep]
    for s in sessions:
        db.delete(s)
    db.commit()
    return len(sessions)


def _fernet(secret_key: str | None = None) -> Fernet:
    digest = hashlib.sha256(("lpr-secrets:" + (secret_key or get_settings().secret_key)).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str, secret_key: str | None = None) -> str:
    return _fernet(secret_key).encrypt(value.encode()).decode()


def decrypt(value: str, secret_key: str | None = None) -> str | None:
    """Decrypt with the app's secret key, or another one (restoring a backup from another server)."""
    try:
        return _fernet(secret_key).decrypt(value.encode()).decode()
    except InvalidToken:
        return None


API_KEY_PREFIX = "lpr_"


def new_api_key() -> tuple[str, str, str]:
    """Return (key shown once, short prefix for the UI, hash stored in the database)."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:12], _token_id(key)


# Compared against when the user name does not exist, so a failed sign-in takes as long either way.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))


def verify_password_timed(password: str, hashed: str | None) -> bool:
    if not hashed:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed)


# Columns outside the settings table that hold encrypted secrets: (table, column).
ENCRYPTED_COLUMNS = (("consoles", "api_token"), ("backup_targets", "password"), ("import_schedules", "password"))


def resolve_api_key(db: Session, key: str) -> ApiKey | None:
    if not key.startswith(API_KEY_PREFIX):
        return None
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == _token_id(key)))
    if row is None or not row.is_active:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return row
