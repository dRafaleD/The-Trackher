"""Polite, profile-aware request scheduling for public OSINT endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60.0


@dataclass
class _OriginRequestState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_allowed_at: float = 0.0
    cooldown_until: float = 0.0


def _origin_key(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown-origin"


def _bounded_interval(value: object, default: float) -> float:
    try:
        return max(0.0, min(float(value), 30.0))
    except (TypeError, ValueError):
        return default


def _retry_after_seconds(response: httpx.Response, default: float) -> float:
    raw_value = response.headers.get("Retry-After", "").strip()
    try:
        return max(1.0, min(float(raw_value), 600.0))
    except (TypeError, ValueError):
        return default


class _ScopedPoliteClient:
    def __init__(
        self,
        parent: "PoliteAsyncClient",
        *,
        rate_limit_key: str | None,
        interval_seconds: float,
    ) -> None:
        self._parent = parent
        self._rate_limit_key = rate_limit_key
        self._interval_seconds = interval_seconds

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return await self._parent.request(
            method,
            url,
            rate_limit_key=self._rate_limit_key,
            interval_seconds=self._interval_seconds,
            **kwargs,
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


class PoliteAsyncClient:
    """Serialize requests per site and pause an origin after HTTP 429."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_concurrent: int = 4,
        origin_interval_seconds: float = 1.0,
        rate_limit_cooldown_seconds: float = DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
    ) -> None:
        self._client = client
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._origin_interval_seconds = _bounded_interval(origin_interval_seconds, 1.0)
        self._rate_limit_cooldown_seconds = max(1.0, rate_limit_cooldown_seconds)
        self._states: dict[str, _OriginRequestState] = {}
        self._states_lock = asyncio.Lock()

    def for_platform(self, platform: dict[str, Any]) -> _ScopedPoliteClient:
        raw_key = str(platform.get("rate_limit_key", "")).strip().casefold()
        interval = max(
            self._origin_interval_seconds,
            _bounded_interval(
                platform.get("min_request_interval_seconds"),
                self._origin_interval_seconds,
            ),
        )
        return _ScopedPoliteClient(
            self,
            rate_limit_key=raw_key or None,
            interval_seconds=interval,
        )

    async def _state_for(self, key: str) -> _OriginRequestState:
        async with self._states_lock:
            return self._states.setdefault(key, _OriginRequestState())

    async def request(
        self,
        method: str,
        url: str,
        *,
        rate_limit_key: str | None = None,
        interval_seconds: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        state = await self._state_for(rate_limit_key or _origin_key(url))
        interval = _bounded_interval(interval_seconds, self._origin_interval_seconds)
        loop = asyncio.get_running_loop()

        async with state.lock:
            now = loop.time()
            if state.cooldown_until > now:
                remaining = max(1, round(state.cooldown_until - now))
                return httpx.Response(
                    429,
                    request=httpx.Request(method, url),
                    headers={"Retry-After": str(remaining), "X-Trackher-Cooldown": "1"},
                    text="Trackher paused this site after HTTP 429.",
                )

            delay = state.next_allowed_at - now
            if delay > 0:
                await asyncio.sleep(delay)

            try:
                async with self._semaphore:
                    response = await self._client.request(method, url, **kwargs)
            except Exception:
                state.next_allowed_at = loop.time() + interval
                raise

            state.next_allowed_at = loop.time() + interval
            if response.status_code == 429:
                cooldown = _retry_after_seconds(response, self._rate_limit_cooldown_seconds)
                state.cooldown_until = max(state.cooldown_until, loop.time() + cooldown)
            return response

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
