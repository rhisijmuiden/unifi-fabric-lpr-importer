def test_create_update_delete_user(admin_client):
    r = admin_client.post(
        "/api/users", json={"username": "jan", "password": "long-enough-pw", "role": "operator"}
    )
    assert r.status_code == 201
    uid = r.json()["id"]
    assert admin_client.post("/api/users", json={"username": "jan", "password": "long-enough-pw"}).status_code == 409
    r = admin_client.patch(f"/api/users/{uid}", json={"role": "viewer"})
    assert r.json()["role"] == "viewer"
    assert admin_client.delete(f"/api/users/{uid}").status_code == 204


def test_last_admin_is_protected(admin_client):
    me = admin_client.get("/api/auth/me").json()
    assert admin_client.patch(f"/api/users/{me['id']}", json={"role": "viewer"}).status_code == 400
    assert admin_client.delete(f"/api/users/{me['id']}").status_code == 400


def test_viewer_cannot_manage_users(admin_client):
    admin_client.post("/api/users", json={"username": "kees", "password": "long-enough-pw", "role": "viewer"})
    admin_client.post("/api/auth/logout")
    admin_client.post("/api/auth/login", json={"username": "kees", "password": "long-enough-pw"})
    assert admin_client.get("/api/users").status_code == 403
