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
