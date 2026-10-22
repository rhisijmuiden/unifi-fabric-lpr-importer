from app.services import access_mock
from tests.test_consoles import add_console

CSV = "Kenteken;Afdeling;Standplaats;Merk\n12bdf3;Netwerktransport;Wognum;DAF\nvz-482-k;Netwerktransport;Zwaagdijk;Volvo\n;Netwerktransport;Wognum;x\n12-BDF-3;Netwerktransport;Wognum;dup\n"


def test_parse_suggests_mapping(admin_client):
    r = admin_client.post("/api/import/parse", files={"file": ("lijst.csv", CSV.encode("cp1252"), "text/csv")})
    data = r.json()
    assert data["headers"] == ["Kenteken", "Afdeling", "Standplaats", "Merk"]
    assert data["mapping"] == {"plate": "Kenteken", "department": "Afdeling", "location": "Standplaats", "description": "Merk"}
    assert len(data["rows"]) == 4


def rows():
    return [
        {"plate": "12bdf3", "department": "Netwerktransport", "location": "Wognum", "description": "DAF"},
        {"plate": "vz-482-k", "department": "Netwerktransport", "location": "Zwaagdijk"},
        {"plate": "", "department": "Netwerktransport"},
        {"plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum"},
        {"plate": "41-VLP-7", "department": ""},
    ]


def test_preview_and_run(admin_client):
    c = add_console(admin_client)
    plan = admin_client.post("/api/import/preview", json={"rows": rows(), "console_ids": [c["id"]]}).json()
    assert [r["status"] for r in plan["rows"]] == ["new", "new", "invalid", "invalid", "invalid"]
    assert [r["error"] for r in plan["rows"]][2:] == ["invalid_plate", "duplicate", "missing_department"]
    assert plan["summary"]["groups"] == ["Netwerktransport Wognum", "Netwerktransport Zwaagdijk"]
    assert plan["consoles"][0]["add"] == 2

    job = admin_client.post("/api/import/run", json={"rows": rows(), "console_ids": [c["id"]]}).json()
    assert job["status"] == "done", admin_client.get(f"/api/jobs/{job['id']}").json()
    assert access_mock.fake_for("wognum.local").plates() == {"12BDF3", "VZ482K"}
    groups = {g["name"] for g in access_mock.fake_for("wognum.local").groups.values()}
    assert groups == {"Netwerktransport Wognum", "Netwerktransport Zwaagdijk"}

    plan = admin_client.post("/api/import/preview", json={"rows": rows()[:2], "console_ids": [c["id"]]}).json()
    assert [r["status"] for r in plan["rows"]] == ["unchanged", "unchanged"]
    assert plan["consoles"][0] == {**plan["consoles"][0], "add": 0, "present": 2}


def test_full_sync_removes_missing_of_same_department(admin_client):
    c = add_console(admin_client)
    admin_client.post("/api/import/run", json={"rows": rows()[:2] + [{"plate": "41-VLP-7", "department": "Distributie"}], "console_ids": [c["id"]]})
    plan = admin_client.post("/api/import/preview", json={"rows": rows()[:1], "console_ids": [c["id"]], "mode": "full"}).json()
    assert plan["remove"] == ["VZ-482-K"]  # Distributie is not in the source, so it stays
    admin_client.post("/api/import/run", json={"rows": rows()[:1], "console_ids": [c["id"]], "mode": "full"})
    assert access_mock.fake_for("wognum.local").plates() == {"12BDF3", "41VLP7"}
    assert sorted(v["plate"] for v in admin_client.get("/api/vehicles").json()["items"]) == ["12-BDF-3", "41-VLP-7"]
