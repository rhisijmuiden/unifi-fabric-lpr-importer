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
    assert r.status_code == 200 and r.json()["summary"]["new"] == 1
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


def test_status_filters_and_single_vehicle(admin_client):
    add_console(admin_client)
    key = make_key(admin_client)
    auth = {"Authorization": f"Bearer {key}"}
    status = admin_client.get("/api/v1/status", headers=auth).json()
    assert status["status"] == "ok" and status["key"] == "Lobster" and status["consoles"] == 1 and status["allow_delete"] is False
    vehicles = [
        {"plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum"},
        {"plate": "VZ-482-K", "department": "Werkplaats", "location": "Zwaagdijk"},
    ]
    admin_client.post("/api/v1/vehicles", json={"vehicles": vehicles}, headers=auth)
    assert [v["plate"] for v in admin_client.get("/api/v1/vehicles?department=Werkplaats", headers=auth).json()] == ["VZ-482-K"]
    one = admin_client.get("/api/v1/vehicles/12bdf3", headers=auth).json()
    assert one["plate"] == "12-BDF-3" and one["consoles"] == ["Wognum"] and one["source"] == "api"
    assert admin_client.get("/api/v1/vehicles/99-XXX-9", headers=auth).status_code == 404


def test_idempotency_key_returns_same_job(admin_client):
    key = make_key(admin_client)
    auth = {"Authorization": f"Bearer {key}", "Idempotency-Key": "delivery-1"}
    body = {"vehicles": [{"plate": "12-BDF-3", "department": "Netwerktransport"}], "consoles": []}
    first = admin_client.post("/api/v1/vehicles", json=body, headers=auth)
    again = admin_client.post("/api/v1/vehicles", json=body, headers=auth)
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"] and again.json()["replayed"] is True
    other = admin_client.post("/api/v1/vehicles", json=body, headers={**auth, "Idempotency-Key": "delivery-2"})
    assert other.status_code == 202 and other.json()["job_id"] != first.json()["job_id"]


def test_ip_allowlist(admin_client):
    r = admin_client.post("/api/api-keys", json={"name": "Lobster", "allowed_ips": ["10.0.0.0/8"]})
    assert r.status_code == 201 and r.json()["allowed_ips"] == ["10.0.0.0/8"]
    auth = {"Authorization": f"Bearer {r.json()['key']}"}
    # The test client connects from "testclient", which is in no network.
    assert admin_client.get("/api/v1/status", headers=auth).status_code == 403
    admin_client.patch(f"/api/api-keys/{r.json()['id']}", json={"allowed_ips": []})
    assert admin_client.get("/api/v1/status", headers=auth).status_code == 200
    assert admin_client.post("/api/api-keys", json={"name": "Bad", "allowed_ips": ["not-an-ip"]}).status_code == 400


def test_ip_allowed():
    from app.deps import ip_allowed

    assert ip_allowed("10.1.2.3", ["10.0.0.0/8"])
    assert ip_allowed("::ffff:10.1.2.3", ["10.0.0.0/8"])
    assert not ip_allowed("192.168.1.1", ["10.0.0.0/8", "172.16.0.1"])
    assert ip_allowed("172.16.0.1", ["172.16.0.1"])


def test_too_long_department_is_skipped(admin_client):
    key = make_key(admin_client)
    auth = {"Authorization": f"Bearer {key}"}
    body = {"vehicles": [{"plate": "12-BDF-3", "department": "x" * 101}], "dry_run": True}
    assert admin_client.post("/api/v1/vehicles", json=body, headers=auth).json()["invalid"][0]["error"] == "too_long"


def test_openapi_lists_v1_paths(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for path in ("/api/v1/status", "/api/v1/vehicles", "/api/v1/vehicles/{plate}", "/api/v1/jobs/{job_id}", "/api/v1/consoles"):
        assert path in paths


def test_published_openapi_is_current(app_env):
    """docs/openapi-v1.json is what the supplier gets; regenerate with `python -m app.cli openapi --output ../docs/openapi-v1.json`."""
    import json
    from pathlib import Path

    from app.main import create_app
    from app.routers.public_api import v1_openapi

    published = json.loads((Path(__file__).resolve().parents[2] / "docs" / "openapi-v1.json").read_text())
    assert published == json.loads(json.dumps(v1_openapi(create_app())))
