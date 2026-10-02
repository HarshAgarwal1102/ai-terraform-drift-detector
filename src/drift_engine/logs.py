"""Structured logging for drift_engine (Task 4.7), standard library `logging` only.

The package is silent by default: its root logger `drift_engine` has a
NullHandler, so library callers and scripts/detect_drift.py see no new output.
Applications opt in with `configure_logging()` (the CLI does so with --log-level).

Every engine log record is an *event*: a stable `event` name, a human message and
a `fields` mapping, e.g. event `classification_finished` with fields
`{"outcome": "succeeded", "has_drift": true, ...}`. Fields carry identifiers,
counts, stages and reasons only, never attribute values, so sensitive values from
plan.json cannot reach a log event. The one exception is the CLI's handling of an
unexpected internal error: it logs the traceback at DEBUG, and that traceback holds
whatever message the exception carried.

Logs go to the configured stream (standard error for the CLI) and never into a
report, so reports stay deterministic.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import IO, Any

LOGGER_NAME = "drift_engine"
LOG_FORMATS = ("text", "json")
LOG_LEVELS = ("debug", "info", "warning", "error")

_HANDLER_MARK = "_drift_engine_handler"


def log_event(logger: logging.Logger, level: int, event: str, message: str, **fields: Any) -> None:
    """Log one structured event; `fields` must not contain attribute values."""
    if logger.isEnabledFor(level):
        # stacklevel=2: the record points at the caller, not at this helper
        logger.log(level, message, extra={"event": event, "fields": fields}, stacklevel=2)


def _payload(record: logging.LogRecord) -> dict:
    return {
        "event": getattr(record, "event", None),
        "fields": getattr(record, "fields", None) or {},
    }


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, event, message, fields, exception."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            **_payload(record),
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, sort_keys=True, default=str)


class TextFormatter(logging.Formatter):
    """`time LEVEL logger event: message key=value ...` (values JSON-encoded)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = _payload(record)
        time = datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds")
        event = f" {payload['event']}" if payload["event"] else ""
        fields = "".join(
            f" {k}={json.dumps(v, sort_keys=True, default=str)}" for k, v in sorted(payload["fields"].items())
        )
        line = f"{time} {record.levelname} {record.name}{event}: {record.getMessage()}{fields}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str = "warning", fmt: str = "text", stream: IO[str] | None = None) -> logging.Handler:
    """Send drift_engine logs at `level` and above to `stream` (default: standard error).

    Replaces a handler installed by an earlier call, so it can be called repeatedly.
    Returns the handler (remove it with `logger.removeHandler` to undo).
    """
    if level not in LOG_LEVELS:
        raise ValueError(f"unknown log level {level!r}; expected one of {', '.join(LOG_LEVELS)}")
    if fmt not in LOG_FORMATS:
        raise ValueError(f"unknown log format {fmt!r}; expected one of {', '.join(LOG_FORMATS)}")
    logger = logging.getLogger(LOGGER_NAME)
    for old in [h for h in logger.handlers if getattr(h, _HANDLER_MARK, False)]:
        logger.removeHandler(old)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    setattr(handler, _HANDLER_MARK, True)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    return handler
