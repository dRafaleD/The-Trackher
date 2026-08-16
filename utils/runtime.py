"""Runtime validation helpers for local Trackher state."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from utils.app_logging import get_logger, safe_log


def _ensure_dir(path: Path, *, label: str, logger) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return {"name": label, "path": str(path), "ready": True}
    except OSError as exc:
        safe_log(logger, logging.WARNING, "Runtime directory unavailable for %s at %s: %s", label, path, exc)
        return {
            "name": label,
            "path": str(path),
            "ready": False,
            "warning": f"{label} directory is unavailable",
        }


def validate_runtime() -> dict[str, Any]:
    """Prepare optional local state directories without failing startup."""
    from utils.history import get_history_dir
    from utils.platform_health import get_health_dir

    logger = get_logger("runtime")
    checks = [
        _ensure_dir(get_history_dir() / "snapshots", label="history", logger=logger),
        _ensure_dir(get_health_dir(), label="health", logger=logger),
    ]
    warnings = [item["warning"] for item in checks if item.get("warning")]
    return {
        "ready": not warnings,
        "checks": checks,
        "warnings": warnings,
    }
