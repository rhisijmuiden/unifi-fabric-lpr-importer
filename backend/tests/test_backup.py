import datetime as dt
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
from pyftpdlib.servers import ThreadedFTPServer
from sqlalchemy import select

from app import db as app_db
from app.config import get_settings
from app.models import Console, Setting, Vehicle
from app.security import decrypt, encrypt
from app.services import backup, scheduler
from app.services.remote import RemoteFile

PASSPHRASE = "correct horse battery staple"
SCHEDULE_OFF = {"enabled": False, "frequency": "daily", "time": "02:00", "weekday": 6, "monthday": 1}


def _self_signed(path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
        + key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )


@pytest.fixture(params=["ftp", "ftps"])
def ftp_server(request, tmp_path):
    root = tmp_path / "ftp-root"
    root.mkdir()
    authorizer = DummyAuthorizer()
    authorizer.add_user("backup", "secret-pass", str(root), perm="elradfmwMT")
    if request.param == "ftps":
        cert = tmp_path / "cert.pem"
        _self_signed(cert)
        handler = type("Handler", (TLS_FTPHandler,), {"certfile": str(cert), "tls_control_required": True, "tls_data_required": True})
    else:
        handler = type("Handler", (FTPHandler,), {})
    handler.authorizer = authorizer
    server = ThreadedFTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"timeout": 0.1}, daemon=True)
    thread.start()
    yield {"protocol": request.param, "port": server.address[1], "root": root}
    server.close_all()


def _setup(admin_client, server):
    r = admin_client.put(
        "/api/backup/settings",
        json={"passphrase": PASSPHRASE, "keep_full": 2, "schedule_full": SCHEDULE_OFF, "schedule_incremental": SCHEDULE_OFF},
    )
    assert r.status_code == 200, r.text
    assert r.json()["passphrase_set"] is True
    assert "passphrase" not in r.json()
    assert r.json()["ssh_public_key"].startswith("ssh-ed25519 ")
    body = {
        "name": "NAS",
        "protocol": server["protocol"],
        "host": "127.0.0.1",
        "port": server["port"],
        "username": "backup",
        "password": "secret-pass",
        "remote_path": "backups/lpr",
        "verify_tls": False,
    }
    test = admin_client.post("/api/backup/targets/test", json=body)
    assert test.json()["ok"] is True, test.json()
    r = admin_client.post("/api/backup/targets", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["password_set"] is True
    return r.json()["id"]


def _run(admin_client, kind):
    r = admin_client.post("/api/backup/run", json={"kind": kind})
    assert r.status_code == 202, r.text
    job = admin_client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "done", job
    assert job["failed"] == 0, job
    return job


def _plates(db):
    db.expire_all()
    return sorted(v.plate_key for v in db.scalars(select(Vehicle)))


def test_full_incremental_and_restore(admin_client, db, ftp_server):
    target_id = _setup(admin_client, ftp_server)
    db.add(Vehicle(plate="12-BDF-3", plate_key="12BDF3", department="Netwerktransport"))
    db.add(Console(name="Wognum", host="10.0.0.1", api_token=encrypt("token-1")))
    db.commit()

    _run(admin_client, "full")
    db.add(Vehicle(plate="34-XYZ-5", plate_key="34XYZ5", department="Netwerktransport"))
    db.commit()
    _run(admin_client, "incremental")
    db.delete(db.scalar(select(Vehicle).where(Vehicle.plate_key == "12BDF3")))
    db.commit()
    _run(admin_client, "incremental")

    files = sorted((p.name for p in (ftp_server["root"] / "backups" / "lpr").iterdir()), key=lambda n: backup.parse_name(n).stamp)
    assert len(files) == 3
    assert [backup.parse_name(f).kind for f in files] == ["full", "incr", "incr"]
    # Encrypted: no plate in clear text.
    assert b"12BDF3" not in (ftp_server["root"] / "backups" / "lpr" / files[0]).read_bytes()

    listing = admin_client.get(f"/api/backup/targets/{target_id}/backups").json()["items"]
    assert [i["kind"] for i in listing] == ["incremental", "incremental", "full"]
    assert all(i["restorable"] for i in listing)
    assert listing[0]["chain_length"] == 3

    # Change things after the last backup, then go back in time step by step.
    db.add(Vehicle(plate="99-AAA-9", plate_key="99AAA9", department="Other"))
    db.commit()
    assert _plates(db) == ["34XYZ5", "99AAA9"]

    def restore(name):
        r = admin_client.post("/api/backup/restore", json={"target_id": target_id, "name": name, "confirm": True})
        assert r.status_code == 202, r.text
        job = admin_client.get(f"/api/jobs/{r.json()['id']}").json()
        assert job["status"] == "done", job
        return job

    restore(listing[1]["name"])  # first incremental: both vehicles
    assert _plates(db) == ["12BDF3", "34XYZ5"]
    restore(listing[2]["name"])  # full: one vehicle
    assert _plates(db) == ["12BDF3"]
    job = restore(listing[0]["name"])  # newest
    assert _plates(db) == ["34XYZ5"]
    assert job["result"]["chain"] == [i["name"] for i in reversed(listing)]

    # Still signed in, the console token still readable, the restore is in the audit log.
    assert admin_client.get("/api/auth/me").status_code == 200
    console = db.scalar(select(Console))
    assert decrypt(console.api_token) == "token-1"
    audit = admin_client.get("/api/audit", params={"action": "backup.restore"}).json()
    assert any(e["action"] == "backup.restore" for e in audit.get("items", audit))

    # The next incremental starts a new chain with a full backup.
    job = _run(admin_client, "incremental")
    assert any("full backup instead" in e["message"] for e in job["log"])


def test_retention_keeps_newest_full_backups(admin_client, ftp_server):
    _setup(admin_client, ftp_server)
    for kind in ("full", "incremental", "full", "incremental", "full"):
        _run(admin_client, kind)
    names = sorted((p.name for p in (ftp_server["root"] / "backups" / "lpr").iterdir()), key=lambda n: backup.parse_name(n).stamp)
    kinds = [backup.parse_name(n).kind for n in names]
    # keep_full = 2: the first full backup and its incremental are gone.
    assert kinds == ["full", "incr", "full"]


def test_wrong_passphrase_and_upload_restore(admin_client, db, ftp_server):
    target_id = _setup(admin_client, ftp_server)
    db.add(Vehicle(plate="12-BDF-3", plate_key="12BDF3", department="Netwerktransport"))
    db.commit()
    _run(admin_client, "full")
    name = admin_client.get(f"/api/backup/targets/{target_id}/backups").json()["items"][0]["name"]
    data = admin_client.get(f"/api/backup/targets/{target_id}/backups/{name}").content
    assert data.startswith(backup.MAGIC)

    db.delete(db.scalar(select(Vehicle)))
    db.commit()
    files = {"files": (name, data, "application/octet-stream")}
    r = admin_client.post("/api/backup/restore/upload", files=files, data={"passphrase": "not the passphrase", "confirm": "true"})
    job = admin_client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "failed"
    assert "Wrong passphrase" in job["log"][-1]["message"]
    assert _plates(db) == []

    r = admin_client.post("/api/backup/restore/upload", files=files, data={"passphrase": PASSPHRASE, "confirm": "true"})
    assert admin_client.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done"
    assert _plates(db) == ["12BDF3"]


def test_restore_requires_confirmation(admin_client, ftp_server):
    target_id = _setup(admin_client, ftp_server)
    r = admin_client.post("/api/backup/restore", json={"target_id": target_id, "name": "x", "confirm": False})
    assert r.status_code == 400


def test_backup_without_passphrase_fails(admin_client):
    r = admin_client.post("/api/backup/run", json={"kind": "full"})
    job = admin_client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "failed"


def test_target_test_reports_login_failure(admin_client, ftp_server):
    r = admin_client.post(
        "/api/backup/targets/test",
        json={"protocol": ftp_server["protocol"], "host": "127.0.0.1", "port": ftp_server["port"], "username": "backup", "password": "wrong", "verify_tls": False},
    )
    assert r.json()["ok"] is False
    assert r.json()["code"] == "login_failed"


def test_restore_on_another_server_reencrypts_secrets(app_env, db, monkeypatch):
    db.add(Console(name="Wognum", host="10.0.0.1", api_token=encrypt("token-1")))
    db.add(Setting(key="smtp", value={"password": encrypt("mail-pass"), "host": "smtp.example.com"}))
    db.commit()
    snapshot = backup.take_snapshot(db)
    payload, _, _ = backup._payload(snapshot, None)
    name = backup.make_name("full")
    manifest = {"format": backup.FORMAT, "name": name, "kind": "full", "parent": None, "revision": snapshot.revision}
    blob = backup.encrypt_blob(backup.build_archive(manifest, payload, {"secret_key": "test-secret"}), PASSPHRASE)

    # A fresh server: other secret key, empty database.
    monkeypatch.setenv("LPR_SECRET_KEY", "another-secret")
    get_settings.cache_clear()
    db.query(Console).delete()
    db.query(Setting).delete()
    db.commit()

    loaded = backup.load_backup(name, [name], {name: blob}.__getitem__, PASSPHRASE)
    result = backup.apply_backup(loaded)
    assert result["secrets_lost"] == 0
    db.expire_all()
    assert decrypt(db.scalar(select(Console)).api_token) == "token-1"
    assert decrypt(db.get(Setting, "smtp").value["password"]) == "mail-pass"


def test_restore_older_schema_runs_migrations(tmp_path, monkeypatch):
    """A backup made before an upgrade is loaded into its own schema version, then migrated."""
    from alembic import command

    monkeypatch.setenv("LPR_DATABASE_URL", f"sqlite:///{tmp_path / 'migrated.db'}")
    monkeypatch.setenv("LPR_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LPR_STATE_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    app_db.reset_engine()
    try:
        command.upgrade(backup._alembic_config(), "0002")
        session = next(app_db.get_db())
        engine = app_db.get_engine()
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO vehicles (plate, plate_key, department, location, group_name, description, source, created_at, updated_at) "
                "VALUES ('12-BDF-3', '12BDF3', 'Netwerktransport', '', '', '', 'manual', '2026-10-01 10:00:00', '2026-10-01 10:00:00')"
            )
        snapshot = backup.take_snapshot(session)
        assert snapshot.revision == "0002"
        assert "backup_targets" not in snapshot.tables
        payload, _, _ = backup._payload(snapshot, None)
        name = backup.make_name("full")
        manifest = {"format": backup.FORMAT, "name": name, "kind": "full", "parent": None, "revision": "0002"}
        blob = backup.encrypt_blob(backup.build_archive(manifest, payload, {"secret_key": "test-secret"}), PASSPHRASE)
        session.close()

        command.upgrade(backup._alembic_config(), "head")
        with engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM vehicles")
            conn.exec_driver_sql("INSERT INTO jobs (kind, status, actor_type, actor, params, total, processed, succeeded, failed, log, created_at) VALUES ('restore', 'running', 'user', 'admin', '{}', 0, 0, 0, 0, '[]', '2026-10-22 10:00:00')")

        loaded = backup.load_backup(name, [name], {name: blob}.__getitem__, PASSPHRASE)
        backup.apply_backup(loaded)
        with engine.connect() as conn:
            assert backup.current_revision(conn) is not None and backup.current_revision(conn) != "0002"
            assert conn.exec_driver_sql("SELECT plate_key FROM vehicles").scalars().all() == ["12BDF3"]
            assert conn.exec_driver_sql("SELECT count(*) FROM backup_targets").scalar() == 0
            assert conn.exec_driver_sql("SELECT count(*) FROM jobs").scalar() == 1  # the running restore job survives
    finally:
        app_db.reset_engine()
        get_settings.cache_clear()


def test_backup_newer_than_app_is_refused(app_env, db):
    loaded = backup.LoadedBackup("x", "9999", {}, "", ["x"])
    with pytest.raises(backup.BackupError) as exc:
        backup.apply_backup(loaded)
    assert exc.value.code == "backup_newer"


# ---------------------------------------------------------------- pure functions


def test_names_chain_and_prune():
    full1 = "lpr_20261001T020000Z_full.lprbak"
    inc1 = "lpr_20261002T020000Z_incr_20261001T020000Z.lprbak"
    inc2 = "lpr_20261003T020000Z_incr_20261002T020000Z.lprbak"
    full2 = "lpr_20261008T020000Z_full.lprbak"
    inc3 = "lpr_20261009T020000Z_incr_20261008T020000Z.lprbak"
    orphan = "lpr_20261010T020000Z_incr_20261005T020000Z.lprbak"
    names = [full1, inc1, inc2, full2, inc3, orphan, "notes.txt"]
    assert [p.name for p in backup.chain_of(inc2, names)] == [full1, inc1, inc2]
    assert backup.chain_of(orphan, names) is None
    assert backup.plan_prune(names, 2) == []
    assert backup.plan_prune(names, 1) == [full1, inc1, inc2]
    items = backup.catalog([RemoteFile(n, 10) for n in names])
    assert [i["name"] for i in items][0] == orphan
    assert items[0]["restorable"] is False
    assert backup.parse_name("lpr_20261010T020000Z_incr.lprbak") is None


def test_incremental_name_is_after_parent():
    parent = backup.parse_name("lpr_29991231T235959Z_full.lprbak")
    name = backup.parse_name(backup.make_name("incr", parent))
    assert name.stamp > parent.stamp and name.parent == parent.stamp


def test_encryption_roundtrip():
    blob = backup.encrypt_blob(b"hello", PASSPHRASE)
    assert backup.decrypt_blob(blob, PASSPHRASE) == b"hello"
    with pytest.raises(backup.BackupError) as exc:
        backup.decrypt_blob(blob, "wrong passphrase!")
    assert exc.value.code == "wrong_passphrase"
    with pytest.raises(backup.BackupError) as exc:
        backup.decrypt_blob(b"PK\x03\x04 a zip file", PASSPHRASE)
    assert exc.value.code == "not_a_backup"


def test_schedule_slots():
    now = dt.datetime(2026, 10, 22, 10, 30)  # a Thursday
    daily = {"frequency": "daily", "time": "02:00"}
    assert scheduler.last_slot(daily, now) == dt.datetime(2026, 10, 22, 2, 0)
    assert scheduler.next_slot(daily, now) == dt.datetime(2026, 10, 23, 2, 0)
    weekly = {"frequency": "weekly", "time": "03:15", "weekday": 6}
    assert scheduler.last_slot(weekly, now) == dt.datetime(2026, 10, 18, 3, 15)
    assert scheduler.next_slot(weekly, now) == dt.datetime(2026, 10, 25, 3, 15)
    hourly = {"frequency": "hourly", "time": "00:45"}
    assert scheduler.last_slot(hourly, now) == dt.datetime(2026, 10, 22, 9, 45)
    assert scheduler.next_slot(hourly, now) == dt.datetime(2026, 10, 22, 10, 45)
    monthly = {"frequency": "monthly", "time": "01:00", "monthday": 28}
    assert scheduler.last_slot(monthly, now) == dt.datetime(2026, 9, 28, 1, 0)
    assert scheduler.next_slot(monthly, now) == dt.datetime(2026, 10, 28, 1, 0)


def test_schedule_due_kinds():
    cfg = {
        "schedule_full": {"enabled": True, "frequency": "weekly", "time": "02:00", "weekday": 6},
        "schedule_incremental": {"enabled": True, "frequency": "daily", "time": "02:00"},
    }
    state: dict = {}
    sunday = dt.datetime(2026, 10, 25, 1, 0)
    assert scheduler.due_kinds(cfg, state, sunday) == []  # armed, nothing runs at once
    assert scheduler.due_kinds(cfg, state, sunday.replace(hour=2, minute=1)) == ["full"]  # full wins
    assert scheduler.due_kinds(cfg, state, sunday.replace(hour=3)) == []
    assert scheduler.due_kinds(cfg, state, dt.datetime(2026, 10, 26, 2, 0, 30)) == ["incremental"]
    # Switched off for days: missed runs older than the catch-up window are skipped.
    assert scheduler.due_kinds(cfg, state, dt.datetime(2026, 10, 30, 23, 0)) == []
