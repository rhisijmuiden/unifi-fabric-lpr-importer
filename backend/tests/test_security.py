from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import User, UserSession
from app.security import hash_password
from tests.conftest import ADMIN_PASSWORD, HEADERS
from tests.test_public_api import make_key


def login(client, username="admin", password=ADMIN_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_lockout_per_username(client):
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    r = login(client)  # even the right password waits until the lock expires
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"
    assert int(r.headers["retry-after"]) > 0
    assert login(client, username="someone-else", password="x").status_code == 401  # other names still answer


def test_success_resets_counter(client):
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="wrong-password").status_code == 401


def test_sessions_list_and_end_others(admin_client, app_env):
    with TestClient(create_app(), headers=HEADERS) as other:
        assert login(other).status_code == 200
        sessions = admin_client.get("/api/auth/sessions").json()
        assert len(sessions) == 2
        assert sum(s["current"] for s in sessions) == 1
        assert all(s["user_agent"] and s["ip_address"] for s in sessions)

        assert admin_client.post("/api/auth/sessions/end-others").json() == {"ended": 1}
        assert other.get("/api/auth/me").status_code == 401
        assert admin_client.get("/api/auth/me").status_code == 200


def test_password_change_ends_other_sessions(admin_client):
    with TestClient(create_app(), headers=HEADERS) as other:
        login(other)
        r = admin_client.put("/api/auth/me/password", json={"current_password": ADMIN_PASSWORD, "new_password": "a-new-password-456"})
        assert r.status_code == 204
        assert other.get("/api/auth/me").status_code == 401
        assert admin_client.get("/api/auth/me").status_code == 200


def test_admin_disable_and_end_sessions(admin_client, db):
    db.add(User(username="op", role="operator", password_hash=hash_password("operator-pass-1")))
    db.commit()
    op = db.query(User).filter_by(username="op").one()
    with TestClient(create_app(), headers=HEADERS) as other:
        assert login(other, "op", "operator-pass-1").status_code == 200
        everyone = admin_client.get("/api/security/sessions").json()
        assert {s["username"] for s in everyone} == {"admin", "op"}
        assert admin_client.post(f"/api/security/users/{op.id}/end-sessions").json() == {"ended": 1}
        assert other.get("/api/auth/me").status_code == 401

        login(other, "op", "operator-pass-1")
        admin_client.patch(f"/api/users/{op.id}", json={"role": "viewer"})
        assert other.get("/api/auth/me").status_code == 401  # a role change signs the user out


def test_idle_timeout(admin_client, db):
    session = db.query(UserSession).one()
    session.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=61)
    db.commit()
    assert admin_client.get("/api/auth/me").status_code == 401

    login(admin_client)
    r = admin_client.put("/api/security/settings", json={"session_hours": 8, "idle_minutes": 0, "login_max_attempts": 5, "login_lock_minutes": 15, "api_requests_per_minute": 600})
    assert r.status_code == 200 and r.json()["idle_minutes"] == 0
    db.expire_all()
    session = db.query(UserSession).one()
    session.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert admin_client.get("/api/auth/me").status_code == 200  # no idle limit any more


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in client.get("/api/docs").headers


def test_api_rate_limit(admin_client):
    key = make_key(admin_client)
    admin_client.put("/api/security/settings", json={"session_hours": 12, "idle_minutes": 60, "login_max_attempts": 5, "login_lock_minutes": 15, "api_requests_per_minute": 10})
    auth = {"Authorization": f"Bearer {key}"}
    codes = [admin_client.get("/api/v1/status", headers=auth).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_invalid_keys_are_paused(client):
    codes = [client.get("/api/v1/status", headers={"Authorization": "Bearer lpr_wrong"}).status_code for _ in range(31)]
    assert codes[:30] == [401] * 30 and codes[30] == 429
