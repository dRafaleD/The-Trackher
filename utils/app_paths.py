"""Resource and launcher helpers for source, installed, and frozen Trackher runs."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running from a frozen executable bundle."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Return the source or installed module root."""
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """Return the active bundle root when frozen, otherwise the project root."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return project_root()


def resource_path(*parts: str) -> Path:
    """Resolve a runtime resource from a frozen bundle or source tree."""
    relative = Path(*parts)
    candidates = [
        bundle_root() / relative,
        Path(sys.executable).resolve().parent / relative,
        Path(sys.prefix).resolve() / relative,
        project_root() / relative,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return project_root() / relative


def launcher_arguments(*args: str) -> list[str]:
    """Return a safe launcher command for scheduled or shell-integrated runs."""
    if is_frozen():
        return [str(Path(sys.executable)), *args]
    return [sys.executable, str(project_root() / "main.py"), *args]
