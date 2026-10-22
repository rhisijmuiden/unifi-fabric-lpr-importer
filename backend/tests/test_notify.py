import pytest

from app.services import notify
from app.settings_store import update_section
from tests.test_consoles import add_console


@pytest.fixture
def mails(monkeypatch):
    sent = []

    async def fake_send(cfg, to, subject, text, html=None):
        sent.append({"to": to, "subject": subject, "text": text})

    monkeypatch.setattr(notify, "send_mail", fake_send)
    return sent


def configure(db, **changes):
    update_section(db, "smtp", {"host": "smtp.example.com", "from_address": "lpr@example.com"})
    update_section(db, "notifications", {"recipients": "ops@example.com, it@example.com", **changes})


def push(client, key, vehicles):
    return client.post("/api/v1/vehicles", json={"vehicles": vehicles}, headers={"Authorization": f"Bearer {key}"})


def make_key(client):
    return client.post("/api/api-keys", json={"name": "Lobster"}).json()["key"]


def test_settings_roundtrip(admin_client):
    r = admin_client.put("/api/settings/notifications", json={"recipients": "ops@example.com", "import_report": "always", "sync_failure": True, "update_available": False})
    assert r.status_code == 200 and r.json()["import_report"] == "always"
    assert admin_client.put("/api/settings/notifications", json={"recipients": "nope"}).status_code == 400


def test_import_report_always(admin_client, db, mails):
    configure(db, import_report="always")
    add_console(admin_client)
    push(admin_client, make_key(admin_client), [{"plate": "12-BDF-3", "department": "Netwerktransport"}])
    assert len(mails) == 1
    assert mails[0]["to"] == "ops@example.com, it@example.com"
    assert mails[0]["subject"].startswith("Import completed") and "Lobster" in mails[0]["text"] and "Gestart door" in mails[0]["text"]


def test_import_report_only_on_failure(admin_client, db, mails):
    configure(db, import_report="failure")
    add_console(admin_client)
    push(admin_client, make_key(admin_client), [{"plate": "12-BDF-3", "department": "Netwerktransport"}])
    assert mails == []


def test_sync_failure(admin_client, db, mails, monkeypatch):
    configure(db, import_report="never")
    add_console(admin_client)
    from app.services import sync

    def broken(*args, **kwargs):
        raise RuntimeError("console offline")

    monkeypatch.setattr(sync, "assign", broken)
    push(admin_client, make_key(admin_client), [{"plate": "12-BDF-3", "department": "Netwerktransport"}])
    assert len(mails) == 1 and mails[0]["subject"].startswith("Sync failed")
    assert "console offline" in mails[0]["text"]


def test_no_mail_without_recipients(admin_client, db, mails):
    update_section(db, "smtp", {"host": "smtp.example.com", "from_address": "lpr@example.com"})
    update_section(db, "notifications", {"import_report": "always"})
    push(admin_client, make_key(admin_client), [{"plate": "12-BDF-3", "department": "Netwerktransport"}])
    assert mails == []


def test_update_notification_once_per_commit(app_env, db, mails, monkeypatch):
    from app.services import updater

    configure(db)
    check = {"current": {"version": "0.4.0", "channel": "test", "commit": "aaa"}, "channels": {"test": {"version": "0.4.1", "commit": "bbb", "update_available": True}}}
    monkeypatch.setattr(updater, "check_for_updates", lambda: check)
    assert notify.check_update(db, force=True) is True
    assert mails[0]["subject"].startswith("Update available: 0.4.1")
    assert notify.check_update(db, force=True) is False
    # Not again within six hours, even for a new commit.
    check["channels"]["test"]["commit"] = "ccc"
    assert notify.check_update(db) is False
    assert notify.check_update(db, force=True) is True and len(mails) == 2
