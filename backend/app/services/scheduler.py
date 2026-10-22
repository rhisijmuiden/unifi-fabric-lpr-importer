"""Runs scheduled full and incremental backups.

A schedule has a frequency (hourly, daily, weekly, monthly) and a time in the
server's local time zone. A run is due when the most recent scheduled moment has
passed and no run has been started since. Missed moments older than the catch-up
window (server switched off) are skipped. When both are due, the full backup runs.
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from .. import db as app_db
from ..config import get_settings
from ..settings_store import get_section
from . import backup, jobs

log = logging.getLogger(__name__)

TICK_SECONDS = 30
CATCH_UP = timedelta(hours=6)
FREQUENCIES = ("hourly", "daily", "weekly", "monthly")

_stop = threading.Event()
_thread: threading.Thread | None = None


def _clock(value: str) -> tuple[int, int]:
    try:
        hour, minute = (int(x) for x in (value or "02:00").split(":")[:2])
        return min(max(hour, 0), 23), min(max(minute, 0), 59)
    except ValueError:
        return 2, 0


def last_slot(schedule: dict[str, Any], now: datetime) -> datetime:
    """The most recent scheduled moment at or before `now` (naive local time)."""
    hour, minute = _clock(schedule.get("time", "02:00"))
    frequency = schedule.get("frequency", "daily")
    if frequency == "hourly":
        slot = now.replace(minute=minute, second=0, microsecond=0)
        return slot if slot <= now else slot - timedelta(hours=1)
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if frequency == "weekly":
        slot -= timedelta(days=(now.weekday() - int(schedule.get("weekday", 6))) % 7)
        return slot if slot <= now else slot - timedelta(days=7)
    if frequency == "monthly":
        day = min(max(int(schedule.get("monthday", 1)), 1), 28)
        slot = slot.replace(day=day)
        if slot > now:
            previous = (slot.replace(day=1) - timedelta(days=1)).replace(day=day)
            slot = previous
        return slot
    return slot if slot <= now else slot - timedelta(days=1)


def next_slot(schedule: dict[str, Any], now: datetime) -> datetime:
    """The first scheduled moment after `now`."""
    step = {"hourly": timedelta(minutes=61), "daily": timedelta(hours=25), "weekly": timedelta(days=8), "monthly": timedelta(days=32)}
    probe = now + step.get(schedule.get("frequency", "daily"), timedelta(hours=25))
    slot = last_slot(schedule, probe)
    while True:
        earlier = last_slot(schedule, slot - timedelta(seconds=1))
        if earlier <= now:
            return slot
        slot = earlier


def _state_path():
    path = get_settings().state_dir / "backup"
    path.mkdir(parents=True, exist_ok=True)
    return path / "schedule.json"


def _load() -> dict[str, str]:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save(state: dict[str, str]) -> None:
    _state_path().write_text(json.dumps(state))


def due_kinds(cfg: dict[str, Any], state: dict[str, str], now: datetime) -> list[str]:
    """Which backup kinds are due. Updates `state` (last start per kind)."""
    due = []
    for kind in backup.KINDS:
        schedule = cfg.get(f"schedule_{kind}") or {}
        if not schedule.get("enabled"):
            continue
        slot = last_slot(schedule, now)
        last = state.get(kind)
        if last is None:
            state[kind] = now.isoformat()  # armed: first run at the next scheduled moment
            continue
        if datetime.fromisoformat(last) < slot and now - slot <= CATCH_UP:
            due.append(kind)
    if due:
        for kind in due:
            state[kind] = now.isoformat()
        if "full" in due:
            return ["full"]
    return due


def tick(now: datetime | None = None) -> str | None:
    """Start a due backup, if any. Returns the kind started."""
    now = now or datetime.now()
    db = next(app_db.get_db())
    try:
        cfg = get_section(db, "backup")
        state = _load()
        due = due_kinds(cfg, state, now)
        _save(state)
        if not due:
            return None
        kind = due[0]
        jobs.start(
            db,
            "backup",
            jobs.Actor("system", "scheduler"),
            {"kind": kind, "scheduled": True},
            lambda ctx: backup.run_backup(ctx, kind),
        )
        return kind
    finally:
        db.close()


def _loop() -> None:
    while not _stop.wait(TICK_SECONDS):
        try:
            tick()
        except Exception:  # keep the scheduler alive whatever happens
            log.exception("backup scheduler tick failed")


def start() -> None:
    global _thread
    if not get_settings().scheduler or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="backup-scheduler")
    _thread.start()


def stop() -> None:
    _stop.set()
