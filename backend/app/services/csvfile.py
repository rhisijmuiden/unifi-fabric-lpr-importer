"""Reading vehicle CSV files: delimiter and encoding detection, column mapping.

Used by the CSV wizard (the browser maps the columns) and by scheduled imports
(the mapping saved with the schedule is applied here).
"""

import csv
import io
import re
from typing import Any

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20000
FIELDS = ("plate", "department", "location", "group_name", "description")

# Header names (lower case, letters only) recognised per field, Dutch and English.
HINTS = {
    "plate": ["kenteken", "kentekens", "plate", "licenseplate", "licenceplate", "registration", "nummerplaat", "regnr"],
    "department": ["afdeling", "department", "divisie", "bedrijfsonderdeel", "businessunit", "dept"],
    "location": ["standplaats", "vestiging", "locatie", "location", "depot", "site", "plaats"],
    "group_name": ["groep", "group", "usergroup", "toegangsgroep"],
    "description": ["omschrijving", "description", "merk", "type", "model", "opmerking", "naam", "voertuig"],
}


class CsvError(Exception):
    """The file cannot be used. `code` is translated in the UI."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
    if len(content) > MAX_BYTES:
        raise CsvError("file_too_large")
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
        raise CsvError("empty_file")
    headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(lines[0])]
    if len(lines) - 1 > MAX_ROWS:
        raise CsvError("too_many_rows")
    rows = [{h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(headers)} for r in lines[1:]]
    return headers, rows


def _fold(value: str) -> str:
    return " ".join(value.split()).casefold()


def convert(
    rows: list[dict[str, str]],
    mapping: dict[str, str],
    defaults: dict[str, str],
    locations: list[str] | None = None,
    departments: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Apply a column mapping like the wizard does: the mapped column, else the default.
    Optionally keep only rows of the given locations and departments (case-insensitive)."""
    keep_locations = {_fold(x) for x in locations or [] if x.strip()}
    keep_departments = {_fold(x) for x in departments or [] if x.strip()}
    out = []
    for raw in rows:
        row = {f: ((raw.get(mapping[f], "") if mapping.get(f) else "") or defaults.get(f, "") or "").strip() for f in FIELDS}
        if keep_locations and _fold(row["location"]) not in keep_locations:
            continue
        if keep_departments and _fold(row["department"]) not in keep_departments:
            continue
        out.append(row)
    return out
