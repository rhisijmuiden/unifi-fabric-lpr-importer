from app.services import access_mock


def add_console(client, name="Wognum", host="wognum.local", token="token-1"):
    r = client.post("/api/consoles", json={"name": name, "location": name, "host": host, "api_token": token})
    assert r.status_code == 201, r.text
    return r.json()


def test_console_crud_hides_token(admin_client):
    c = add_console(admin_client, host="https://10.0.0.5:12445/")
    assert c["host"] == "10.0.0.5" and c["api_token_set"] and "api_token" not in c
    r = admin_client.put(f"/api/consoles/{c['id']}", json={"name": "Wognum", "location": "Wognum", "host": "10.0.0.6"})
    assert r.json()["api_token_set"]  # token kept when omitted
    assert admin_client.post("/api/consoles", json={"name": "Wognum", "host": "x", "api_token": "t"}).status_code == 409
    assert admin_client.delete(f"/api/consoles/{c['id']}").status_code == 204


def test_connection_test(admin_client):
    access_mock.fake_for("wognum.local").add_user("Netwerktransport", "12-BDF-3", ["12-BDF-3"])
    r = admin_client.post("/api/consoles/test", json={"host": "wognum.local", "api_token": "good"})
    assert r.json() == {"ok": True, "users": 1, "groups": 0}
    r = admin_client.post("/api/consoles/test", json={"host": "wognum.local", "api_token": "invalid"})
    assert r.json()["ok"] is False and r.json()["code"] == "unauthorized"
    c = add_console(admin_client)
    r = admin_client.post("/api/consoles/test", json={"host": "wognum.local", "console_id": c["id"]})
    assert r.json()["ok"]
    r = admin_client.post(f"/api/consoles/{c['id']}/test")
    assert r.json()["ok"]
    assert admin_client.get("/api/consoles").json()[0]["last_test_ok"] is True


def test_scan_and_adopt(admin_client):
    fake = access_mock.fake_for("wognum.local")
    fake.add_user("Netwerktransport", "12-BDF-3", ["12-BDF-3"], ["Netwerktransport Wognum"])
    fake.add_user("Jan", "de Vries", ["VZ-482-K"])
    add_console(admin_client)
    job = admin_client.post("/api/consoles/scan", json={}).json()
    assert job["status"] == "done" and job["succeeded"] == 1
    candidates = {c["plate"]: c for c in admin_client.get("/api/vehicles/adopt").json()}
    assert candidates["12-BDF-3"]["department"] == "Netwerktransport"
    assert candidates["12-BDF-3"]["location"] == "Wognum"
    assert candidates["12-BDF-3"]["group_name"] == "Netwerktransport Wognum"
    assert candidates["VZ-482-K"]["follows_convention"] is False
    c = candidates["12-BDF-3"]
    r = admin_client.post("/api/vehicles/adopt", json={"items": [{k: c[k] for k in ("plate", "department", "location", "group_name")}]})
    assert r.json() == {"adopted": 1}
    data = admin_client.get("/api/vehicles").json()
    [vehicle] = data["items"]
    assert vehicle["source"] == "console" and str(data["consoles"][0]["id"]) in vehicle["presence"]
    assert [c["plate"] for c in admin_client.get("/api/vehicles/adopt").json()] == ["VZ-482-K"]


def test_operator_cannot_add_console(admin_client):
    admin_client.post("/api/users", json={"username": "op", "password": "long-enough-pw", "role": "operator"})
    admin_client.post("/api/auth/logout")
    admin_client.post("/api/auth/login", json={"username": "op", "password": "long-enough-pw"})
    assert admin_client.post("/api/consoles", json={"name": "x", "host": "x", "api_token": "t"}).status_code == 403
