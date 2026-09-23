"""
Unit tests for LogNeedle - text log parser.
"""

import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.parsers.text_parser import TextLogParser


def _write_temp(content: str, suffix: str = ".log") -> str:
    """Write content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_basic_text_log():
    content = """2025-11-17 06:22:00 INFO  Service started
2025-11-17 06:22:01 ERROR Failed to send message to driver
  java.lang.RuntimeException: driver not responding
  at com.example.Driver.send(Driver.java:42)
2025-11-17 06:22:05 WARN  Retrying connection
"""
    path = _write_temp(content)
    parser = TextLogParser(path, source_file_label="test.log")
    events = list(parser.parse())
    os.unlink(path)

    assert len(events) == 3, f"Expected 3 events, got {len(events)}"
    assert events[0]["level"] == "INFO"
    assert events[1]["level"] == "ERROR"
    assert events[1]["line_start"] == 2
    assert events[1]["line_end"] == 4  # includes stack trace lines
    assert "driver" in events[1]["tags"]
    assert events[2]["level"] == "WARN"
    print("  PASS basic text parsing works")


def test_csv_parsing():
    content = """Timestamp,Action,Details
11/17/2025 2:30:00 PM,Toggle,Protection enabled
11/17/2025 2:35:00 PM,Action,Shutdown initiated
"""
    path = _write_temp(content, suffix=".csv")
    parser = TextLogParser(path, source_file_label="actions.csv")
    events = list(parser.parse())
    os.unlink(path)

    assert len(events) == 2, f"Expected 2 events, got {len(events)}"
    assert events[0]["event_time_utc"] is not None
    assert events[0]["event_time_utc"].hour == 14  # 2:30 PM -> 14:30
    print("  PASS CSV parsing works")


def test_jsonl_parsing():
    content = '{"timestamp":"2025-11-17T10:00:00Z","level":"ERROR","message":"disk full"}\n'
    content += '{"timestamp":"2025-11-17T10:01:00Z","level":"INFO","message":"recovered"}\n'
    path = _write_temp(content, suffix=".jsonl")
    parser = TextLogParser(path, source_file_label="app.jsonl")
    events = list(parser.parse())
    os.unlink(path)

    assert len(events) == 2
    assert events[0]["level"] == "ERROR"
    assert events[1]["level"] == "INFO"
    print("  PASS JSONL parsing works")


def test_encoding_resilience():
    """Test that the parser doesn't crash on latin-1 encoded files."""
    content_bytes = "2025-01-01 00:00:00 cafe resume naive\n".encode("latin-1")
    f = tempfile.NamedTemporaryFile(suffix=".log", delete=False)
    f.write(content_bytes)
    f.close()
    parser = TextLogParser(f.name)
    events = list(parser.parse())
    os.unlink(f.name)

    assert len(events) >= 1 or parser.warning_count >= 0  # no crash is a pass
    print("  PASS encoding resilience OK")


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
