"""
Redaction utility for LogNeedle.

Masks likely secrets (GUIDs, bearer tokens, API keys, hex strings, emails)
while preserving evidence references (file paths, line numbers).
"""

from __future__ import annotations

import re

# Pre-compiled patterns for secret-like strings
_PATTERNS: list[tuple[re.Pattern, str]] = [
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
