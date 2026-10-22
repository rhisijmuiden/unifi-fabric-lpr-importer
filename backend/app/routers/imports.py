import csv
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_operator, user_actor
from ..models import User
from ..schemas import ImportIn, ImportMappingIn
from ..services import jobs
from ..services.vehicles import plan_import, run_import
from ..settings_store import get_section, update_section

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20000

# Header names (lower case, letters only) recognised per field, Dutch and English.
HINTS = {
    "plate": ["kenteken", "kentekens", "plate", "licenseplate", "licenceplate", "registration", "nummerplaat", "regnr"],
    "department": ["afdeling", "department", "divisie", "bedrijfsonderdeel", "businessunit", "dept"],
    "location": ["standplaats", "vestiging", "locatie", "location", "depot", "site", "plaats"],
    "group_name": ["groep", "group", "usergroup", "toegangsgroep"],
    "description": ["omschrijving", "description", "merk", "type", "model", "opmerking", "naam", "voertuig"],
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z]", "", header.lower())


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field, names in HINTS.items():
        for header in headers:
            if header not in mapping.values() and _norm(header) in names:
                mapping[field] = header
                break
    return mapping


def read_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")  # Excel on Windows
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    lines = [r for r in reader if any(c.strip() for c in r)]
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty_file")
    headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(lines[0])]
    if len(lines) - 1 > MAX_ROWS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "too_many_rows")
    rows = [{h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(headers)} for r in lines[1:]]
    return headers, rows


@router.post("/parse")
async def parse(file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_operator)) -> dict:
    """Read a CSV file and suggest which column holds what. Nothing is stored yet."""
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file_too_large")
    headers, rows = read_csv(content)
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
