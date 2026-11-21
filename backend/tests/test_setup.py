import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.settings_store import get_section, update_section

from .conftest import ADMIN_PASSWORD


@pytest.fixture
def no_service(monkeypatch):
    """The privileged unit is not there in tests: 'true' stands in for systemctl."""
    monkeypatch.setenv("LPR_UPDATE_COMMAND", "true")
    get_settings.cache_clear()


def _pending(db):
    update_section(db, "setup", {"pending": True})


def _cert(cn="lpr.example.com", days=30):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return cert.public_bytes(serialization.Encoding.PEM).decode(), key_pem


def test_status_not_pending_by_default(admin_client):
    assert admin_client.get("/api/setup/status").json() == {"pending": False}


def test_create_admin_marks_setup_pending(app_env, db, capsys):
    from app import cli

    assert cli.main(["create-admin"]) == 0
    assert "password:" in capsys.readouterr().out
    db.expire_all()
    assert get_section(db, "setup")["pending"] is True


def test_setup_account_and_complete(admin_client, db, no_service, app_env):
    _pending(db)
    status = admin_client.get("/api/setup/status").json()
    assert status["pending"] is True and "web" in status
    r = admin_client.put("/api/setup/account", json={"new_password": "a-new-password-1", "email": "it@example.com", "language": "nl"})
    assert r.status_code == 204, r.text
    r = admin_client.post("/api/setup/complete", json={"web": {"mode": "selfsigned", "host": "lpr.example.com"}, "channel": ""})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True and body["restart"] is True
    assert body["base_url"] == "https://lpr.example.com:8080"
    request = json.loads((app_env / "state" / "config-request.json").read_text())
    assert request["mode"] == "selfsigned" and request["finish_setup"] is True
    assert admin_client.get("/api/setup/status").json() == {"pending": False}
    # Done once: no second run, and the old password no longer works.
    assert admin_client.post("/api/setup/complete", json={}).status_code == 409
    admin_client.post("/api/auth/logout")
    assert admin_client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 401
    assert admin_client.post("/api/auth/login", json={"username": "admin", "password": "a-new-password-1"}).status_code == 200


def test_setup_needs_pending(admin_client):
    assert admin_client.put("/api/setup/account", json={"new_password": "a-new-password-1"}).status_code == 409


def test_invalid_host_rejected(admin_client, db, no_service):
    _pending(db)
    r = admin_client.post("/api/setup/complete", json={"web": {"mode": "http", "host": "bad host/;rm"}})
    assert r.status_code == 400 and r.json()["detail"] == "invalid_host"
    db.expire_all()
    assert get_section(db, "setup")["pending"] is True


def test_own_certificate_checked(admin_client, no_service, app_env):
    cert, key = _cert()
    _, other_key = _cert()
    r = admin_client.put("/api/system/web", json={"mode": "own", "host": "lpr.example.com", "cert_pem": cert, "key_pem": other_key})
    assert r.status_code == 400 and r.json()["detail"] == "key_mismatch"
    r = admin_client.put("/api/system/web", json={"mode": "own", "host": "lpr.example.com", "cert_pem": cert, "key_pem": key})
    assert r.status_code == 202, r.text
    request = json.loads((app_env / "state" / "config-request.json").read_text())
    assert request["cert_pem"] == cert and request["finish_setup"] is False
    assert admin_client.get("/api/system/web-status").json()["state"] == "running"


def test_service_failure_reported(admin_client, monkeypatch):
    monkeypatch.setenv("LPR_UPDATE_COMMAND", "false")
    get_settings.cache_clear()
    r = admin_client.put("/api/system/web", json={"mode": "http"})
    assert r.status_code == 400


def test_web_info(admin_client):
    info = admin_client.get("/api/system/web").json()
    assert info["mode"] == "http" and info["port"] == 8080 and info["https"] is False


def test_viewer_cannot_change_web(client, db):
    from app.models import User
    from app.security import hash_password

    db.add(User(username="viewer", role="viewer", password_hash=hash_password("viewer-password-1")))
    db.commit()
    client.post("/api/auth/login", json={"username": "viewer", "password": "viewer-password-1"})
    assert client.put("/api/system/web", json={"mode": "http"}).status_code == 403
    assert client.get("/api/setup/status").json() == {"pending": False}
