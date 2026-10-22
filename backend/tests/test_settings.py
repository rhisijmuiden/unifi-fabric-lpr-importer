from app.services import entra
from app.settings_store import get_section


def test_smtp_secret_is_encrypted_and_hidden(admin_client, db):
    r = admin_client.put(
        "/api/settings/smtp",
        json={"host": "smtp.example.com", "port": 587, "username": "u", "password": "s3cret", "from_address": "a@b.nl"},
    )
    body = r.json()
    assert body["password_set"] is True
    assert "password" not in body
    from app.models import Setting

    stored = db.get(Setting, "smtp").value["password"]
    assert stored and stored != "s3cret"
    assert get_section(db, "smtp")["password"] == "s3cret"
    # Omitting the secret keeps it.
    admin_client.put("/api/settings/smtp", json={"host": "smtp2.example.com", "password": None})
    db.expire_all()
    assert get_section(db, "smtp")["password"] == "s3cret"


def test_sso_requires_config_before_enabling(admin_client):
    r = admin_client.put("/api/settings/sso", json={"enabled": True})
    assert r.status_code == 400
    r = admin_client.put(
        "/api/settings/sso",
        json={"enabled": True, "tenant_id": "t", "client_id": "c", "client_secret": "s", "admin_group_id": "g1"},
    )
    assert r.status_code == 200
    assert r.json()["client_secret_set"] is True
    assert r.json()["redirect_uri"].endswith("/api/auth/sso/callback")


def test_sso_role_mapping_highest_wins():
    cfg = {"admin_group_id": "a", "operator_group_id": "o", "viewer_group_id": "v"}
    assert entra.role_for_claims(cfg, {"groups": ["v", "o"]}) == "operator"
    assert entra.role_for_claims(cfg, {"groups": ["a", "v"]}) == "admin"
    assert entra.role_for_claims(cfg, {"groups": ["x"]}) is None


def test_local_login_disabled_keeps_admin_emergency_access(admin_client):
    admin_client.post("/api/users", json={"username": "op", "password": "long-enough-pw", "role": "operator"})
    admin_client.put(
        "/api/settings/sso",
        json={"enabled": True, "tenant_id": "t", "client_id": "c", "client_secret": "s",
              "admin_group_id": "g", "allow_local_login": False},
    )
    admin_client.post("/api/auth/logout")
    assert admin_client.post("/api/auth/login", json={"username": "op", "password": "long-enough-pw"}).status_code == 403
    from tests.conftest import ADMIN_PASSWORD

    assert admin_client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
