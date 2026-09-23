"""
Streaming text-log parser for LogNeedle.

Handles *.log, *.txt, *.csv, *.jsonl, *.out files.
- Detects encoding via chardet
- Extracts timestamps with the timestamp battery
- Merges multi-line stack traces into the previous event
- Heuristically assigns level (ERROR / WARN / INFO / UNKNOWN)
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator, Optional

import chardet

from .timestamp import parse_timestamp

# ── level heuristics ───────────────────────────────────────────────────

_LEVEL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(ERROR|FATAL|CRITICAL|SEVERE)\b", re.I), "ERROR"),
    (re.compile(r"\b(WARN(?:ING)?)\b", re.I), "WARN"),
    (re.compile(r"\b(INFO(?:RMATION)?)\b", re.I), "INFO"),
    (re.compile(r"\b(DEBUG|TRACE|VERBOSE)\b", re.I), "DEBUG"),
    # Exception keywords → error
    (re.compile(r"\b(exception|traceback|stack\s*trace|fault|bugcheck)\b", re.I), "ERROR"),
    (re.compile(r"\bfailed\b", re.I), "ERROR"),
]

# Tags
_TAG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(shutdown|power\s*off|power\s*down)\b", re.I), "shutdown"),
    (re.compile(r"\b(boot|startup|reboot)\b", re.I), "boot"),
    (re.compile(r"\b(ntfs|disk|storage|volume)\b", re.I), "ntfs"),
    (re.compile(r"\b(driver|cannot\s+communicate)\b", re.I), "driver"),
    (re.compile(r"\b(timeout|watchdog)\b", re.I), "timeout"),
    (re.compile(r"\b(crash|bugcheck|bsod|bluescreen)\b", re.I), "crash"),
    (re.compile(r"\b(service)\b", re.I), "service"),
]


def _detect_level(line: str) -> str:
    for pat, lvl in _LEVEL_PATTERNS:
        if pat.search(line):
            return lvl
    return "UNKNOWN"


def _detect_tags(text: str) -> str:
    tags = []
    for pat, tag in _TAG_PATTERNS:
        if pat.search(text):
            tags.append(tag)
    return ",".join(sorted(set(tags))) if tags else ""


def _detect_encoding(path: str | Path, sample_bytes: int = 65536) -> str:
    with open(path, "rb") as f:
        raw = f.read(sample_bytes)
    # Check for BOM
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    result = chardet.detect(raw)
    enc = result.get("encoding") or "utf-8"
    # normalise
    enc = enc.lower().replace("-", "_")
    if "ascii" in enc:
        enc = "utf-8"
    return enc


class TextLogParser:
    """Stream-parse a text log file into normalised event dicts."""

    def __init__(
        self,
        file_path: str | Path,
        source_file_label: str | None = None,
        reference_year: int | None = None,
        line_cb: Callable[[int, int], None] | None = None,
    ):
        self.file_path = Path(file_path)
        self.label = source_file_label or str(self.file_path.name)
        self.ref_year = reference_year
        self.warning_count = 0   # encoding / parse warnings
        self._line_cb = line_cb  # (lines_read, events_found)

    def parse(self) -> Generator[dict[str, Any], None, None]:
        """Yield normalised event dicts, one per timestamped entry."""
        enc = _detect_encoding(self.file_path)

        # Check if this is a jsonl/csv file and handle specially
        suffix = self.file_path.suffix.lower()
        if suffix == ".jsonl":
            yield from self._parse_jsonl(enc)
            return
        if suffix == ".csv":
            yield from self._parse_csv(enc)
            return

        # ── generic text log ────────────────────────────────────────
        current_event: dict[str, Any] | None = None
        current_lines: list[str] = []
        line_start = 0
        event_count = 0
        line_no = 0

        try:
            with open(self.file_path, "r", encoding=enc, errors="replace") as fh:
                for line_no, line in enumerate(fh, start=1):
                    if self._line_cb is not None and line_no % 25_000 == 0:
                        self._line_cb(line_no, event_count)
                    dt, raw_ts, assumed = parse_timestamp(line, self.ref_year)
                    if dt is not None:
                        # flush previous
                        if current_event is not None:
                            ev = current_event
                            ev["line_end"] = line_no - 1
                            msg = "\n".join(current_lines)
                            ev["level"] = _detect_level(msg)
                            ev["tags"] = _detect_tags(msg)
                            ev["message"] = msg[:500]
                            ev["message_raw"] = msg[:4000]
                            yield ev
                        current_event = {
                            "event_time_utc": dt,
                            "event_time_str": raw_ts,
                            "source_type": "text",
                            "source_file": self.label,
                            "line_start": line_no,
                            "line_end": line_no,
                            "evtx_log_name": None,
                            "evtx_record_id": None,
                            "provider": None,
                            "event_id": None,
                        }
                        current_lines = [line.rstrip()]
                    elif current_event is not None:
                        # continuation / multi-line
                        current_lines.append(line.rstrip())
                    # else: line before any timestamp → skip

                # flush last
                if current_event is not None:
                    ev = current_event
                    ev["line_end"] = line_no
                    msg = "\n".join(current_lines)
                    ev["level"] = _detect_level(msg)
                    ev["tags"] = _detect_tags(msg)
                    ev["message"] = msg[:500]
                    ev["message_raw"] = msg[:4000]
                    yield ev
        except Exception:
            self.warning_count += 1

    # ── specialised formats ─────────────────────────────────────────

    def _parse_jsonl(self, enc: str) -> Generator[dict[str, Any], None, None]:
        try:
            with open(self.file_path, "r", encoding=enc, errors="replace") as fh:
                for line_no, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        self.warning_count += 1
                        continue
                    # Try common JSON log keys
                    ts_str = ""
                    dt = None
                    for key in ("timestamp", "time", "@timestamp", "ts", "date", "datetime"):
                        if key in obj:
                            ts_str = str(obj[key])
                            dt, raw_ts, assumed = parse_timestamp(ts_str, self.ref_year)
                            if dt:
                                ts_str = raw_ts
                                break
                    msg = obj.get("message") or obj.get("msg") or json.dumps(obj)[:500]
                    lvl_str = str(obj.get("level") or obj.get("severity") or "").upper()
                    level = "UNKNOWN"
                    if "ERR" in lvl_str or "FATAL" in lvl_str or "CRIT" in lvl_str:
                        level = "ERROR"
                    elif "WARN" in lvl_str:
                        level = "WARN"
                    elif "INFO" in lvl_str:
                        level = "INFO"
                    yield {
                        "event_time_utc": dt,
                        "event_time_str": ts_str,
                        "source_type": "text",
                        "source_file": self.label,
                        "line_start": line_no,
                        "line_end": line_no,
                        "evtx_log_name": None,
                        "evtx_record_id": None,
                        "provider": None,
                        "event_id": None,
                        "level": level,
                        "message": str(msg)[:500],
                        "message_raw": str(msg)[:4000],
                        "tags": _detect_tags(str(msg)),
                    }
        except Exception:
            self.warning_count += 1

    def _parse_csv(self, enc: str) -> Generator[dict[str, Any], None, None]:
        """Parse CSV line-by-line (avoids loading into memory)."""
        import csv

        try:
            with open(self.file_path, "r", encoding=enc, errors="replace", newline="") as fh:
                reader = csv.reader(fh)
                header = None
                for line_no, row in enumerate(reader, start=1):
                    if header is None:
                        header = row
                        continue
                    # try to find a timestamp in any column
                    dt = None
                    ts_str = ""
                    full_text = " | ".join(row)
                    for cell in row:
                        dt, raw_ts, assumed = parse_timestamp(cell.strip(), self.ref_year)
                        if dt:
                            ts_str = raw_ts
                            break
                    yield {
                        "event_time_utc": dt,
                        "event_time_str": ts_str,
                        "source_type": "text",
                        "source_file": self.label,
                        "line_start": line_no,
                        "line_end": line_no,
                        "evtx_log_name": None,
                        "evtx_record_id": None,
                        "provider": None,
                        "event_id": None,
                        "level": _detect_level(full_text),
                        "message": full_text[:500],
                        "message_raw": full_text[:4000],
                        "tags": _detect_tags(full_text),
                    }
        except Exception:
            self.warning_count += 1
