"""
Analysis / "Needle" engine for LogNeedle.

Queries the EventStore and produces structured report sections:
  - Timeline bullets per window
  - Last-error causal analysis
  - Storm detection summaries
  - Boot / shutdown lifecycle markers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..store.db import EventStore


# ── data classes for report output ──────────────────────────────────

@dataclass
class Citation:
    """Evidence citation for a report bullet."""
    source_type: str          # 'evtx' | 'text'
    source_file: str
    line_start: int | None = None
    line_end: int | None = None
    evtx_log_name: str | None = None
    evtx_record_id: int | None = None
    provider: str | None = None
    event_id: int | None = None
    timestamp: str = ""

    def format_text(self) -> str:
        if self.source_type == "evtx":
            parts: list[str] = []
            if self.evtx_log_name:
                parts.append(str(self.evtx_log_name))
            if self.evtx_record_id is not None:
                parts.append(f"Record#{self.evtx_record_id}")
            if self.timestamp:
                parts.append(self.timestamp)
            if self.provider:
                parts.append(str(self.provider))
            if self.event_id is not None:
                parts.append(f"EventID={self.event_id}")
            return "Source: " + " / ".join(parts)
        else:
            loc = f"L{self.line_start}"
            if self.line_end and self.line_end != self.line_start:
                loc = f"L{self.line_start}–L{self.line_end}"
            return f"Source: {self.source_file} {loc}"


@dataclass
class ReportBullet:
    """Single bullet in a report section."""
    timestamp_range: str
    summary: str
    badges: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    level: str = "INFO"
    repeat_count: int | None = None


@dataclass
class ReportSection:
    """A section in the report (e.g., 'High confidence findings')."""
    heading: str
    bullets: list[ReportBullet] = field(default_factory=list)


@dataclass
class Report:
    """Full report for a time window."""
    window_label: str
    end_time: datetime
    start_time: datetime
    sections: list[ReportSection] = field(default_factory=list)
    total_events: int = 0


# ── main analyzer ───────────────────────────────────────────────────

WINDOWS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "10m": timedelta(minutes=10),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

WINDOW_LABELS = {
    "1m": "LAST MINUTE",
    "5m": "LAST 5 MINUTES",
    "10m": "LAST 10 MINUTES",
    "15m": "LAST 15 MINUTES",
    "1h": "LAST HOUR",
    "1d": "LAST DAY",
    "1w": "LAST WEEK",
}


def _citation_from_event(ev: dict) -> Citation:
    return Citation(
        source_type=ev.get("source_type", "text"),
        source_file=ev.get("source_file", ""),
        line_start=ev.get("line_start"),
        line_end=ev.get("line_end"),
        evtx_log_name=ev.get("evtx_log_name"),
        evtx_record_id=ev.get("evtx_record_id"),
        provider=ev.get("provider"),
        event_id=ev.get("event_id"),
        timestamp=str(ev.get("event_time_str", "")),
    )


def _badges_from_event(ev: dict) -> list[str]:
    """Extract badge-worthy keywords from an event."""
    badges: list[str] = []
    tags = ev.get("tags", "") or ""
    for t in tags.split(","):
        t = t.strip().upper()
        if t:
            badges.append(f"[{t}]")
    if ev.get("level") == "ERROR":
        badges.append("[ERROR]")
    if ev.get("event_id") is not None:
        badges.append(f"[EID:{ev['event_id']}]")
    return badges


class Analyzer:
    """Generates reports from the EventStore."""

    def __init__(self, store: EventStore):
        self.store = store

    def generate_report(
        self,
        window_key: str,
        *,
        level_filter: str | None = None,
        source_type_filter: str | None = None,
        provider_filter: str | None = None,
        event_id_filter: int | None = None,
        file_filter: str | None = None,
        search_text: str | None = None,
    ) -> Report | None:
        """Build a full report for the given time window."""
        end_time = self.store.end_of_logs()
        if end_time is None:
            return None

        window = WINDOWS.get(window_key, timedelta(days=1))
        label = WINDOW_LABELS.get(window_key, window_key)
        start_time = end_time - window

        report = Report(
            window_label=label,
            end_time=end_time,
            start_time=start_time,
        )

        # 1) Storms (high confidence)
        storms = self.store.storm_groups(end_time, window)
        if storms:
            storm_section = ReportSection(heading="⚠ Repeating / Storming Events")
            for sg in storms:
                cites = []
                for s in sg.get("samples", []):
                    cites.append(_citation_from_event(s))
                ts_range = ""
                if sg.get("first_seen") and sg.get("last_seen"):
                    ts_range = f"{sg['first_seen']} – {sg['last_seen']}"
                storm_section.bullets.append(
                    ReportBullet(
                        timestamp_range=ts_range,
                        summary=(str(sg.get("message", "")) or "")[:200],
                        badges=[f"[×{sg['cnt']}]"],
                        citations=cites,
                        level=sg.get("level", "UNKNOWN"),
                        repeat_count=sg.get("cnt"),
                    )
                )
            report.sections.append(storm_section)

        # 2) Last errors (high confidence)
        last_errs = self.store.last_errors(end_time, window)
        if last_errs:
            err_section = ReportSection(heading="🔴 Last Unique Error Signatures")
            for ev in last_errs:
                err_section.bullets.append(
                    ReportBullet(
                        timestamp_range=str(ev.get("event_time_str", "")),
                        summary=str(ev.get("message", ""))[:300],
                        badges=_badges_from_event(ev),
                        citations=[_citation_from_event(ev)],
                        level="ERROR",
                    )
                )
            report.sections.append(err_section)

        # 3) Boot / shutdown markers
        boot_shut = self._boot_shutdown_events(end_time, window)
        if boot_shut:
            bs_section = ReportSection(heading="🔄 Boot / Shutdown Lifecycle")
            for ev in boot_shut:
                bs_section.bullets.append(
                    ReportBullet(
                        timestamp_range=str(ev.get("event_time_str", "")),
                        summary=str(ev.get("message", ""))[:300],
                        badges=_badges_from_event(ev),
                        citations=[_citation_from_event(ev)],
                        level=ev.get("level", "INFO"),
                    )
                )
            report.sections.append(bs_section)

        # 4) Full timeline (with filters applied)
        events = self.store.query_window(
            end_time,
            window,
            level_filter=level_filter,
            source_type_filter=source_type_filter,
            provider_filter=provider_filter,
            event_id_filter=event_id_filter,
            file_filter=file_filter,
            search_text=search_text,
            limit=2000,
        )
        report.total_events = len(events)
        if events:
            tl_section = ReportSection(
                heading=f"📋 Timeline ({label} leading to end of logs, working backwards)"
            )
            for ev in events:
                tl_section.bullets.append(
                    ReportBullet(
                        timestamp_range=str(ev.get("event_time_str", "")),
                        summary=str(ev.get("message", ""))[:300],
                        badges=_badges_from_event(ev),
                        citations=[_citation_from_event(ev)],
                        level=ev.get("level", "UNKNOWN"),
                    )
                )
            report.sections.append(tl_section)

        return report

    def _boot_shutdown_events(
        self, end_time: datetime, window: timedelta
    ) -> list[dict]:
        """Find boot/shutdown tagged events."""
        self.store.flush()
        start_time = end_time - window
        sql = """
            SELECT * FROM events
            WHERE event_time_utc BETWEEN ? AND ?
              AND (tags LIKE '%boot%' OR tags LIKE '%shutdown%'
                   OR tags LIKE '%crash%')
            ORDER BY event_time_utc DESC
            LIMIT 100
        """
        cols = [d[0] for d in self.store.con.execute(sql, [start_time, end_time]).description]
        rows = self.store.con.execute(sql, [start_time, end_time]).fetchall()
        return [dict(zip(cols, r)) for r in rows]
