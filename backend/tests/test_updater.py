import json
import subprocess

import pytest

from app.config import get_settings
from app.services import updater


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path, monkeypatch, app_env):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    (work / "VERSION").write_text("0.1.0\n")
    git(work, "add", "VERSION")
    git(work, "commit", "-qm", "v1")
    git(work, "push", "-q", "origin", "main")
    git(work, "push", "-q", "origin", "main:test")
    install = tmp_path / "install"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(origin), str(install)], check=True, capture_output=True)
    monkeypatch.setenv("LPR_REPO_DIR", str(install))
    monkeypatch.setenv("LPR_UPDATE_COMMAND", "true")
    get_settings.cache_clear()
    return work, install


def test_info_and_update_check(repos):
    work, _ = repos
    info = updater.local_info()
    assert info["version"] == "0.1.0" and info["channel"] == "main"
    assert updater.check_for_updates()["channels"]["main"]["update_available"] is False

    (work / "VERSION").write_text("0.2.0\n")
    git(work, "commit", "-qam", "v2")
    git(work, "push", "-q", "origin", "main:test")
    result = updater.check_for_updates()
    assert result["channels"]["test"]["version"] == "0.2.0"
    assert result["channels"]["main"]["update_available"] is False

    git(work, "push", "-q", "origin", "main")
    assert updater.check_for_updates()["channels"]["main"]["update_available"] is True


def test_request_update_writes_request(repos):
    updater.request_update("test", "admin")
    req = json.loads((get_settings().state_dir / "update-request.json").read_text())
    assert req["channel"] == "test"
    with pytest.raises(updater.UpdateError):
        updater.request_update("evil; rm -rf /", "admin")


def test_running_update_blocks_new_request(repos):
    state = get_settings().state_dir
    state.mkdir(parents=True, exist_ok=True)
    (state / "update-status.json").write_text(json.dumps({"state": "running"}))
    with pytest.raises(updater.UpdateError):
        updater.request_update("main", "admin")


def test_update_endpoint_audited(repos, admin_client):
    assert admin_client.post("/api/system/update", json={"channel": "test"}).status_code == 202
    actions = [i["action"] for i in admin_client.get("/api/audit").json()["items"]]
    assert "system.switch_channel" in actions
