"""Collision-resistant run identity."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

_RUN_ID_RE = re.compile(r"^FN-(?P<stamp>\d{8}T\d{6}Z)-[0-9a-f]{8}$")


def generate_run_id(now: datetime | None = None) -> str:
    """Return a unique run identifier of the form ``FN-YYYYMMDDTHHMMSSZ-<hex8>``.

    The timestamp anchors the identifier in UTC; the 32-bit random suffix
    (from ``secrets.token_hex``) makes collisions vanishingly unlikely even
    if two runs start in the same second on the same host.

    Passing a naive ``datetime`` is rejected — we refuse to guess whether a
    caller means UTC or local time.
    """
    if now is not None:
        if not isinstance(now, datetime):
            raise TypeError(
                f"generate_run_id: `now` must be a datetime (got {type(now).__name__})"
            )
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(
                "generate_run_id: `now` must be timezone-aware; refusing to "
                "apply local-time behavior to a naive datetime."
            )
    ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(4)
    return f"FN-{stamp}-{suffix}"


def is_valid_run_id(candidate: str) -> bool:
    """Return True iff ``candidate`` matches the run_id contract exactly.

    Validation covers shape AND semantic parsability of the timestamp — a
    shape-only match like ``FN-20260232T140102Z-abcdef01`` is rejected
    because 2026-02-32 is not a real date.
    """
    if not isinstance(candidate, str):
        return False
    match = _RUN_ID_RE.match(candidate)
    if not match:
        return False
    try:
        datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return False
    return True
