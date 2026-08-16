"""Centralized application logging with redaction for Trackher."""

from __future__ import annotations

import io
import logging
import os
import re
import sys
from typing import Any


LOGGER_NAME = "trackher"
DEFAULT_LOG_LEVEL = "WARNING"

_EMAIL_PATTERN = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@(?:[a-zA-Z0-9\-]+\.)+[A-Za-z]{2,}\b"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]{8,})")
_TOKEN_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*?(?:api[_-]?key|token|secret|password|passwd|authorization))\b"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\",;]{6,})(\3)"
)
_HIBP_HEADER_PATTERN = re.compile(r"(?i)(hibp-api-key\s*[:=]\s*)([^\s,;]+)")
_LONG_HEX_PATTERN = re.compile(r"\b[a-fA-F0-9]{32,}\b")


def redact_sensitive_text(value: object) -> str:
    """Redact likely secrets and target identifiers from log output."""
    text = str(value)
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED_TOKEN]", text)
    text = _TOKEN_ASSIGNMENT_PATTERN.sub(r"\1\2\3[REDACTED]\5", text)
    text = _HIBP_HEADER_PATTERN.sub(r"\1[REDACTED]", text)
    text = _LONG_HEX_PATTERN.sub("[REDACTED_HEX]", text)
    return text


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        key: redact_sensitive_text(value) for key, value in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(redact_sensitive_text(value) for value in record.args)
                else:
                    record.args = redact_sensitive_text(record.args)
            record.msg = redact_sensitive_text(record.msg)
        except Exception:
            record.msg = "[log redaction failed]"
            record.args = ()
        return True


class SafeStreamHandler(logging.StreamHandler):
    """Logging handler that never raises back into scan/runtime code."""

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        try:
            stream = self.stream if isinstance(self.stream, io.TextIOBase) else sys.stderr
            stream.write("Trackher logging failure suppressed.\n")
        except Exception:
            pass


def _normalize_level(level: str | None) -> int:
    raw_level = (level or os.environ.get("TRACKHER_LOG_LEVEL", DEFAULT_LOG_LEVEL)).strip().upper()
    return getattr(logging, raw_level, logging.WARNING)


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure Trackher root logger once."""
    logger = logging.getLogger(LOGGER_NAME)
    configured = getattr(logger, "_trackher_configured", False)
    if configured:
        logger.setLevel(_normalize_level(level))
        return logger

    handler = SafeStreamHandler()
    handler.setLevel(logging.NOTSET)
    handler.addFilter(_RedactionFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(_normalize_level(level))
    logger.propagate = False
    logger._trackher_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    root = configure_logging()
    if not name:
        return root
    return root.getChild(name)


def safe_log(logger: logging.Logger, level: int, message: str, *args: Any, **kwargs: Any) -> None:
    """Emit a log entry without allowing logging errors to affect application flow."""
    try:
        logger.log(level, message, *args, **kwargs)
    except Exception:
        pass
