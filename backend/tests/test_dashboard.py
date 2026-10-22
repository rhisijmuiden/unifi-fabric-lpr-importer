from datetime import datetime

from app.services import scheduler
from tests.test_consoles import add_console


def test_dashboard_status_per_location(admin_client):
    wognum = add_console(admin_client)
    add_console(admin_client, name="Hoorn", host="hoorn.local", token="token-2")
    rows = [{"plate": "12-BDF-3", "department": "Netwerktransport", "location": "Wognum"}]
    admin_client.post("/api/import/run", json={"rows": rows, "console_ids": [wognum["id"]]})
    admin_client.post("/api/consoles/scan", json={"console_ids": None})

    data = admin_client.get("/api/dashboard").json()
    assert data["vehicles"] == 1
    by_name = {loc["name"]: loc for loc in data["locations"]}
    assert by_name["Wognum"]["status"] == "ok"
    assert by_name["Wognum"]["present"] == 1 and by_name["Wognum"]["changes_7d"] >= 1
    assert by_name["Hoorn"]["status"] == "warning" and by_name["Hoorn"]["missing"] == 1
    assert [s["kind"] for s in data["syncs"]][:2] == ["scan", "import"]
    assert data["syncs"][1]["source"] == "csv"
    assert data["backup"] == {"targets": 0, "failed": 0, "last_backup_at": None}


def test_scan_schedule(admin_client):
    add_console(admin_client)
    settings = admin_client.get("/api/settings/access").json()
    assert settings["scan_schedule"]["enabled"] and settings["next_scan"]
    now = datetime(2026, 10, 22, 12, 20)
    state = {}
    scheduler.is_due(settings["scan_schedule"], "scan", state, datetime(2026, 10, 22, 10, 20))
    scheduler._save(state)
    assert scheduler.scan_tick(now) is True
    assert scheduler.scan_tick(now) is False

    r = admin_client.put("/api/settings/access", json={**settings, "scan_schedule": {**settings["scan_schedule"], "enabled": False}})
    assert r.json()["next_scan"] is None and r.json()["plate_notation"] == settings["plate_notation"]
