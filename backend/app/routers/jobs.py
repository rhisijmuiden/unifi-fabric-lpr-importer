from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Job, User
from ..services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(db: Session = Depends(get_db), _: User = Depends(current_user), limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    return [jobs.to_dict(j, with_log=False) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(limit))]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return jobs.to_dict(job)
