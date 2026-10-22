"""License plate normalisation and the vehicle naming convention.

Dutch plates are written in their official notation (sidecodes 1-14, e.g.
`12-ABC-3`). Plates that match no Dutch sidecode, such as foreign trucks, are
kept as entered, in capitals. Matching always uses the key: letters and digits only.
"""

import re

# Sidecode patterns: L = letter, D = digit, '-' = separator.
_SIDECODES = [
    "LL-DD-DD", "DD-DD-LL", "DD-LL-DD", "LL-DD-LL", "LL-LL-DD", "DD-LL-LL",
    "DD-LLL-D", "D-LLL-DD", "LL-DDD-L", "L-DDD-LL", "LLL-DD-L", "L-DD-LLL",
    "D-LL-DDD", "DDD-LL-D",
]


def _regex(code: str) -> re.Pattern[str]:
    parts = code.split("-")
    body = "".join(f"([A-Z]{{{len(p)}}})" if p[0] == "L" else f"([0-9]{{{len(p)}}})" for p in parts)
    return re.compile(f"^{body}$")


_PATTERNS = [_regex(c) for c in _SIDECODES]


def plate_key(value: str) -> str:
    """Letters and digits only, in capitals. Used to match plates across sources."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def format_plate(value: str) -> str:
    """Official notation for a Dutch plate; other plates in capitals as entered."""
    key = plate_key(value)
    for pattern in _PATTERNS:
        m = pattern.match(key)
        if m:
            return "-".join(m.groups())
    cleaned = re.sub(r"[^A-Z0-9-]", "", re.sub(r"\s+", "-", (value or "").strip().upper()))
    return re.sub(r"-{2,}", "-", cleaned).strip("-") or key


def is_valid_plate(value: str) -> bool:
    return 2 <= len(plate_key(value)) <= 12


def group_name(department: str, location: str) -> str:
    """Convention: group = department + location, e.g. `Netwerktransport Wognum`."""
    return " ".join(p for p in (department.strip(), location.strip()) if p)


def credential_value(plate: str, notation: str) -> str:
    """The value sent to UniFi Access as the license plate credential."""
    return plate_key(plate) if notation == "compact" else format_plate(plate)
