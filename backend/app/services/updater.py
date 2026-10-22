"""Version information, update checks and update requests.

The app itself never runs privileged commands. An update is requested by writing
update-request.json to the state directory and starting the
lpr-importer-update.service unit, which runs scripts/update.sh as root.
"""

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings

CHANNELS = {"main": "production", "test": "test"}


class UpdateError(Exception):
    pass


def _git(*args: str, timeout: int = 30) -> str:
    repo = get_settings().repo_dir
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise UpdateError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _read_version(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return "0.0.0"


def local_info() -> dict[str, Any]:
    settings = get_settings()
    info: dict[str, Any] = {
        "version": _read_version(settings.repo_dir / "VERSION"),
        "channel": None,
        "commit": None,
        "commit_date": None,
    }
    try:
        info["channel"] = _git("rev-parse", "--abbrev-ref", "HEAD")
        info["commit"] = _git("rev-parse", "--short=10", "HEAD")
        info["commit_date"] = _git("log", "-1", "--format=%cI")
    except (UpdateError, OSError, subprocess.TimeoutExpired):
        pass
    return info


def check_for_updates() -> dict[str, Any]:
    info = local_info()
    try:
        # Explicit refspecs so this also works in single-branch or shallow clones.
        refspecs = [f"+refs/heads/{b}:refs/remotes/origin/{b}" for b in CHANNELS]
        _git("fetch", "--quiet", "origin", *refspecs, timeout=60)
    except (UpdateError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"Could not reach the update server: {exc}") from exc

    local_full = _git("rev-parse", "HEAD")
    channels = {}
    for branch in CHANNELS:
        try:
            remote_commit = _git("rev-parse", f"origin/{branch}")
            remote_version = _git("show", f"origin/{branch}:VERSION")
            remote_date = _git("log", "-1", "--format=%cI", f"origin/{branch}")
        except UpdateError:
            continue
        channels[branch] = {
            "version": remote_version,
            "commit": remote_commit[:10],
            "commit_date": remote_date,
            "is_current": branch == info["channel"],
            "update_available": branch == info["channel"] and remote_commit != local_full,
        }
    return {
        "current": info,
        "channels": channels,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def request_update(channel: str, requested_by: str) -> None:
    if channel not in CHANNELS:
        raise UpdateError("Unknown channel")
    settings = get_settings()
    state = settings.state_dir
    status = read_status()
    if status.get("state") == "running":
        raise UpdateError("An update is already running")
    state.mkdir(parents=True, exist_ok=True)
    (state / "update-request.json").write_text(
        json.dumps(
            {
                "channel": channel,
                "requested_by": requested_by,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    result = subprocess.run(shlex.split(settings.update_command), capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise UpdateError(result.stderr.strip() or "Could not start the update service")


def read_status() -> dict[str, Any]:
    state = get_settings().state_dir
    try:
        status = json.loads((state / "update-status.json").read_text())
    except (OSError, ValueError):
        status = {"state": "idle"}
    try:
        lines = (state / "update.log").read_text(errors="replace").splitlines()
        status["log"] = lines[-200:]
    except OSError:
        status["log"] = []
    return status
