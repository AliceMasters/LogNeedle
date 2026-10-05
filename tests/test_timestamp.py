"""
Unit tests for LogNeedle - timestamp parsing patterns.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.parsers.timestamp import parse_timestamp


def local_to_utc(*args):
    """The UTC instant for a wall-clock time on this machine (what a zone-less log line means)."""
    return datetime(*args).astimezone(timezone.utc)


def test_iso8601_utc():
    dt, raw, assumed = parse_timestamp("2025-11-17T06:22:13.123Z some log message")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025
    assert dt.hour == 6  # explicit Z: no local conversion
    assert dt.minute == 22
    assert not assumed


def test_iso8601_offset():
    dt, raw, assumed = parse_timestamp("2025-11-17T06:22:13+05:00 message")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 1  # 06:22 +05:00 -> 01:22 UTC
    assert not assumed


def test_dash_separated():
    dt, raw, assumed = parse_timestamp("2025-11-17 14:30:00.500  INFO  Starting")
    assert dt == local_to_utc(2025, 11, 17, 14, 30, 0, 500000)
    assert assumed  # no tz info


def test_slash_separated():
    dt, raw, assumed = parse_timestamp("2025/01/05 08:00:00 Service starting")
    # Compare instants, not calendar fields: east of UTC this is still 4 Jan in UTC.
    assert dt == local_to_utc(2025, 1, 5, 8, 0, 0)
    assert assumed


def test_syslog_style():
    dt, raw, assumed = parse_timestamp("Nov 17 06:22:13 myhost kernel: something", reference_year=2025)
    assert dt is not None
    assert dt == local_to_utc(2025, 11, 17, 6, 22, 13)
    assert assumed


def test_us_datetime():
    dt, raw, assumed = parse_timestamp("11/17/2025 2:30:00 PM  Action executed")
    assert dt == local_to_utc(2025, 11, 17, 14, 30, 0)
    assert assumed


def test_no_timestamp():
    dt, raw, assumed = parse_timestamp("Just a random line with no date")
    assert dt is None
    assert raw == ""


def test_partial_garbage():
    dt, raw, assumed = parse_timestamp("####!!!! not a date at all")
    assert dt is None


# -- run tests --

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            print(f"  FAIL {t.__name__}: EXCEPTION {e}")
    print(f"\n{passed}/{len(tests)} passed")


def test_naive_and_utc_sources_align():
    """Regression: a zone-less line is local time, not UTC.

    The same instant written as local wall-clock and as explicit UTC must parse to
    the same moment, or a bundle mixing log formats produces an out-of-order
    timeline on any machine not set to UTC. CI runs this under a non-UTC TZ.
    """
    instant = local_to_utc(2026, 9, 14, 2, 25, 0)
    naive, _, assumed_naive = parse_timestamp("2026-09-14 02:25:00 ERROR disk full")
    zulu, _, assumed_zulu = parse_timestamp(f"{instant:%Y-%m-%dT%H:%M:%S}Z ERROR disk full")
    assert naive == zulu == instant
    assert assumed_naive and not assumed_zulu
