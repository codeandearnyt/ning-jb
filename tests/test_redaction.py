"""Redaction is a structural guarantee, not a convention."""

from __future__ import annotations

import io
import json
import logging

import pytest

from ningx.observability.logging import RedactionFilter, build_console_handler
from ningx.observability.redaction import (
    REDACTED,
    contains_secret,
    redact_mapping,
    redact_text,
)


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ("Authorization: Bearer abcdef1234567890xyz", "abcdef1234567890"),
        ("GEMINI_KEY=AIzaSyD-1234567890abcdefghijklmnop", "AIzaSyD-1234567890"),
        ("openai sk-proj-abcdefghijklmnopqrstuvwxyz", "sk-proj-abcdefghijkl"),
        ("token=ghp_abcdefghijklmnopqrstuvwxyz123456", "ghp_abcdefghijklmnop"),
        ("https://user:hunter2@example.com/v1", "hunter2"),
        ("api_key=super-secret-value", "super-secret-value"),
        ("password: correct-horse-battery", "correct-horse-battery"),
        ("x-api-key: 9f8e7d6c5b4a", "9f8e7d6c5b4a"),
    ],
)
def test_redact_text_removes_credentials(raw: str, needle: str) -> None:
    cleaned = redact_text(raw)
    assert needle not in cleaned
    assert REDACTED in cleaned


def test_redact_text_leaves_ordinary_text_alone() -> None:
    message = "CPU 42% across 8 logical processors; commit charge 11.2 GB"
    assert redact_text(message) == message
    assert not contains_secret(message)


def test_redact_mapping_by_key_and_by_value() -> None:
    payload = {
        "provider": "gemini",
        "api_key": "plain-value",
        "nested": {"token": "also-secret", "note": "Bearer abcdefghijklmnop"},
        "items": ["sk-abcdefghijklmnopqrst", "harmless"],
    }
    cleaned = redact_mapping(payload)
    assert cleaned["provider"] == "gemini"
    assert cleaned["api_key"] == REDACTED
    assert cleaned["nested"]["token"] == REDACTED
    assert "abcdefghijklmnop" not in cleaned["nested"]["note"]
    assert cleaned["items"][0].startswith("sk-")
    assert "abcdefghijklmnopqrst" not in cleaned["items"][0]
    assert cleaned["items"][1] == "harmless"


def test_logging_filter_prevents_secret_from_reaching_handler() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("ningx.test.redaction")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = build_console_handler(stream)
    assert handler.filters and isinstance(handler.filters[0], RedactionFilter)
    logger.addHandler(handler)

    logger.info("provider call failed", extra={"api_key": "sk-abcdefghijklmnopqrst", "url": "https://x.test"})
    logger.error("Authorization: Bearer abcdef1234567890xyz")

    output = stream.getvalue()
    assert "abcdefghijklmnopqrst" not in output
    assert "abcdef1234567890" not in output
    assert "redacted" in output

    for line in output.strip().splitlines():
        json.loads(line)  # every line is valid JSON


def test_filter_survives_unprintable_args() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("ningx.test.redaction.args")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(build_console_handler(stream))

    logger.info("value=%s", {"api_key": "secret-in-arg"})
    assert "secret-in-arg" not in stream.getvalue()
