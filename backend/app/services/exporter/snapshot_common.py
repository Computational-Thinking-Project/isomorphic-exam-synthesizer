"""Small helpers shared by the snapshot reader and builder (W4-MVP-07)."""

import re
from datetime import datetime
from typing import Any

LOCKED_STATUSES = ("approved", "exported")
# Same pattern as ``DisplayVersion.code`` in bundle_models.py.
VERSION_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


def valid_timestamp(value: Any) -> bool:
    """True for an ISO-8601 string that carries a UTC offset."""
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def code_order(code: str) -> tuple[int, int, str]:
    """Numeric codes first (ASCII digits only), then the rest alphabetically."""
    return (0, int(code), code) if code.isascii() and code.isdigit() else (1, 0, code)
