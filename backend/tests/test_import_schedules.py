import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

from app.models import ImportSchedule
from app.services import access_mock, scheduler
from tests.test_consoles import add_console

CSV = "Kenteken;Afdeling;Standplaats\n12bdf3;Netwerktransport;Wognum\nvz-482-k;Netwerktransport;Zwaagdijk\n41-vlp-7;Netwerktransport;Hoorn\n"
DAILY = {"enabled": True, "frequency": "daily", "time": "06:00", "weekday": 0, "monthday": 1}


@pytest.fixture
def ftp(tmp_path):
    root = tmp_path / "ftp-root"
    (root / "export").mkdir(parents=True)
    (root / "export" / "voertuigen.csv").write_text(CSV, encoding="utf-8")
    authorizer = DummyAuthorizer()
    authorizer.add_user("lobster", "secret-pass", str(root), perm="elr")
    handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
    server = ThreadedFTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, kwargs={"timeout": 0.1}, daemon=True).start()
    yield {"port": server.address[1], "file": root / "export" / "voertuigen.csv"}
    server.close_all()


@pytest.fixture
def http():
    state = {"body": CSV.encode(), "auth": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["auth"] = self.headers.get("authorization")
            if self.path != "/export.csv":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.end_headers()
            self.wfile.write(state["body"])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"url": f"http://127.0.0.1:{server.server_address[1]}/export.csv", "state": state}
    server.shutdown()


def body(ftp, **extra):
    return {
        "name": "Lobster export",
        "protocol": "ftp",
        "host": "127.0.0.1",
        "port": ftp["port"],
        "username": "lobster",
        "password": "secret-pass",
        "remote_path": "export",
        "filename": "voertuigen.csv",
        "mapping": {"plate": "Kenteken", "department": "Afdeling", "location": "Standplaats"},
        "schedule": DAILY,
        **extra,
    }


def test_test_shows_columns_and_plan(admin_client, ftp):
    add_console(admin_client)
    r = admin_client.post("/api/import/schedules/test", json=body(ftp, filter_locations=["wognum", "Zwaagdijk"]))
    data = r.json()
    assert data["ok"], data
    assert data["headers"] == ["Kenteken", "Afdeling", "Standplaats"]
    assert data["suggested"]["plate"] == "Kenteken"
    assert data["summary"]["new"] == 2  # Hoorn is filtered out
    assert data["consoles"][0]["add"] == 2

    wrong = admin_client.post("/api/import/schedules/test", json=body(ftp, filename="missing.csv")).json()
    assert wrong == {**wrong, "ok": False, "code": "not_found"}
    login = admin_client.post("/api/import/schedules/test", json=body(ftp, password="nope")).json()
    assert login["code"] == "login_failed"


def test_create_run_skip_unchanged_and_secret(admin_client, ftp, db):
    add_console(admin_client)
    created = admin_client.post("/api/import/schedules", json=body(ftp))
    assert created.status_code == 201, created.text
    sched = created.json()
    assert sched["password_set"] and "password" not in sched
    assert sched["next_run"]
    stored = db.get(ImportSchedule, sched["id"])
    assert stored.password and "secret-pass" not in stored.password  # encrypted at rest

    job = admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()
    assert job["status"] == "done", admin_client.get(f"/api/jobs/{job['id']}").json()
    assert access_mock.fake_for("wognum.local").plates() == {"12BDF3", "VZ482K", "41VLP7"}
    vehicles = admin_client.get("/api/vehicles").json()["items"]
    assert {v["source"] for v in vehicles} == {"schedule"}

    # Scheduled run with the same file: skipped. A changed file is imported.
    now = datetime.now().replace(hour=6, minute=30)
    state = {}
    scheduler.is_due(DAILY, f"import:{sched['id']}", state, now - timedelta(days=2))
    scheduler._save(state)
    assert scheduler.import_tick(now) == ["Lobster export"]
    listed = admin_client.get("/api/import/schedules").json()[0]
    assert listed["last_status"] == "unchanged"
    assert scheduler.import_tick(now) == []  # already ran for this slot

    ftp["file"].write_text(CSV + "99-XX-99;Distributie;Wognum\n", encoding="utf-8")
    job = admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()
    assert job["status"] == "done"
    assert "99XX99" in access_mock.fake_for("wognum.local").plates()
    assert admin_client.get("/api/import/schedules").json()[0]["last_status"] == "ok"


def test_full_sync_removal_limit(admin_client, ftp):
    add_console(admin_client)
    sched = admin_client.post("/api/import/schedules", json=body(ftp, mode="full", max_remove=1)).json()
    assert admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()["status"] == "done"

    ftp["file"].write_text("Kenteken;Afdeling;Standplaats\n12bdf3;Netwerktransport;Wognum\n", encoding="utf-8")
    job = admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()
    assert job["status"] == "failed"
    assert access_mock.fake_for("wognum.local").plates() == {"12BDF3", "VZ482K", "41VLP7"}  # nothing removed
    listed = admin_client.get("/api/import/schedules").json()[0]
    assert listed["last_status"] == "failed" and "limit of 1" in listed["last_message"]

    # An empty export never wipes the vehicles.
    ftp["file"].write_text("Kenteken;Afdeling;Standplaats\n", encoding="utf-8")
    assert admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()["status"] == "failed"
    assert len(admin_client.get("/api/vehicles").json()["items"]) == 3


def test_url_source_with_basic_auth(admin_client, http):
    add_console(admin_client)
    payload = {
        "name": "Web export",
        "protocol": "url",
        "url": http["url"],
        "username": "lpr",
        "password": "pw",
        "mapping": {"plate": "Kenteken", "location": "Standplaats"},
        "defaults": {"department": "Netwerktransport"},
        "schedule": DAILY,
    }
    sched = admin_client.post("/api/import/schedules", json=payload).json()
    job = admin_client.post(f"/api/import/schedules/{sched['id']}/run").json()
    assert job["status"] == "done", admin_client.get(f"/api/jobs/{job['id']}").json()
    assert http["state"]["auth"].startswith("Basic ")
    assert len(access_mock.fake_for("wognum.local").plates()) == 3


def test_validation_and_roles(admin_client, ftp):
    assert admin_client.post("/api/import/schedules", json=body(ftp, mapping={})).json()["detail"] == "plate_column_required"
    assert admin_client.post("/api/import/schedules", json={**body(ftp), "protocol": "url", "url": "file:///etc/passwd"}).json()["detail"] == "invalid_url"
    assert admin_client.post("/api/import/schedules", json=body(ftp, mapping={"plate": "Kenteken"})).json()["detail"] == "department_required"
