"""Secret redaction.

Every log record, audit row and crash bundle passes through here. The rules are
deliberately pattern-based: we redact things that *look like* credentials even
when we did not know they were present, because the alternative is leaking an
API key into a support bundle.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "\u00abredacted\u00bb"

SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|secret|token|password|passwd|credential|authorization"
    r"|bearer|cookie|private[_-]?key|access[_-]?key|session[_-]?id)",
    re.IGNORECASE,
)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}"), f"Bearer {REDACTED}"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"), f"sk-{REDACTED}"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), f"AIza{REDACTED}"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), f"gh_{REDACTED}"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_\-]{16,}"), f"nvapi-{REDACTED}"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), f"gsk_{REDACTED}"),
)

_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|access[_-]?key)"
    r"(\s*[:=]\s*)([^\s,;'\"&]{4,})"
)

_URL_CREDENTIAL_RE = re.compile(r"(?i)\b(https?://[^\s:/@]+):([^\s/@]+)@")


def redact_text(value: str) -> str:
    """Return ``value`` with credential-shaped substrings replaced."""
    if not value:
        return value
    result = value
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    result = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", result)
    return _URL_CREDENTIAL_RE.sub(lambda m: f"{m.group(1)}:{REDACTED}@", result)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact a mapping by key name and by value pattern."""
    out: dict[str, Any] = {}
    for key, item in value.items():
        if SENSITIVE_KEY_RE.search(str(key)):
            out[key] = REDACTED
        else:
            out[key] = _redact_value(item)
    return out


def _redact_value(item: Any) -> Any:
    if isinstance(item, str):
        return redact_text(item)
    if isinstance(item, Mapping):
        return redact_mapping(item)
    if isinstance(item, list):
        return [_redact_value(entry) for entry in item]
    if isinstance(item, tuple):
        return tuple(_redact_value(entry) for entry in item)
    return item


def contains_secret(value: str) -> bool:
    """True when redaction would change the string. Used by tests and guards."""
    return redact_text(value) != value


__all__ = [
    "REDACTED",
    "SENSITIVE_KEY_RE",
    "contains_secret",
    "redact_mapping",
    "redact_text",
]
