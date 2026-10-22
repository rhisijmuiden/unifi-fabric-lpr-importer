from tests.conftest import ADMIN_PASSWORD


def test_login_and_me(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_wrong_password_is_rejected_and_logged(admin_client):
    admin_client.post("/api/auth/logout")
    r = admin_client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    admin_client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    actions = [i["action"] for i in admin_client.get("/api/audit").json()["items"]]
    assert "auth.login_failed" in actions


def test_logout_invalidates_session(admin_client):
    assert admin_client.post("/api/auth/logout").status_code == 204
    assert admin_client.get("/api/auth/me").status_code == 401


def test_csrf_header_required(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403


def test_language_preference(admin_client):
    r = admin_client.put("/api/auth/me/language", json={"language": "nl"})
    assert r.json()["language"] == "nl"
