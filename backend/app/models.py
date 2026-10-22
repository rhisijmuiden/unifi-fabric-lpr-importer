from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLES = ("admin", "operator", "viewer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    # Null for SSO-only accounts.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_source: Mapped[str] = mapped_column(String(20), default="local")  # local | entra
    entra_oid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Setting(Base):
    """Key/value settings edited from the UI. Secret values are stored encrypted."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Every change made by a person, an API key or the system."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_type: Mapped[str] = mapped_column(String(20))  # user | api_key | system
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str] = mapped_column(String(255), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str] = mapped_column(Text, default="")


class Console(Base):
    """A UniFi console running UniFi Access, reached on its local API (port 12445)."""

    __tablename__ = "consoles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    location: Mapped[str] = mapped_column(String(100), default="")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=12445)
    api_token: Mapped[str] = mapped_column(Text, default="")  # encrypted
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plates: Mapped[list["ConsolePlate"]] = relationship(back_populates="console", cascade="all, delete-orphan")


class Vehicle(Base):
    """A company vehicle managed by this application."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(32))  # official notation, e.g. 12-BDF-3
    plate_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # letters and digits only
    department: Mapped[str] = mapped_column(String(100), default="", index=True)
    location: Mapped[str] = mapped_column(String(100), default="", index=True)
    group_name: Mapped[str] = mapped_column(String(200), default="", index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | csv | api | console
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ConsolePlate(Base):
    """A license plate found on a console during the last scan or change.

    Presence of a vehicle on a console = a row with the same plate_key."""

    __tablename__ = "console_plates"
    __table_args__ = (UniqueConstraint("console_id", "plate_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    console_id: Mapped[int] = mapped_column(ForeignKey("consoles.id", ondelete="CASCADE"), index=True)
    plate_key: Mapped[str] = mapped_column(String(32), index=True)
    credential: Mapped[str] = mapped_column(String(64))
    plate_id: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="")
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str] = mapped_column(String(255), default="")
    groups: Mapped[list] = mapped_column(JSON, default=list)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    console: Mapped[Console] = relationship(back_populates="plates")


class ApiKey(Base):
    """Key for systems such as Lobster that push vehicles through the REST API."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))  # shown in the UI to recognise the key
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    allow_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    """A batch of changes on the consoles, run in the background."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # scan | assign | remove | import
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed
    actor_type: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(255))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackupTarget(Base):
    """A remote location (FTP, FTPS or SCP) that receives encrypted backups."""

    __tablename__ = "backup_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    protocol: Mapped[str] = mapped_column(String(10))  # ftp | ftps | scp
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(Text, default="")  # encrypted
    # scp only: "password" or "key" (the application's own SSH key).
    auth_method: Mapped[str] = mapped_column(String(10), default="password")
    # scp only: SHA256 fingerprint pinned on the first successful connection.
    host_key: Mapped[str] = mapped_column(String(128), default="")
    remote_path: Mapped[str] = mapped_column(String(500), default="lpr-importer")
    # ftps only: implicit TLS (port 990) instead of explicit (AUTH TLS on port 21).
    ftps_implicit: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    passive: Mapped[bool] = mapped_column(Boolean, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_backup_name: Mapped[str] = mapped_column(String(100), default="")
    last_status: Mapped[str] = mapped_column(String(20), default="")  # "" | ok | failed
    last_message: Mapped[str] = mapped_column(Text, default="")
