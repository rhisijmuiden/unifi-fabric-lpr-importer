from app.services import access_mock
from tests.test_consoles import add_console


def setup_two(client):
    return add_console(client, "Wognum", "wognum.local"), add_console(client, "Zwaagdijk", "zwaagdijk.local")


def test_assign_creates_user_plate_and_group(admin_client):
    a, b = setup_two(admin_client)
    v = admin_client.post("/api/vehicles", json={"plate": "12bdf3", "department": "Netwerktransport", "location": "Wognum"}).json()
    assert v["plate"] == "12-BDF-3" and v["group_name"] == "Netwerktransport Wognum"
    job = admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]], "console_ids": [a["id"]]}).json()
    assert job["status"] == "done" and job["succeeded"] == 1 and job["failed"] == 0

    fake = access_mock.fake_for("wognum.local")
    [user] = fake.users.values()
    assert (user["first_name"], user["last_name"]) == ("Netwerktransport", "12-BDF-3")
    assert [p["credential"] for p in user["license_plates"]] == ["12BDF3"]  # compact by default
    [group] = fake.groups.values()
    assert group["name"] == "Netwerktransport Wognum" and user["id"] in group["members"]
    assert not access_mock.fake_for("zwaagdijk.local").users

    # Running it again changes nothing.
    job = admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]], "console_ids": [a["id"]]}).json()
    assert "unchanged" in admin_client.get(f"/api/jobs/{job['id']}").json()["log"][-1]["message"]
    assert len(fake.users) == 1

    presence = admin_client.get("/api/vehicles").json()["items"][0]["presence"]
    assert list(presence) == [str(a["id"])]

    actions = [e["action"] for e in admin_client.get("/api/audit?limit=100").json()["items"]]
    for action in ("access.user_created", "access.plate_assigned", "access.group_created", "access.group_member_added"):
        assert action in actions


def test_official_notation(admin_client):
    a, _ = setup_two(admin_client)
    admin_client.put("/api/settings/access", json={"plate_notation": "official", "delete_vehicle_users": True})
    v = admin_client.post("/api/vehicles", json={"plate": "vz482k", "department": "Distributie"}).json()
    admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]], "console_ids": [a["id"]]})
    assert access_mock.fake_for("wognum.local").plates() == {"VZ-482-K"}
    assert str(a["id"]) in admin_client.get("/api/vehicles").json()["items"][0]["presence"]


def test_remove_deletes_vehicle_user_and_audits(admin_client):
    a, b = setup_two(admin_client)
    v = admin_client.post("/api/vehicles", json={"plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum"}).json()
    admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]]})
    assert access_mock.fake_for("zwaagdijk.local").plates() == {"12BDF3"}
    # A person who also holds a plate is kept; only the plate goes.
    person = access_mock.fake_for("wognum.local").add_user("Jan", "de Vries", ["5-TXR-29"])
    w = admin_client.post("/api/vehicles", json={"plate": "5-TXR-29", "department": "Directie"}).json()

    job = admin_client.post("/api/vehicles/remove", json={"vehicle_ids": [v["id"], w["id"]], "console_ids": [a["id"]], "delete_vehicles": False}).json()
    assert job["status"] == "done" and job["failed"] == 0
    fake = access_mock.fake_for("wognum.local")
    assert fake.plates() == set()
    assert list(fake.users) == [person]
    assert access_mock.fake_for("zwaagdijk.local").plates() == {"12BDF3"}
    assert len(admin_client.get("/api/vehicles").json()["items"]) == 2

    admin_client.post("/api/vehicles/remove", json={"vehicle_ids": [v["id"]], "delete_vehicles": True})
    assert [i["plate"] for i in admin_client.get("/api/vehicles").json()["items"]] == ["5-TXR-29"]
    actions = [e["action"] for e in admin_client.get("/api/audit?limit=100").json()["items"]]
    assert "access.plate_removed" in actions and "access.user_deleted" in actions and "vehicle.deleted" in actions


def test_unreachable_console_is_reported(admin_client):
    a, _ = setup_two(admin_client)
    admin_client.put(f"/api/consoles/{a['id']}", json={"name": "Wognum", "host": "wognum.local", "api_token": "invalid"})
    v = admin_client.post("/api/vehicles", json={"plate": "12-BDF-3", "department": "Netwerktransport"}).json()
    job = admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]]}).json()
    assert job["status"] == "done" and job["failed"] == 1 and job["succeeded"] == 1


def test_bulk_edit_regroups(admin_client):
    ids = [admin_client.post("/api/vehicles", json={"plate": p, "department": "Netwerktransport"}).json()["id"] for p in ("12-BDF-3", "VZ-482-K")]
    admin_client.post("/api/vehicles/bulk-edit", json={"vehicle_ids": ids, "location": "Wognum"})
    groups = {i["group_name"] for i in admin_client.get("/api/vehicles").json()["items"]}
    assert groups == {"Netwerktransport Wognum"}
    assert admin_client.get("/api/vehicles/filters").json()["locations"] == ["Wognum"]


def test_stats(admin_client):
    a, _ = setup_two(admin_client)
    v = admin_client.post("/api/vehicles", json={"plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum"}).json()
    admin_client.post("/api/vehicles", json={"plate": "VZ-482-K", "department": "Distributie", "location": "Wognum"})
    admin_client.post("/api/vehicles/assign", json={"vehicle_ids": [v["id"]], "console_ids": [a["id"]]})
    s = admin_client.get("/api/stats").json()
    assert s["vehicles"] == 2
    assert {d["name"] for d in s["departments"]} == {"Netwerktransport", "Distributie"}
    wognum = next(c for c in s["consoles"] if c["name"] == "Wognum")
    assert (wognum["present"], wognum["missing"]) == (1, 1)
    assert s["totals_30d"]["added"] == 1
