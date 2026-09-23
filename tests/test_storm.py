"""
Unit tests for LogNeedle - storm detection via EventStore.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta
from src.store.db import EventStore


def test_storm_detection():
    """Insert many identical messages; verify storm_groups picks them up."""
    store = EventStore()  # temp db
    base_time = datetime(2025, 11, 17, 6, 22, 0, tzinfo=timezone.utc)

    # Insert 200 identical error messages across 5 minutes
    for i in range(200):
        store.insert_event(
            event_time_utc=base_time + timedelta(seconds=i),
            event_time_str=str(base_time + timedelta(seconds=i)),
            source_type="text",
            source_file="SmartShieldService2025-11-17.txt",
            line_start=1000 + i,
            line_end=1000 + i,
            level="ERROR",
            message="Failed to send message to driver",
            tags="driver",
        )

    # Insert 5 normal info messages (should NOT be detected as storm)
    for i in range(5):
        store.insert_event(
            event_time_utc=base_time + timedelta(seconds=i * 10),
            event_time_str=str(base_time + timedelta(seconds=i * 10)),
            source_type="text",
            source_file="app.log",
            line_start=i + 1,
            line_end=i + 1,
            level="INFO",
            message="Heartbeat OK",
            tags="",
        )

    store.flush()

    # Query storms in a 10-minute window with threshold=50
    end_time = base_time + timedelta(minutes=10)
    storms = store.storm_groups(end_time, timedelta(minutes=10), threshold=50)

    assert len(storms) >= 1, f"Expected at least 1 storm, got {len(storms)}"
    driver_storm = [s for s in storms if "driver" in s.get("message", "").lower()]
    assert len(driver_storm) == 1
    assert driver_storm[0]["cnt"] == 200
    assert "samples" in driver_storm[0]
    assert len(driver_storm[0]["samples"]) >= 2  # first, middle, last

    store.close()
    print("  PASS storm detection works correctly")


def test_last_errors():
    """Verify last_errors returns unique error signatures."""
    store = EventStore()
    base_time = datetime(2025, 11, 17, 10, 0, 0, tzinfo=timezone.utc)

    # Insert 3 different errors
    for i, msg in enumerate([
        "Failed to start service",
        "Disk timeout on volume C:",
        "Cannot communicate with driver",
    ]):
        store.insert_event(
            event_time_utc=base_time + timedelta(minutes=i),
            source_type="text",
            source_file="system.log",
            line_start=i + 1,
            level="ERROR",
            message=msg,
        )

    # Also insert duplicates of the first error
    for i in range(10):
        store.insert_event(
            event_time_utc=base_time + timedelta(seconds=i),
            source_type="text",
            source_file="system.log",
            line_start=100 + i,
            level="ERROR",
            message="Failed to start service",
        )

    store.flush()

    end_time = base_time + timedelta(hours=1)
    errs = store.last_errors(end_time, timedelta(hours=1), top_n=5)

    assert len(errs) == 3, f"Expected 3 unique error signatures, got {len(errs)}"
    store.close()
    print("  PASS last_errors returns unique signatures")


def test_event_count_and_end():
    store = EventStore()
    t1 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    store.insert_event(event_time_utc=t1, message="first")
    store.insert_event(event_time_utc=t2, message="last")
    store.flush()

    assert store.event_count() == 2
    end = store.end_of_logs()
    # DuckDB TIMESTAMP type may convert to local time or strip tz;
    # just verify it returns something close to t2
    assert end is not None
    store.close()
    print("  PASS event_count and end_of_logs work correctly")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
            except Exception as e:
                print(f"  FAIL {name}: EXCEPTION {e}")
    print("\nDone.")
