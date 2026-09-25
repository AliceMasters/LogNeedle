"""
Unit tests for LogNeedle - redaction utility.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.redact import redact_secrets


def test_guid_redaction():
    text = "Session ID: 550e8400-e29b-41d4-a716-446655440000 created"
    result = redact_secrets(text)
    assert "[REDACTED-GUID]" in result
    assert "550e8400" not in result
    print("  PASS GUID redacted")


def test_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    result = redact_secrets(text)
    assert "[REDACTED]" in result
    assert "eyJhbGci" not in result
    print("  PASS Bearer token redacted")


def test_api_key():
    text = "api_key=sk_live_abcdefghijklmnop1234"
    result = redact_secrets(text)
    assert "[REDACTED]" in result
    assert "sk_live" not in result
    print("  PASS API key redacted")


def test_email():
    text = "User alice@example.com logged in"
    result = redact_secrets(text)
    assert "[REDACTED-EMAIL]" in result
    assert "alice@example.com" not in result
    print("  PASS Email redacted")


def test_evidence_preserved():
    """File paths and line numbers must NOT be redacted."""
    text = "Source: logs/SmartShieldService2025-11-17.txt L2940-L2944"
    result = redact_secrets(text)
    assert "SmartShieldService" in result
    assert "L2940" in result
    print("  PASS Evidence citation preserved")


def test_standalone_jwt():
    text = "cookie session=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk rejected"
    result = redact_secrets(text)
    assert "eyJzdWIi" not in result
    assert "rejected" in result
    print("  PASS Standalone JWT redacted")


def test_aws_access_key():
    text = "Using credentials AKIAIOSFODNN7EXAMPLE for s3 upload"
    result = redact_secrets(text)
    assert "[REDACTED-AWS-KEY]" in result
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    print("  PASS AWS access key redacted")


def test_private_key_block():
    text = (
        "loaded cert\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7x\nabc123\n"
        "-----END RSA PRIVATE KEY-----\nhandshake ok"
    )
    result = redact_secrets(text)
    assert "[REDACTED-PRIVATE-KEY]" in result
    assert "MIIEowIBAAKCAQEA7x" not in result
    assert "handshake ok" in result
    print("  PASS PEM private key redacted")


def test_windows_profile_username():
    text = r"Failed to open C:\Users\jsmith\AppData\Local\App\config.json"
    result = redact_secrets(text)
    assert "jsmith" not in result
    assert r"C:\Users\[USER]\AppData\Local\App\config.json" in result
    print("  PASS Windows profile username redacted")


def test_shared_profiles_not_redacted():
    text = r"Wrote C:\Users\Public\Documents\report.txt"
    assert redact_secrets(text) == text
    print("  PASS Shared profile path preserved")


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
