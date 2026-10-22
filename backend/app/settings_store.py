"""Settings sections stored in the database.

Each section is a dict. Fields listed in SECRET_FIELDS are encrypted at rest and
never returned to the browser; the API exposes `<field>_set: true/false` instead.
"""

from typing import Any

from sqlalchemy.orm import Session

from .models import Setting
from .security import decrypt, encrypt

DEFAULTS: dict[str, dict[str, Any]] = {
    "sso": {
        "enabled": False,
        "tenant_id": "",
        "client_id": "",
        "client_secret": "",
        "admin_group_id": "",
        "operator_group_id": "",
        "viewer_group_id": "",
        # When true, local password login stays available next to SSO.
        "allow_local_login": True,
    },
    "smtp": {
        "host": "",
        "port": 587,
        "security": "starttls",  # none | starttls | ssl
        "auth_method": "password",  # none | password | oauth2_m365
        "username": "",
        "password": "",
        "oauth_tenant_id": "",
        "oauth_client_id": "",
        "oauth_client_secret": "",
        "from_address": "",
        "from_name": "UniFi Fabric License Plate Importer",
        "verify_tls": True,
    },
    "access": {
        # How the plate is sent to UniFi Access: "compact" (12BDF3, default) or "official" (12-BDF-3).
        "plate_notation": "compact",
        # When a plate is removed, also delete the Access user if it only held that vehicle.
        "delete_vehicle_users": True,
    },
    "backup": {
        # Encrypts every backup (AES-256-GCM). Needed to restore, also on a new server.
        "passphrase": "",
        # The application's own SSH key (OpenSSH format) for SCP targets.
        "ssh_private_key": "",
        # Number of full backups to keep per target, each with its incremental backups.
        "keep_full": 4,
        "schedule_full": {"enabled": True, "frequency": "weekly", "time": "02:00", "weekday": 6, "monthday": 1},
        "schedule_incremental": {"enabled": True, "frequency": "daily", "time": "02:00", "weekday": 0, "monthday": 1},
        "notify_email": "",
        "notify_on": "failure",  # failure | always | never
    },
    "notifications": {
        # Comma separated addresses that receive the mails below.
        "recipients": "",
        "import_report": "failure",  # failure | always | never (CSV and API imports)
        "sync_failure": True,  # registering or removing plates on a console failed
        "update_available": True,  # a new version is available on the installed channel
    },
    "import": {
        # Last used CSV column mapping, offered again on the next import.
        "mapping": {},
        "defaults": {},
    },
}

SECRET_FIELDS = {
    "sso": {"client_secret"},
    "smtp": {"password", "oauth_client_secret"},
    "backup": {"passphrase", "ssh_private_key"},
}


def get_section(db: Session, key: str) -> dict[str, Any]:
    """Return the section with secrets decrypted (server-side use only)."""
    data = dict(DEFAULTS.get(key, {}))
    row = db.get(Setting, key)
    if row is not None:
        data.update(row.value or {})
    for field in SECRET_FIELDS.get(key, set()):
        stored = data.get(field) or ""
        data[field] = decrypt(stored) or "" if stored else ""
    return data


def public_section(db: Session, key: str) -> dict[str, Any]:
    """Return the section for the browser, with secrets replaced by a flag."""
    data = get_section(db, key)
    for field in SECRET_FIELDS.get(key, set()):
        data[f"{field}_set"] = bool(data.pop(field))
    return data


def update_section(db: Session, key: str, changes: dict[str, Any]) -> None:
    """Merge changes into a section. A secret sent as None or omitted keeps its value;
    an empty string clears it."""
    row = db.get(Setting, key)
    current = dict(row.value) if row is not None else {}
    secrets = SECRET_FIELDS.get(key, set())
    allowed = DEFAULTS.get(key, {})
    for field, value in changes.items():
        if field not in allowed:
            continue
        if field in secrets:
            if value is None:
                continue
            current[field] = encrypt(value) if value else ""
        else:
            current[field] = value
    if row is None:
        db.add(Setting(key=key, value=current))
    else:
        row.value = current
    db.commit()
