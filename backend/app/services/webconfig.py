"""Web address and HTTP/HTTPS of the application.

The configuration file and certificates belong to root, so the app never changes them itself.
A change is requested by writing config-request.json to the state directory and starting
lpr-importer-update.service, whose script hands the request to scripts/configure.sh. That
script writes config-status.json and restarts the application.
"""

import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from ..config import get_settings

MODES = ("http", "selfsigned", "own", "keep")
HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
PORT = 8080


class WebConfigError(Exception):
    pass


def _env_file_value(key: str) -> str:
    """A value from the configuration file, as loaded by systemd when the app started."""
    return os.environ.get(key, "")


def _certificate_info(path: str) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        cert = x509.load_pem_x509_certificate(Path(path).read_bytes())
    except (OSError, ValueError):
        return None
    try:
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        san = [str(n.value) for n in names]
    except x509.ExtensionNotFound:
        san = []
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "self_signed": cert.issuer == cert.subject,
        "not_after": cert.not_valid_after_utc.isoformat(),
        "names": san,
    }


def info() -> dict[str, Any]:
    settings = get_settings()
    parts = urlsplit(settings.base_url)
    cert_path = _env_file_value("LPR_TLS_CERT")
    cert = _certificate_info(cert_path)
    https = bool(cert_path)
    mode = "http"
    if https:
        mode = "selfsigned" if cert and cert["self_signed"] else "own"
    return {
        "base_url": settings.base_url,
        "host": parts.hostname or "",
        "port": PORT,
        "https": https,
        "mode": mode,
        "certificate": cert,
        "status": read_status(),
    }


def validate_host(host: str) -> str:
    host = host.strip().lower()
    if not HOST_RE.match(host):
        raise WebConfigError("invalid_host")
    return host


def validate_certificate(cert_pem: str, key_pem: str) -> None:
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
    except ValueError as exc:
        raise WebConfigError("invalid_certificate") from exc
    try:
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise WebConfigError("invalid_key") from exc
    pub = serialization.PublicFormat.SubjectPublicKeyInfo
    enc = serialization.Encoding.PEM
    if cert.public_key().public_bytes(enc, pub) != key.public_key().public_bytes(enc, pub):
        raise WebConfigError("key_mismatch")
    if cert.not_valid_after_utc < datetime.now(timezone.utc):
        raise WebConfigError("certificate_expired")


def request_change(
    *,
    mode: str = "keep",
    host: str = "",
    cert_pem: str = "",
    key_pem: str = "",
    finish_setup: bool = False,
    channel: str = "",
) -> None:
    """Ask the privileged unit to apply a web configuration; the app restarts afterwards."""
    if mode not in MODES:
        raise WebConfigError("invalid_mode")
    if host:
        host = validate_host(host)
    if mode == "own":
        validate_certificate(cert_pem, key_pem)
    settings = get_settings()
    state = settings.state_dir
    state.mkdir(parents=True, exist_ok=True)
    current = read_status()
    if current.get("state") == "running" and not _stale(current):
        raise WebConfigError("already_running")
    request = state / "config-request.json"
    request.touch(mode=0o600)
    request.write_text(
        json.dumps(
            {
                "mode": mode,
                "host": host,
                "cert_pem": cert_pem if mode == "own" else "",
                "key_pem": key_pem if mode == "own" else "",
                "finish_setup": finish_setup,
                "channel": channel,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    (state / "config-status.json").write_text(
        json.dumps({"state": "running", "message": "Requested", "updated_at": datetime.now(timezone.utc).isoformat()})
    )
    result = subprocess.run(shlex.split(settings.update_command), capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        (state / "config-status.json").write_text(json.dumps({"state": "failed", "message": "Could not start the configuration service"}))
        request.unlink(missing_ok=True)
        raise WebConfigError(result.stderr.strip() or "service_unavailable")


def new_base_url(mode: str, host: str) -> str:
    current = urlsplit(get_settings().base_url)
    https = bool(_env_file_value("LPR_TLS_CERT")) if mode == "keep" else mode in ("selfsigned", "own")
    return f"{'https' if https else 'http'}://{host or current.hostname or 'localhost'}:{PORT}"


def _stale(status: dict[str, Any]) -> bool:
    """A request that never finished (e.g. the server restarted) does not block new ones forever."""
    try:
        updated = datetime.fromisoformat(status["updated_at"])
    except (KeyError, ValueError):
        return True
    return (datetime.now(timezone.utc) - updated).total_seconds() > 600


def read_status() -> dict[str, Any]:
    try:
        return json.loads((get_settings().state_dir / "config-status.json").read_text())
    except (OSError, ValueError):
        return {"state": "idle"}
