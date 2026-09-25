"""
Redaction utility for LogNeedle.

Masks likely secrets (GUIDs, bearer tokens, API keys, JWTs, AWS access keys,
PEM private keys, hex strings, emails, and Windows profile usernames) while
preserving evidence references (file paths, line numbers).
"""

from __future__ import annotations

import re

# Pre-compiled patterns for secret-like strings
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # PEM private key blocks (multi-line)
    (
        re.compile(
            r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED-PRIVATE-KEY]",
    ),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]{20,}", re.I), r"\1[REDACTED]"),
    # API key patterns  (key=..., api_key=..., apikey:, token=)
    (
        re.compile(
            r"((?:api[_-]?key|token|secret|password|authorization)\s*[:=]\s*)[^\s,;\"']{8,}",
            re.I,
        ),
        r"\1[REDACTED]",
    ),
    # Standalone JWTs (header.payload.signature)
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), "[REDACTED-JWT]"),
    # AWS access key IDs
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
    # Windows profile usernames (keep the rest of the path as evidence)
    (
        re.compile(r"(\b[A-Za-z]:\\Users\\)(?!(?:Public|Default|All Users)\\)[^\\/:*?\"<>|\r\n]+", re.I),
        r"\1[USER]",
    ),
    # GUIDs / UUIDs
    (
        re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
        "[REDACTED-GUID]",
    ),
    # Long hex strings (32+ chars, likely hashes or tokens)
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[REDACTED-HEX]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED-EMAIL]"),
]


def redact_secrets(text: str) -> str:
    """Apply all redaction patterns to *text* and return the cleaned version."""
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text
