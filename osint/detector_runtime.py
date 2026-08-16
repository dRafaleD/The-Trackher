"""Shared detector runtime helpers for Trackher OSINT checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar


TResult = TypeVar("TResult")


class AsyncDetector(Protocol):
    """Small shared async detector interface used by email and username checks."""

    def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[dict[str, Any]]:
        ...


class DetectorRegistry:
    """Minimal detector registry that keeps execution wiring explicit."""

    def __init__(self) -> None:
        self._detectors: dict[str, AsyncDetector] = {}

    def register(self, name: str, detector: AsyncDetector) -> None:
        self._detectors[str(name)] = detector

    def get(self, name: str) -> AsyncDetector | None:
        return self._detectors.get(str(name))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._detectors))


async def safe_execute(
    detector: Callable[[], Awaitable[TResult]],
    *,
    on_error: Callable[[Exception], TResult],
) -> TResult:
    """Run a detector and isolate unexpected execution failures."""

    try:
        return await detector()
    except Exception as exc:  # pragma: no cover - exercised through callers
        return on_error(exc)


def normalize_email_result(
    platform: dict[str, Any],
    status: str,
    detail: str = "",
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "service": platform["name"],
        "category": platform.get("category", "manual"),
        "status": status,
        "found": status == "FOUND",
        "detail": detail,
        "url": platform.get("url", ""),
    }
    if extra:
        result.update(extra)
    return result


def normalize_breach_result(
    platform: dict[str, Any],
    status: str,
    detail: str = "",
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "service": platform["name"],
        "section": platform.get("section", "breach"),
        "status": status,
        "found": status == "FOUND",
        "detail": detail,
        "breaches": [],
    }
    if extra:
        result.update(extra)
    return result


def normalize_username_result(
    platform: dict[str, Any],
    *,
    url: str = "",
    status: str = "unknown",
    detail: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "platform": str(platform.get("name", "Bilinmeyen")),
        "url": url,
        "found": status == "found",
        "status": status,
        "detail": detail,
        "reliability": str(platform.get("reliability", "unreliable")),
    }
    if extra:
        result.update(extra)
    result["found"] = result.get("status") == "found"
    return result
