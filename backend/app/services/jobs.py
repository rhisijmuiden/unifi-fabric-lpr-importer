"""Background jobs: batches of console changes with progress and a report.

A job runs in a worker thread with its own database session, so a large
import does not block the request that started it.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .. import db as app_db
from ..config import get_settings
from ..models import Job
from . import notify

log = logging.getLogger(__name__)

MAX_LOG = 2000

# Jobs that change the consoles run one at a time, so two imports never create
# the same Access user or group twice. Later jobs wait in the "queued" state.
CONSOLE_KINDS = {"scan", "assign", "remove", "import"}
_console_lock = threading.Lock()


@dataclass
class Actor:
    """Who caused a change: a signed-in user, an API key or the system."""

    type: str
    name: str
    ip: str = ""

    def audit(self) -> dict[str, str]:
        return {"actor_type": self.type, "actor": self.name, "ip": self.ip}


class JobContext:
    def __init__(self, db: Session, job: Job, actor: Actor):
        self.db = db
        self.job = job
        self.actor = actor

    def add_total(self, count: int) -> None:
        self.job.total += count
        self.db.commit()

    def step(self, ok: bool, message: str, **details: Any) -> None:
        self.job.processed += 1
        if ok:
            self.job.succeeded += 1
        else:
            self.job.failed += 1
        self.note(message, ok, **details)

    def note(self, message: str, ok: bool = True, **details: Any) -> None:
        if len(self.job.log) < MAX_LOG:
            entry = {"at": datetime.now(timezone.utc).isoformat(), "ok": ok, "message": message, **details}
            self.job.log = [*self.job.log, entry]
        self.db.commit()


JobFn = Callable[[JobContext], dict[str, Any] | None]


def start(db: Session, kind: str, actor: Actor, params: dict[str, Any], fn: JobFn, inline: bool = False, idempotency_key: str | None = None) -> Job:
    """Run fn as a job in a worker thread, or right away when `inline` (command line)."""
    job = Job(kind=kind, actor_type=actor.type, actor=actor.name, params=params, idempotency_key=idempotency_key)
    db.add(job)
    db.commit()
    if inline or get_settings().jobs_inline:
        _run(job.id, actor, fn)
        db.refresh(job)
    else:
        threading.Thread(target=_run, args=(job.id, actor, fn), daemon=True, name=f"job-{job.id}").start()
    return job


def _run(job_id: int, actor: Actor, fn: JobFn) -> None:
    db = next(app_db.get_db())
    lock = None
    try:
        job = db.get(Job, job_id)
        assert job is not None
        if job.kind in CONSOLE_KINDS:
            lock = _console_lock
            lock.acquire()
        job.status = "running"
        db.commit()
        ctx = JobContext(db, job, actor)
        try:
            result = fn(ctx) or {}
            job.params = {**job.params, "result": result}
            job.status = "done"
        except Exception as exc:  # report every failure in the job instead of losing it
            log.exception("job %s failed", job_id)
            db.rollback()
            job = db.get(Job, job_id)
            job.status = "failed"
            job.log = [*job.log, {"at": datetime.now(timezone.utc).isoformat(), "ok": False, "message": str(exc)}]
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        if lock is not None:
            lock.release()
            lock = None
        notify.job_finished(db, job)
    finally:
        if lock is not None:
            lock.release()
        db.close()


def to_dict(job: Job, with_log: bool = True) -> dict[str, Any]:
    data = {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "actor_type": job.actor_type,
        "actor": job.actor,
        "total": job.total,
        "processed": job.processed,
        "succeeded": job.succeeded,
        "failed": job.failed,
        "result": (job.params or {}).get("result"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if with_log:
        data["log"] = job.log
    return data
