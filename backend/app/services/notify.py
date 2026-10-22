"""Mail notifications: import report, failed sync and available update.

Recipients and the events to mail are set under Administration > Notifications.
Every mail is in English followed by Dutch. A mail problem is logged and never
breaks the job that triggered it.
"""

import asyncio
import json
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Job
from ..settings_store import get_section
from .mailer import send_mail

log = logging.getLogger(__name__)

APP = "UniFi Fabric License Plate Importer"
SYNC_KINDS = {"assign", "remove", "scan"}
UPDATE_CHECK_EVERY = timedelta(hours=6)
MAX_LINES = 50

KIND_NL = {"assign": "registreren", "remove": "verwijderen", "scan": "inlezen", "import": "import"}


def _url(path: str) -> str:
    return get_settings().base_url.rstrip("/") + path


def recipients(cfg: dict[str, Any]) -> list[str]:
    return [r for r in re.split(r"[,;\s]+", cfg.get("recipients") or "") if r]


def send(db: Session, subject: str, body: str) -> bool:
    """Mail every recipient. Returns False when nothing was sent."""
    to = recipients(get_section(db, "notifications"))
    smtp = get_section(db, "smtp")
    if not to or not smtp.get("host"):
        return False
    try:
        asyncio.run(send_mail(smtp, ", ".join(to), f"{subject} - {APP}", body))
    except Exception:  # a mail problem must never break the job
        log.exception("could not send notification %r", subject)
        return False
    return True


def _failed_lines(job: Job) -> list[str]:
    lines = [f"- {e['message']}" for e in job.log or [] if not e.get("ok")]
    if len(lines) > MAX_LINES:
        lines = [*lines[:MAX_LINES], f"- ... (+{len(lines) - MAX_LINES})"]
    return lines


def _job_body(job: Job, title_en: str, title_nl: str) -> str:
    source = (job.params or {}).get("source", "")
    who = f"{job.actor} ({job.actor_type})"
    counts = f"{job.succeeded} / {job.processed}"
    failed = _failed_lines(job)
    result = (job.params or {}).get("result") or {}
    en = [
        f"{title_en} on {socket.gethostname()}.",
        "",
        f"Job:        #{job.id} ({job.kind}{', ' + source if source else ''})",
        f"Started by: {who}",
        f"Status:     {job.status}",
        f"Succeeded:  {counts}, failed: {job.failed}",
    ]
    nl = [
        f"{title_nl} op {socket.gethostname()}.",
        "",
        f"Taak:         #{job.id} ({KIND_NL.get(job.kind, job.kind)}{', ' + source if source else ''})",
        f"Gestart door: {who}",
        f"Status:       {job.status}",
        f"Gelukt:       {counts}, mislukt: {job.failed}",
    ]
    if "vehicles" in result:
        en.append(f"Vehicles:   {result['vehicles']} stored, {result.get('skipped', 0)} rows skipped")
        nl.append(f"Voertuigen:   {result['vehicles']} opgeslagen, {result.get('skipped', 0)} regels overgeslagen")
    if failed:
        en += ["", "Problems:", *failed]
        nl += ["", "Problemen: zie de lijst hierboven."]
    en += ["", f"Audit log: {_url('/admin/audit')}"]
    nl += ["", f"Auditlog: {_url('/admin/audit')}"]
    return "\n".join([*en, "", "----", "", *nl, ""])


def job_finished(db: Session, job: Job) -> None:
    """Called by the job runner after every job."""
    if job.kind != "import" and job.kind not in SYNC_KINDS:
        return
    cfg = get_section(db, "notifications")
    problem = job.status == "failed" or job.failed > 0
    if job.kind == "import":
        mode = cfg.get("import_report", "failure")
        if mode == "always" or (mode == "failure" and problem):
            state = "with problems" if problem else "completed"
            state_nl = "met problemen" if problem else "voltooid"
            send(db, f"Import {state}: {job.succeeded} of {job.processed} changes", _job_body(job, f"An import {state}", f"Een import is {state_nl}"))
            return
    if problem and cfg.get("sync_failure", True):
        send(db, f"Sync failed ({job.kind})", _job_body(job, f"Changes on the consoles failed ({job.kind})", "Wijzigingen op de consoles zijn mislukt"))


# ---------------------------------------------------------------- updates


def _state_path():
    path = get_settings().state_dir / "notify.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def check_update(db: Session, now: datetime | None = None, force: bool = False) -> bool:
    """Mail once per new commit on the installed channel. Returns True when mailed.

    Called by the scheduler; checks the update server at most every six hours."""
    from . import updater  # git is only needed here

    now = now or datetime.now(timezone.utc)
    cfg = get_section(db, "notifications")
    if not cfg.get("update_available", True) or not recipients(cfg):
        return False
    state = _load()
    last = state.get("update_checked_at")
    if not force and last and now - datetime.fromisoformat(last) < UPDATE_CHECK_EVERY:
        return False
    state["update_checked_at"] = now.isoformat()
    try:
        check = updater.check_for_updates()
    except updater.UpdateError as exc:
        log.info("update check for notification failed: %s", exc)
        _state_path().write_text(json.dumps(state))
        return False
    current = check["current"]
    channel = check["channels"].get(current.get("channel") or "", {})
    sent = False
    if channel.get("update_available") and state.get("update_notified") != channel["commit"]:
        name = updater.CHANNELS.get(current["channel"], current["channel"])
        body = (
            f"A new version is available on the {name} channel of {socket.gethostname()}.\n\n"
            f"Installed: {current['version']} ({current.get('commit')})\n"
            f"Available: {channel['version']} ({channel['commit']})\n\n"
            f"Install it under Administration > System & updates: {_url('/admin/system')}\n\n----\n\n"
            f"Er is een nieuwe versie beschikbaar op het {name}-kanaal van {socket.gethostname()}.\n\n"
            f"Geïnstalleerd: {current['version']} ({current.get('commit')})\n"
            f"Beschikbaar:   {channel['version']} ({channel['commit']})\n\n"
            f"Installeer hem via Beheer > Systeem & updates: {_url('/admin/system')}\n"
        )
        sent = send(db, f"Update available: {channel['version']}", body)
        if sent:
            state["update_notified"] = channel["commit"]
    _state_path().write_text(json.dumps(state))
    return sent
