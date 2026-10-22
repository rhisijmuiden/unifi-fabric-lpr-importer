from app.services import access_mock
from tests.test_consoles import add_console


def make_key(client, allow_delete=False):
    r = client.post("/api/api-keys", json={"name": "Lobster", "allow_delete": allow_delete})
    assert r.status_code == 201
    return r.json()["key"]


def test_requires_key(client):
    assert client.get("/api/v1/vehicles").status_code == 401
    assert client.get("/api/v1/vehicles", headers={"Authorization": "Bearer lpr_wrong"}).status_code == 401


def test_push_and_audit_with_key_name(admin_client):
    add_console(admin_client)
    key = make_key(admin_client)
    auth = {"Authorization": f"Bearer {key}"}
    body = {"vehicles": [{"plate": "12bdf3", "department": "Netwerktransport", "location": "Wognum"}]}

    r = admin_client.post("/api/v1/vehicles", json={**body, "dry_run": True}, headers={**auth, "X-Requested-With": ""})
    assert r.status_code == 202 and r.json()["summary"]["new"] == 1
    r = admin_client.post("/api/v1/vehicles", json=body, headers=auth)
    job = admin_client.get(r.json()["status_url"], headers=auth).json()
    assert job["status"] == "done" and job["actor"] == "Lobster"
    assert access_mock.fake_for("wognum.local").plates() == {"12BDF3"}
    assert admin_client.get("/api/v1/vehicles", headers=auth).json()[0]["consoles"] == ["Wognum"]
    entries = admin_client.get("/api/audit?q=access.plate_assigned").json()["items"]
    assert entries[0]["actor_type"] == "api_key" and entries[0]["actor"] == "Lobster"

    # Deleting needs a key that allows it.
    assert admin_client.delete("/api/v1/vehicles/12-BDF-3", headers=auth).status_code == 403
    assert admin_client.post("/api/v1/vehicles", json={**body, "mode": "full"}, headers=auth).status_code == 403


def test_delete_with_permission(admin_client):
    add_console(admin_client)
    key = make_key(admin_client, allow_delete=True)
    auth = {"Authorization": f"Bearer {key}"}
    admin_client.post("/api/v1/vehicles", json={"vehicles": [{"plate": "12-BDF-3", "department": "Netwerktransport"}]}, headers=auth)
    r = admin_client.delete("/api/v1/vehicles/12bdf3", headers=auth)
    assert r.status_code == 202
    assert access_mock.fake_for("wognum.local").plates() == set()
    assert admin_client.get("/api/v1/vehicles", headers=auth).json() == []


def test_disabled_key_is_refused(admin_client):
    key = make_key(admin_client)
    [row] = admin_client.get("/api/api-keys").json()
    admin_client.patch(f"/api/api-keys/{row['id']}", json={"is_active": False})
    assert admin_client.get("/api/v1/vehicles", headers={"Authorization": f"Bearer {key}"}).status_code == 401
