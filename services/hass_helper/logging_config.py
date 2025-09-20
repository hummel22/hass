"""Logging helpers for the hass_helper service."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict


_RESERVED_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


def _serialise(value: Any) -> Any:
    """Return a JSON-serialisable representation of *value*."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _serialise(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise(item) for item in value]
    return str(value)


class JsonFormatter(logging.Formatter):
    """Formatter that renders log records as JSON objects."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - inherited docstring
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.default_time_format),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_FIELDS
        }
        if extras:
            payload.update({key: _serialise(value) for key, value in extras.items()})

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = record.stack_info

        return json.dumps(payload, separators=(",", ":"))


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging for the hass_helper service."""

    logger = logging.getLogger("hass_helper")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    http_logger = logging.getLogger("hass_helper.http")
    http_logger.setLevel(logging.DEBUG)


__all__ = ["setup_logging"]

