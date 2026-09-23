"""
Timestamp parsing utilities for LogNeedle.

Tries a battery of common log-timestamp formats and returns a
timezone-aware UTC datetime (or None).  When the raw string lacks
timezone info we tag the result as "assumed local" so callers can
label it in the UI.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

# ── regex patterns (order = most-specific first) ───────────────────────

# Each entry: (compiled regex, strptime-compatible format, has_tz flag)
# The regex must match *at the start* of the candidate string.

_MONTH_NAMES = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)

TIMESTAMP_PATTERNS: list[Tuple[re.Pattern, str | None, bool]] = [
    # ISO-8601 with 'T' separator and optional tz  (2025-11-17T06:22:13.123Z)
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
        ),
        None,  # we parse manually for flexibility
        True,
    ),
    # YYYY-MM-DD HH:MM:SS.mmm  (space separator)
    (
        re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)"),
        None,
        False,
    ),
    # YYYY/MM/DD HH:MM:SS
    (
        re.compile(r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)"),
        None,
        False,
    ),
    # MM/DD/YYYY HH:MM:SS  (US style CSV)
    (
        re.compile(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}(?:\s*[APap][Mm])?)"),
        None,
        False,
    ),
    # Syslog style: "Nov 17 06:22:13"
    (
        re.compile(
            rf"((?:{_MONTH_NAMES})\s+\d{{1,2}}\s+\d{{2}}:\d{{2}}:\d{{2}})"
        ),
        None,
        False,
    ),
    # Windows EVTX text rendering: "11/17/2025 06:22:13 AM"
    (
        re.compile(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[APap][Mm])"),
        None,
        False,
    ),
]


def parse_timestamp(
    text: str, reference_year: int | None = None
) -> Tuple[Optional[datetime], str, bool]:
    """Try to extract a timestamp from the beginning of *text*.

    Returns
    -------
    (dt_utc, original_str, assumed_local)
        - *dt_utc*: datetime in UTC (or None if no match)
        - *original_str*: the raw substring that was parsed
        - *assumed_local*: True when we had to guess the timezone
    """
    text_stripped = text.strip()
    # Fast path: if the first 80 chars contain no digit, skip regex battery
    head = text_stripped[:80]
    if not any(c.isdigit() for c in head):
        return (None, "", False)
    for pat, _fmt, _has_tz in TIMESTAMP_PATTERNS:
        m = pat.search(head)
        if not m:
            continue
        raw = m.group(1).strip()
        dt = _try_parse(raw, reference_year)
        if dt is None:
            continue
        if dt.tzinfo is not None:
            return (dt.astimezone(timezone.utc), raw, False)
        else:
            # assume local time
            return (dt.replace(tzinfo=timezone.utc), raw, True)
    return (None, "", False)


def _try_parse(raw: str, ref_year: int | None) -> Optional[datetime]:
    """Best-effort datetime parsing of a raw timestamp string."""
    # ISO with T
    if "T" in raw:
        return _parse_iso(raw)
    # Syslog month-name
    for mname in ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"):
        if raw.startswith(mname):
            return _parse_syslog(raw, ref_year)
    # slash or dash separated
    return _parse_numeric(raw)


def _parse_iso(raw: str) -> Optional[datetime]:
    cleaned = raw.replace("Z", "+00:00")
    # handle missing colon in tz offset  (+0500 -> +05:00)
    cleaned = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', cleaned)
    try:
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_syslog(raw: str, ref_year: int | None) -> Optional[datetime]:
    try:
        dt = datetime.strptime(raw, "%b %d %H:%M:%S")
        yr = ref_year or datetime.now().year
        return dt.replace(year=yr)
    except ValueError:
        return None


def _parse_numeric(raw: str) -> Optional[datetime]:
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None
