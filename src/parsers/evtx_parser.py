"""
EVTX parser for LogNeedle.

Uses the ``python-evtx`` library (pure-Python, cross-platform) to parse
Windows Event Log (.evtx) files offline.  Maps each record to the
normalised event schema.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

try:
    import Evtx.Evtx as evtx
    import Evtx.Views as evtx_views
    HAS_EVTX = True
except ImportError:
    HAS_EVTX = False

# ── EVTX level mapping ────────────────────────────────────────────────

_LEVEL_MAP = {
    "1": "ERROR",    # Critical
    "2": "ERROR",    # Error
    "3": "WARN",     # Warning
    "4": "INFO",     # Information
    "5": "DEBUG",    # Verbose
    "0": "INFO",     # LogAlways
}

# Boot / shutdown heuristic event IDs  (provider → event_id → tag)
_KNOWN_EVENTS: dict[str, dict[int, str]] = {
    "Microsoft-Windows-Kernel-Power": {
        41: "shutdown,crash",
        107: "boot",
        109: "shutdown",
        507: "shutdown",
    },
    "Microsoft-Windows-Kernel-General": {
        12: "boot",
        13: "shutdown",
    },
    "EventLog": {
        6005: "boot",
        6006: "shutdown",
        6008: "shutdown,crash",
        6009: "boot",
    },
    "Microsoft-Windows-WER-SystemErrorReporting": {
        1001: "crash",
    },
    "Microsoft-Windows-Ntfs": {
        147: "ntfs",
        55: "ntfs",
        98: "ntfs",
    },
    "Ntfs": {
        147: "ntfs",
        55: "ntfs",
        98: "ntfs",
    },
    "disk": {
        7: "ntfs",
        11: "ntfs",
        15: "ntfs",
        51: "ntfs",
    },
}

NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


class EvtxParser:
    """Stream-parse an EVTX file into normalised event dicts."""

    def __init__(self, file_path: str | Path, source_file_label: str | None = None):
        if not HAS_EVTX:
            raise ImportError(
                "python-evtx is required for .evtx parsing.  "
                "Install with:  pip install python-evtx"
            )
        self.file_path = Path(file_path)
        self.label = source_file_label or str(self.file_path.name)
        self.warning_count = 0

    def parse(self) -> Generator[dict[str, Any], None, None]:
        try:
            with evtx.Evtx(str(self.file_path)) as log:
                for record in log.records():
                    try:
                        ev = self._parse_record(record)
                        if ev:
                            yield ev
                    except Exception:
                        self.warning_count += 1
        except Exception:
            self.warning_count += 1

    def _parse_record(self, record: Any) -> dict[str, Any] | None:
        xml_str = record.xml()
        root = ET.fromstring(xml_str)

        # System section
        sys_el = root.find(f"{NS}System")
        if sys_el is None:
            return None

        # Provider
        prov_el = sys_el.find(f"{NS}Provider")
        provider = prov_el.get("Name", "") if prov_el is not None else ""

        # EventID
        eid_el = sys_el.find(f"{NS}EventID")
        event_id = None
        if eid_el is not None:
            eid_text = eid_el.text
            if eid_text:
                try:
                    event_id = int(eid_text)
                except ValueError:
                    pass

        # Level
        lvl_el = sys_el.find(f"{NS}Level")
        level_raw: str = "4"
        if lvl_el is not None:
            lvl_text = lvl_el.text
            if lvl_text:
                level_raw = lvl_text
        level = _LEVEL_MAP.get(level_raw, "UNKNOWN")

        # TimeCreated
        tc_el = sys_el.find(f"{NS}TimeCreated")
        ts_str = tc_el.get("SystemTime", "") if tc_el is not None else ""
        dt_utc = None
        if ts_str:
            try:
                # remove trailing 'Z' and parse
                cleaned = ts_str.rstrip("Z").split(".")[0]
                dt_utc = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                try:
                    dt_utc = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

        # Computer
        comp_el = sys_el.find(f"{NS}Computer")
        computer = comp_el.text if comp_el is not None else ""

        # Channel (log name)
        chan_el = sys_el.find(f"{NS}Channel")
        channel = chan_el.text if chan_el is not None else ""

        # EventRecordID
        rid_el = sys_el.find(f"{NS}EventRecordID")
        record_id = None
        if rid_el is not None:
            rid_text = rid_el.text
            if rid_text:
                try:
                    record_id = int(rid_text)
                except ValueError:
                    pass

        # EventData / message
        msg = self._extract_message(root)

        # Tags from known event table
        tags = self._assign_tags(provider, event_id, msg)

        return {
            "event_time_utc": dt_utc,
            "event_time_str": ts_str,
            "source_type": "evtx",
            "source_file": self.label,
            "line_start": None,
            "line_end": None,
            "evtx_log_name": channel,
            "evtx_record_id": record_id,
            "provider": provider,
            "event_id": event_id,
            "level": level,
            "message": (msg or "")[:500],
            "message_raw": (msg or "")[:4000],
            "tags": tags,
        }

    @staticmethod
    def _extract_message(root: ET.Element) -> str:
        """Extract a human-readable message from EventData / UserData."""
        parts: list[str] = []
        for section_name in ("EventData", "UserData"):
            section = root.find(f"{NS}{section_name}")
            if section is None:
                # try without namespace
                section = root.find(section_name)
            if section is None:
                continue
            for child in section.iter():
                txt = child.text
                if txt and txt.strip():
                    name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    parts.append(f"{name}={txt.strip()}")
        return "; ".join(parts) if parts else ""

    @staticmethod
    def _assign_tags(provider: str, event_id: int | None, msg: str) -> str:
        tags: set[str] = set()
        if provider in _KNOWN_EVENTS and event_id is not None and event_id in _KNOWN_EVENTS[provider]:
            for t in _KNOWN_EVENTS[provider][event_id].split(","):
                tags.add(t.strip())
        # Heuristic text tags
        text = (msg or "").lower()
        if any(k in text for k in ("shutdown", "power off", "power down")):
            tags.add("shutdown")
        if any(k in text for k in ("boot", "startup", "reboot")):
            tags.add("boot")
        if any(k in text for k in ("ntfs", "disk", "volume", "storage")):
            tags.add("ntfs")
        if any(k in text for k in ("driver", "cannot communicate")):
            tags.add("driver")
        if any(k in text for k in ("crash", "bugcheck", "bsod", "bluescreen")):
            tags.add("crash")
        if any(k in text for k in ("timeout", "watchdog")):
            tags.add("timeout")
        return ",".join(sorted(tags)) if tags else ""
