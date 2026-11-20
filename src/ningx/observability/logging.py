"""Structured logging with a redaction guarantee.

The redaction filter runs before any handler formats the record, so a secret
cannot reach a file, the console, or a crash report even if a caller logs it by
mistake. This is a structural guarantee, not a code-review convention.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ningx.observability.redaction import redact_mapping, redact_text

_STANDARD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "thread", "threadName", "taskName",
    }
)


class RedactionFilter(logging.Filter):
    """Rewrite a record in place so secrets never reach a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                record.args = _redact_args(record.args)
            for key, value in tuple(record.__dict__.items()):
                if key in _STANDARD_ATTRS:
                    continue
                if isinstance(value, str):
                    record.__dict__[key] = redact_text(value)
                elif isinstance(value, Mapping):
                    record.__dict__[key] = redact_mapping(value)
        except Exception:
            return True
        return True


def _redact_args(args: object) -> Any:
    if isinstance(args, Mapping):
        return redact_mapping(args)
    if isinstance(args, tuple):
        return tuple(_redact_args(a) for a in args)
    if isinstance(args, str):
        return redact_text(args)
    return args


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Machine-readable, greppable, redaction-safe."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True, default=str)


def build_console_handler(stream: Any | None = None) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    return handler


def build_file_handler(log_dir: Path, *, filename: str = "ningx.log") -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / filename,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    return handler


def configure_logging(
    log_dir: Path | None,
    *,
    level: int = logging.INFO,
    console: bool = True,
    stream: Any | None = None,
) -> logging.Logger:
    """Install exactly one configured handler set on the ``ningx`` logger."""
    logger = logging.getLogger("ningx")
    logger.setLevel(level)
    logger.propagate = False
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()
    if console:
        logger.addHandler(build_console_handler(stream))
    if log_dir is not None:
        logger.addHandler(build_file_handler(log_dir))
    return logger


__all__ = [
    "JsonFormatter",
    "RedactionFilter",
    "build_console_handler",
    "build_file_handler",
    "configure_logging",
]
