from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_operator, user_actor
from ..models import User
from ..schemas import ImportIn, ImportMappingIn
from ..services import jobs
from ..services.csvfile import MAX_BYTES, CsvError, read_csv, suggest_mapping
from ..services.vehicles import plan_import, run_import
from ..settings_store import get_section, update_section

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/parse")
async def parse(file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_operator)) -> dict:
    """Read a CSV file and suggest which column holds what. Nothing is stored yet."""
    content = await file.read(MAX_BYTES + 1)
    try:
        headers, rows = read_csv(content)
    except CsvError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.code) from exc
    saved = get_section(db, "import")
    mapping = suggest_mapping(headers)
    # The last used mapping wins when its columns exist in this file.
    mapping.update({f: h for f, h in (saved.get("mapping") or {}).items() if h in headers})
    return {"filename": file.filename, "headers": headers, "rows": rows, "mapping": mapping, "defaults": saved.get("defaults") or {}}


@router.put("/mapping")
def save_mapping(body: ImportMappingIn, db: Session = Depends(get_db), _: User = Depends(require_operator)) -> dict:
    update_section(db, "import", body.model_dump())
    return get_section(db, "import")


@router.post("/preview")
def preview(body: ImportIn, db: Session = Depends(get_db), _: User = Depends(require_operator)) -> dict:
    """Dry run: per row new / changed / unchanged / invalid, and per console what would be added."""
    return plan_import(db, [r.model_dump() for r in body.rows], body.console_ids, body.mode)


@router.post("/run", status_code=202)
def run(body: ImportIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> dict:
    rows = [r.model_dump() for r in body.rows]
    actor = user_actor(user, request)
    params = {"rows": len(rows), "console_ids": body.console_ids, "mode": body.mode, "source": "csv"}
    audit.record(db, "import.started", user=user, details=params, request=request)
    job = jobs.start(db, "import", actor, params, lambda ctx: run_import(ctx, rows, "csv", body.console_ids, body.mode))
    return jobs.to_dict(job, with_log=False)
