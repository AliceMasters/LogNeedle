"""
Verification test: cumulative multi-source timeline merging.

Scenario:
  1. Insert events from a "program log" (text source).
  2. Insert events from a "Windows Event Viewer" (evtx source).
  3. Verify the merged timeline interleaves them by timestamp.
  4. Verify that an error in the program log appearing at the same time
     as a crash event in the evtx log can be correlated.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from src.store.db import EventStore
from src.analysis.analyzer import Analyzer


def test_cumulative_timeline_merging():
    """
    Load events from two different log sources into one store and
    verify they merge into a single interleaved timeline.
    """
    store = EventStore()  # temp DB

    # Use naive datetimes since DuckDB returns naive datetimes
    base = datetime(2025, 11, 17, 6, 20, 0)

    # ── Source 1: Program log (SmartShield) ───────────────────────
    program_events = [
        (base + timedelta(seconds=0),  "INFO",  "Service started successfully"),
        (base + timedelta(seconds=30), "INFO",  "Heartbeat OK"),
        (base + timedelta(seconds=60), "WARN",  "High memory usage detected"),
        (base + timedelta(seconds=90), "ERROR", "Failed to send message to driver"),
        (base + timedelta(seconds=91), "ERROR", "Cannot communicate with driver module"),
        (base + timedelta(seconds=95), "ERROR", "Service entering failure state"),
    ]
    for idx, (ts, level, msg) in enumerate(program_events):
        store.insert_event(
            event_time_utc=ts,
            event_time_str=str(ts),
            source_type="text",
            source_file="SmartShieldService.log",
            line_start=idx + 1,
            level=level,
            message=msg,
            tags="driver" if "driver" in msg.lower() else "",
        )

    # ── Source 2: Windows Event Viewer (evtx) ────────────────────
    evtx_events = [
        (base + timedelta(seconds=10),  "INFO",  "System",
         "Microsoft-Windows-Kernel-General", 12, "boot",
         "Windows has started"),
        (base + timedelta(seconds=45),  "INFO",  "Application",
         "Application", 1000, "",
         "Application started normally"),
        (base + timedelta(seconds=88),  "WARN",  "System",
         "Microsoft-Windows-Kernel-Power", 109, "shutdown",
         "System power state change"),
        (base + timedelta(seconds=92),  "ERROR", "System",
         "Microsoft-Windows-WER-SystemErrorReporting", 1001, "crash",
         "Bugcheck: the computer has rebooted from a crash"),
        (base + timedelta(seconds=93),  "ERROR", "System",
         "Microsoft-Windows-Kernel-Power", 41, "shutdown,crash",
         "The system has rebooted without cleanly shutting down"),
    ]
    for idx, (ts, level, channel, provider, eid, tags, msg) in enumerate(evtx_events):
        store.insert_event(
            event_time_utc=ts,
            event_time_str=str(ts),
            source_type="evtx",
            source_file="System.evtx",
            evtx_log_name=channel,
            evtx_record_id=idx + 1,
            provider=provider,
            event_id=eid,
            level=level,
            message=msg,
            tags=tags,
        )

    store.flush()

    # ── Verify: total event count ─────────────────────────────────
    total = store.event_count()
    assert total == 11, f"Expected 11 total events, got {total}"
    print(f"  ✓ Total events: {total}")

    # ── Verify: merged timeline is ordered by timestamp ──────────
    end_time = base + timedelta(minutes=5)
    window = timedelta(minutes=5)
    events = store.query_window(end_time, window, limit=100)

    assert len(events) == 11, f"Expected 11 events in window, got {len(events)}"

    # Events come back newest-first, verify they interleave sources
    source_types_seen = set(e["source_type"] for e in events)
    assert source_types_seen == {"text", "evtx"}, (
        f"Expected both 'text' and 'evtx' sources, got {source_types_seen}"
    )
    print(f"  ✓ Both source types appear in merged timeline")

    # Verify chronological ordering (newest first)
    times = [e["event_time_utc"] for e in events]
    for i in range(len(times) - 1):
        assert times[i] >= times[i + 1], (
            f"Timeline not sorted! {times[i]} < {times[i+1]}"
        )
    print(f"  ✓ Timeline is correctly sorted by timestamp (newest first)")

    # ── Verify: interleaving — at second 85-96, text and evtx mix ─
    crash_start = base + timedelta(seconds=85)
    crash_end = base + timedelta(seconds=96)
    crash_window_events = [
        e for e in events
        if crash_start <= e["event_time_utc"] <= crash_end
    ]
    crash_sources = set(e["source_type"] for e in crash_window_events)
    assert crash_sources == {"text", "evtx"}, (
        f"Expected interleaving of both sources in crash window, got {crash_sources}"
    )
    print(f"  ✓ Sources are interleaved around the crash event ({len(crash_window_events)} events)")

    # Show the interleaved crash-window timeline
    print("\n  ── Crash-window timeline (t=85s to t=96s) ──")
    for e in sorted(crash_window_events, key=lambda x: x["event_time_utc"]):
        src = e["source_file"]
        ts = e["event_time_utc"]
        level = e["level"]
        msg = e["message"][:80]
        print(f"    [{ts}] [{e['source_type'].upper():4}] [{level:5}] {src}: {msg}")

    # ── Verify: analyzer produces a merged report ─────────────────
    analyzer = Analyzer(store)
    report = analyzer.generate_report("5m")

    assert report is not None, "Expected a non-None report"
    assert report.total_events == 11, f"Report should cover all 11 events, got {report.total_events}"
    print(f"\n  ✓ Analyzer report covers {report.total_events} events")

    # Check that the report has sections
    section_headings = [s.heading for s in report.sections]
    print(f"  ✓ Report sections: {section_headings}")

    # Boot/shutdown lifecycle should appear (from evtx tags)
    lifecycle = [s for s in report.sections if "Boot" in s.heading or "Lifecycle" in s.heading]
    assert len(lifecycle) > 0, "Expected Boot/Shutdown lifecycle section from evtx events"
    print(f"  ✓ Boot/Shutdown lifecycle section present")

    # Last errors should capture errors from BOTH sources
    err_sections = [s for s in report.sections if "Error" in s.heading]
    if err_sections:
        err_sources = set()
        for bullet in err_sections[0].bullets:
            for cite in bullet.citations:
                err_sources.add(cite.source_type)
        print(f"  ✓ Error section cites sources: {err_sources}")

    # ── Verify: source_type filter works ─────────────────────────
    evtx_only = store.query_window(
        end_time, window, source_type_filter="evtx", limit=100
    )
    text_only = store.query_window(
        end_time, window, source_type_filter="text", limit=100
    )
    assert all(e["source_type"] == "evtx" for e in evtx_only)
    assert all(e["source_type"] == "text" for e in text_only)
    assert len(evtx_only) == 5
    assert len(text_only) == 6
    print(f"  ✓ Source type filters work (evtx={len(evtx_only)}, text={len(text_only)})")

    # ── Verify: file filter works ─────────────────────────────────
    shield_only = store.query_window(
        end_time, window, file_filter="SmartShield", limit=100
    )
    assert all("SmartShield" in e["source_file"] for e in shield_only)
    assert len(shield_only) == 6
    print(f"  ✓ File filter works (SmartShield → {len(shield_only)} events)")

    # ── Verify: source_files() lists both ─────────────────────────
    files = store.source_files()
    assert "SmartShieldService.log" in files
    assert "System.evtx" in files
    print(f"  ✓ source_files() lists both: {files}")

    # ── Verify: providers() lists evtx providers ─────────────────
    provs = store.providers()
    assert any("Kernel" in p for p in provs)
    print(f"  ✓ providers() returns evtx providers: {provs}")

    store.close()
    print("\n  ✅ PASS: Cumulative multi-source timeline merging works correctly!")


if __name__ == "__main__":
    try:
        test_cumulative_timeline_merging()
    except AssertionError as e:
        print(f"\n  ❌ FAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
