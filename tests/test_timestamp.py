"""
Unit tests for LogNeedle - timestamp parsing patterns.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.parsers.timestamp import parse_timestamp


def test_iso8601_utc():
    dt, raw, assumed = parse_timestamp("2025-11-17T06:22:13.123Z some log message")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025
    assert dt.month == 11
    assert dt.day == 17
    assert dt.hour == 6
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
    assert dt is not None
    assert dt.year == 2025
    assert dt.hour == 14
    assert assumed  # no tz info


def test_slash_separated():
    dt, raw, assumed = parse_timestamp("2025/01/05 08:00:00 Service starting")
    assert dt is not None
    assert dt.month == 1
    assert dt.day == 5
    assert assumed


def test_syslog_style():
    dt, raw, assumed = parse_timestamp("Nov 17 06:22:13 myhost kernel: something", reference_year=2025)
    assert dt is not None
    assert dt.month == 11
    assert dt.day == 17
    assert dt.hour == 6
    assert assumed


def test_us_datetime():
    dt, raw, assumed = parse_timestamp("11/17/2025 2:30:00 PM  Action executed")
    assert dt is not None
    assert dt.hour == 14
    assert dt.minute == 30
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
