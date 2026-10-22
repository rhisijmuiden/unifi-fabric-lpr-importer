from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    email: str
    role: str
    auth_source: str
    language: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginIn(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    display_name: str = ""
    email: str = ""
    role: str = Field(default="viewer", pattern="^(admin|operator|viewer)$")
    password: str = Field(min_length=10)
    language: str = Field(default="en", pattern="^(en|nl)$")


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = Field(default=None, pattern="^(admin|operator|viewer)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)
    language: str | None = Field(default=None, pattern="^(en|nl)$")


class LanguageIn(BaseModel):
    language: str = Field(pattern="^(en|nl)$")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class SsoSettingsIn(BaseModel):
    enabled: bool = False
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str | None = None
    admin_group_id: str = ""
    operator_group_id: str = ""
    viewer_group_id: str = ""
    allow_local_login: bool = True


class SmtpSettingsIn(BaseModel):
    host: str = ""
    port: int = Field(default=587, ge=1, le=65535)
    security: str = Field(default="starttls", pattern="^(none|starttls|ssl)$")
    auth_method: str = Field(default="password", pattern="^(none|password|oauth2_m365)$")
    username: str = ""
    password: str | None = None
    oauth_tenant_id: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str | None = None
    from_address: str = ""
    from_name: str = ""
    verify_tls: bool = True


class TestMailIn(BaseModel):
    to: str = Field(min_length=3)


class UpdateIn(BaseModel):
    channel: str = Field(pattern="^(main|test)$")


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_type: str
    actor: str
    action: str
    target: str
    details: dict
    ip_address: str
    success: bool
    message: str


class ConsoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location: str = Field(default="", max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=12445, ge=1, le=65535)
    # None keeps the stored token on update.
    api_token: str | None = None
    verify_tls: bool = False
    is_active: bool = True
    sort_order: int = 0


class ConsoleTestIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=12445, ge=1, le=65535)
    api_token: str | None = None
    verify_tls: bool = False
    # Use the stored token of this console when no token is given.
    console_id: int | None = None


class ConsoleIds(BaseModel):
    console_ids: list[int] | None = None


class VehicleIn(BaseModel):
    plate: str = Field(min_length=2, max_length=32)
    department: str = Field(min_length=1, max_length=100)
    location: str = Field(default="", max_length=100)
    group_name: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=255)


class VehicleUpdate(BaseModel):
    department: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    group_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=255)


class VehicleBulk(BaseModel):
    vehicle_ids: list[int] = Field(min_length=1)
    console_ids: list[int] | None = None


class VehicleRemove(VehicleBulk):
    # Also delete the vehicles from this application after removing them from the consoles.
    delete_vehicles: bool = False


class VehicleBulkEdit(BaseModel):
    vehicle_ids: list[int] = Field(min_length=1)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    group_name: str | None = Field(default=None, max_length=200)


class AdoptItem(BaseModel):
    plate: str
    department: str = Field(min_length=1, max_length=100)
    location: str = ""
    group_name: str = ""
    description: str = ""


class AdoptIn(BaseModel):
    items: list[AdoptItem] = Field(min_length=1)


class ImportRow(BaseModel):
    plate: str = ""
    department: str = ""
    location: str = ""
    group_name: str = ""
    description: str = ""


class ImportIn(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=20000)
    console_ids: list[int] = []
    mode: str = Field(default="upsert", pattern="^(upsert|full)$")


class ImportMappingIn(BaseModel):
    mapping: dict[str, str] = {}
    defaults: dict[str, str] = {}


class AccessSettingsIn(BaseModel):
    plate_notation: str = Field(default="compact", pattern="^(official|compact)$")
    delete_vehicle_users: bool = True


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    allow_delete: bool = False


class ApiKeyUpdate(BaseModel):
    allow_delete: bool | None = None
    is_active: bool | None = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    allow_delete: bool
    is_active: bool
    created_by: str
    created_at: datetime
    last_used_at: datetime | None


class ApiVehiclesIn(BaseModel):
    """Vehicles pushed by an external system such as Lobster."""

    vehicles: list[ImportRow] = Field(min_length=1, max_length=20000)
    # upsert: add and update only. full: also remove vehicles of the same departments that are missing.
    mode: str = Field(default="upsert", pattern="^(upsert|full)$")
    # Console ids or names to register on; omitted = all active consoles, [] = store only.
    consoles: list[int | str] | None = None
    dry_run: bool = False


class BackupTargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: str = Field(pattern="^(ftp|ftps|scp)$")
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    # None keeps the stored password on update.
    password: str | None = None
    auth_method: str = Field(default="password", pattern="^(password|key)$")
    # None keeps the pinned SSH host key; "" forgets it (pinned again on the next connection).
    host_key: str | None = None
    remote_path: str = Field(default="lpr-importer", max_length=500)
    ftps_implicit: bool = False
    verify_tls: bool = True
    passive: bool = True
    is_enabled: bool = True


class BackupTargetTestIn(BackupTargetIn):
    name: str = ""
    # Use the stored password and pinned host key of this target when none is given.
    target_id: int | None = None


class BackupSchedule(BaseModel):
    enabled: bool = False
    frequency: str = Field(default="daily", pattern="^(hourly|daily|weekly|monthly)$")
    time: str = Field(default="02:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=6, ge=0, le=6)  # 0 = Monday
    monthday: int = Field(default=1, ge=1, le=28)


class BackupSettingsIn(BaseModel):
    # None keeps the current passphrase.
    passphrase: str | None = Field(default=None, min_length=12, max_length=200)
    keep_full: int = Field(default=4, ge=1, le=100)
    schedule_full: BackupSchedule
    schedule_incremental: BackupSchedule
    notify_email: str = Field(default="", max_length=255)
    notify_on: str = Field(default="failure", pattern="^(failure|always|never)$")


class BackupRunIn(BaseModel):
    kind: str = Field(pattern="^(full|incremental)$")
    target_ids: list[int] | None = None


class RestoreIn(BaseModel):
    target_id: int
    name: str = Field(min_length=1, max_length=100)
    # The passphrase the backup was made with; empty = the current one.
    passphrase: str | None = None
    confirm: bool = False
