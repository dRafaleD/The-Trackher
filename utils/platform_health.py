"""Separate platform and detector health checks for Trackher."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from osint.services import ACCOUNT_DETECTORS, ACCOUNT_PLATFORMS, BREACH_DETECTORS, BREACH_PLATFORMS
from osint.username_checker import USERNAME_DETECTORS, USERNAME_PLATFORMS
from utils import __version__
from utils.app_logging import get_logger, safe_log


HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
BROKEN = "BROKEN"
UNKNOWN = "UNKNOWN"

HEALTH_STATES = (HEALTHY, DEGRADED, BROKEN, UNKNOWN)
CACHE_TTL_SECONDS = 24 * 60 * 60
LATEST_SUMMARY_FILE = "latest_health_summary.json"
LIVE_CACHE_FILE = "live_health_cache.json"
PLACEHOLDER_EMAIL = "trackher-healthcheck@example.invalid"
PLACEHOLDER_USERNAME = "trackher_healthcheck_user_404"

_EMAIL_CATEGORIES = {"verified", "heuristic", "manual"}
_EMAIL_SECTIONS = {"account", "breach"}
_USERNAME_RELIABILITY = {"verified", "unreliable"}
_USERNAME_ERROR_TYPES = {"status_code", "message", "response_url"}
LOGGER = get_logger("platform_health")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def get_health_dir() -> Path:
    override = os.environ.get("TRACKHER_HEALTH_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return root / "Trackher" / "health"
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Trackher" / "health"
    root = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
    return root / "trackher" / "health"


def _cache_file(cache_dir: Path | None = None) -> Path:
    return (cache_dir or get_health_dir()) / LIVE_CACHE_FILE


def _summary_file(cache_dir: Path | None = None) -> Path:
    return (cache_dir or get_health_dir()) / LATEST_SUMMARY_FILE


def clear_health_cache(cache_dir: Path | None = None) -> dict[str, Any]:
    root = cache_dir or get_health_dir()
    removed = 0
    for path in (_cache_file(root), _summary_file(root)):
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError as exc:
            safe_log(LOGGER, logging.WARNING, "Failed to clear health cache file at %s: %s", path, exc)
    return {"cleared": True, "removed_files": removed, "path": str(root)}


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except (OSError, json.JSONDecodeError, ValueError):
        return default


def _write_json_file(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError as exc:
        safe_log(LOGGER, logging.WARNING, "Failed to write health cache/summary at %s: %s", path, exc)


def load_cached_health_summary(cache_dir: Path | None = None) -> dict[str, Any]:
    summary = _read_json_file(_summary_file(cache_dir), {})
    if not isinstance(summary, dict):
        return {}
    return summary


def _summary_line(counts: dict[str, int]) -> str:
    return (
        f"Healthy: {counts.get(HEALTHY, 0)} | "
        f"Degraded: {counts.get(DEGRADED, 0)} | "
        f"Broken: {counts.get(BROKEN, 0)} | "
        f"Unknown: {counts.get(UNKNOWN, 0)}"
    )


def _entry_id(scope: str, name: str) -> str:
    return f"{scope}:{name}"


def _issue(text: str) -> str:
    return str(text).strip()


def _offline_result(
    *,
    scope: str,
    platform_name: str,
    detector: str,
    issues: list[str],
) -> dict[str, Any]:
    state = BROKEN if issues else HEALTHY
    return {
        "id": _entry_id(scope, platform_name),
        "scope": scope,
        "platform": platform_name,
        "detector": detector,
        "state": state,
        "offline_state": state,
        "live_state": UNKNOWN,
        "live_supported": False,
        "issues": issues,
        "detail": "; ".join(issues) if issues else "Schema and detector configuration look valid.",
        "checked_at": _iso_now(),
    }


def _schema_health_email_account(platform_def: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    raw_name = str(platform_def.get("name", "")).strip()
    name = raw_name or "Unknown"
    detector = str(platform_def.get("check", "manual"))
    category = str(platform_def.get("category", "")).strip()
    section = str(platform_def.get("section", "account")).strip()

    if not raw_name:
        issues.append(_issue("Missing required field: name"))
    if category not in _EMAIL_CATEGORIES:
        issues.append(_issue(f"Invalid category: {category or 'missing'}"))
    if section not in _EMAIL_SECTIONS:
        issues.append(_issue(f"Invalid section: {section or 'missing'}"))
    if not str(platform_def.get("url", "")).strip():
        issues.append(_issue("Missing required field: url"))
    if ACCOUNT_DETECTORS.get(detector) is None:
        issues.append(_issue(f"Unsupported detector type: {detector}"))
    if detector in {"heuristic", "public_profile_email"} and not str(platform_def.get("probe_url", "")).strip():
        issues.append(_issue("Missing required field: probe_url"))
    if detector == "public_profile_email":
        if not str(platform_def.get("profile_email_field", "")).strip():
            issues.append(_issue("Missing required field: profile_email_field"))
        if not (
            str(platform_def.get("profile_url_field", "")).strip()
            or str(platform_def.get("profile_url_template", "")).strip()
        ):
            issues.append(_issue("Missing required field: profile_url_field or profile_url_template"))

    return _offline_result(
        scope="email_account",
        platform_name=name,
        detector=detector,
        issues=issues,
    )


def _schema_health_email_breach(platform_def: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    raw_name = str(platform_def.get("name", "")).strip()
    name = raw_name or "Unknown"
    detector = str(platform_def.get("check", "hibp"))
    category = str(platform_def.get("category", "")).strip()
    section = str(platform_def.get("section", "breach")).strip()

    if category not in _EMAIL_CATEGORIES:
        issues.append(_issue(f"Invalid category: {category or 'missing'}"))
    if section != "breach":
        issues.append(_issue(f"Invalid section: {section or 'missing'}"))
    if not str(platform_def.get("url", "")).strip():
        issues.append(_issue("Missing required field: url"))
    if BREACH_DETECTORS.get(detector) is None:
        issues.append(_issue(f"Unsupported detector type: {detector}"))

    return _offline_result(
        scope="email_breach",
        platform_name=name,
        detector=detector,
        issues=issues,
    )


def _schema_health_username(platform_def: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    raw_name = str(platform_def.get("name", "")).strip()
    name = raw_name or "Unknown"
    detector = str(platform_def.get("check", "html"))
    reliability = str(platform_def.get("reliability", "")).strip()
    error_type = str(platform_def.get("error_type", "")).strip()

    if not raw_name:
        issues.append(_issue("Missing required field: name"))
    if not str(platform_def.get("url", "")).strip():
        issues.append(_issue("Missing required field: url"))
    if reliability not in _USERNAME_RELIABILITY:
        issues.append(_issue(f"Invalid reliability: {reliability or 'missing'}"))
    if error_type not in _USERNAME_ERROR_TYPES:
        issues.append(_issue(f"Invalid error_type: {error_type or 'missing'}"))
    if USERNAME_DETECTORS.get(detector) is None:
        issues.append(_issue(f"Unsupported detector type: {detector}"))
    if detector in {"json", "json_list"} and not str(platform_def.get("probe_url", "")).strip():
        issues.append(_issue("Missing required field: probe_url"))
    if detector == "json" and not str(platform_def.get("json_path", "")).strip():
        issues.append(_issue("Missing required field: json_path"))
    if detector == "json_list":
        if not str(platform_def.get("json_list_path", "")).strip():
            issues.append(_issue("Missing required field: json_list_path"))
        if not str(platform_def.get("json_path", "")).strip():
            issues.append(_issue("Missing required field: json_path"))
    if error_type == "status_code" and "expected_status" not in platform_def:
        issues.append(_issue("Missing required field: expected_status"))
    if error_type == "message" and not str(platform_def.get("error_msg", "")).strip():
        issues.append(_issue("Missing required field: error_msg"))

    return _offline_result(
        scope="username",
        platform_name=name,
        detector=detector,
        issues=issues,
    )


def _eligible_for_live_probe(entry: dict[str, Any], platform_def: dict[str, Any]) -> tuple[bool, str]:
    if entry["offline_state"] == BROKEN:
        return False, "Schema validation failed"

    scope = entry["scope"]
    detector = entry["detector"]
    if scope == "email_account" and detector in {"gravatar", "heuristic", "public_profile_email"}:
        return True, "Safe passive detector supports a live probe"
    if scope == "email_breach" and detector == "hibp":
        if not os.environ.get("HIBP_API_KEY", "").strip():
            return False, "HIBP_API_KEY is not configured"
        return True, "Safe breach API probe is available"
    if scope == "username" and detector in USERNAME_DETECTORS.names():
        return True, "Public profile detector supports a live probe"
    return False, "No safe live probe is defined for this detector"


def _cache_key(entry: dict[str, Any]) -> str:
    return entry["id"]


def _read_live_cache(cache_dir: Path | None = None) -> dict[str, Any]:
    payload = _read_json_file(_cache_file(cache_dir), {})
    return payload if isinstance(payload, dict) else {}


def _write_live_cache(payload: dict[str, Any], cache_dir: Path | None = None) -> None:
    _write_json_file(_cache_file(cache_dir), payload)


def _fresh_cache_item(item: dict[str, Any], ttl_seconds: int) -> bool:
    checked_at = _parse_timestamp(item.get("checked_at", ""))
    if checked_at is None:
        return False
    return checked_at >= _utc_now() - timedelta(seconds=ttl_seconds)


def _cached_live_result(
    entry: dict[str, Any],
    *,
    cache: dict[str, Any],
    ttl_seconds: int,
) -> dict[str, Any] | None:
    item = cache.get(_cache_key(entry))
    if not isinstance(item, dict) or not _fresh_cache_item(item, ttl_seconds):
        return None
    return dict(item)


async def _live_probe_email_account(
    platform_def: dict[str, Any],
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    detector = str(platform_def.get("check", "manual"))
    if detector == "gravatar":
        import hashlib

        digest = hashlib.md5(
            PLACEHOLDER_EMAIL.casefold().encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        response = await client.get(
            f"https://www.gravatar.com/avatar/{digest}",
            params={"d": "404", "s": "1"},
        )
        if response.status_code in {200, 404}:
            return {"state": HEALTHY, "detail": f"HTTP {response.status_code}"}
        if response.status_code == 429:
            return {"state": DEGRADED, "detail": "Rate limited (HTTP 429)"}
        if response.status_code >= 500:
            return {"state": DEGRADED, "detail": f"HTTP {response.status_code}"}
        return {"state": UNKNOWN, "detail": f"Unexpected HTTP {response.status_code}"}

    probe_url = str(platform_def.get("probe_url", "")).format(
        email=quote(PLACEHOLDER_EMAIL, safe="")
    )
    headers = {"User-Agent": f"Trackher/{__version__}"}
    headers.update({str(key): str(value) for key, value in platform_def.get("headers", {}).items()})
    response = await client.get(probe_url, follow_redirects=True, headers=headers)
    if response.status_code == 429:
        return {"state": DEGRADED, "detail": "Rate limited (HTTP 429)"}
    if response.status_code >= 500:
        return {"state": DEGRADED, "detail": f"HTTP {response.status_code}"}
    if response.status_code in {200, 404, 410}:
        if detector == "public_profile_email":
            try:
                payload = response.json()
            except ValueError:
                return {"state": UNKNOWN, "detail": "Live probe returned non-JSON data"}
            if isinstance(payload, (dict, list)):
                return {"state": HEALTHY, "detail": f"HTTP {response.status_code}"}
            return {"state": UNKNOWN, "detail": "Live probe JSON shape was unexpected"}
        return {"state": HEALTHY, "detail": f"HTTP {response.status_code}"}
    return {"state": UNKNOWN, "detail": f"Unexpected HTTP {response.status_code}"}


async def _live_probe_email_breach(
    platform_def: dict[str, Any],
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    api_key = os.environ.get("HIBP_API_KEY", "").strip()
    if not api_key:
        return {"state": UNKNOWN, "detail": "HIBP_API_KEY is not configured"}

    response = await client.get(
        f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(PLACEHOLDER_EMAIL, safe='')}",
        params={"truncateResponse": "true"},
        headers={
            "hibp-api-key": api_key,
            "User-Agent": f"Trackher/{__version__}",
            "Accept": "application/json",
        },
    )
    if response.status_code in {200, 404}:
        return {"state": HEALTHY, "detail": f"HTTP {response.status_code}"}
    if response.status_code == 429:
        return {"state": DEGRADED, "detail": "Rate limited (HTTP 429)"}
    if response.status_code == 401:
        return {"state": DEGRADED, "detail": "HIBP API key rejected"}
    if response.status_code >= 500:
        return {"state": DEGRADED, "detail": f"HTTP {response.status_code}"}
    return {"state": UNKNOWN, "detail": f"Unexpected HTTP {response.status_code}"}


async def _live_probe_username(
    platform_def: dict[str, Any],
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    template = str(platform_def.get("probe_url") or platform_def.get("url", ""))
    probe_url = template.format(quote(PLACEHOLDER_USERNAME, safe="._-~"))
    headers = {"Accept": str(platform_def.get("accept", "text/html,application/json,*/*"))}
    response = await client.get(probe_url, follow_redirects=True, headers=headers)
    if response.status_code == 429:
        return {"state": DEGRADED, "detail": "Rate limited (HTTP 429)"}
    if response.status_code in {403, 503}:
        return {"state": DEGRADED, "detail": f"Service blocked the passive probe (HTTP {response.status_code})"}
    if response.status_code >= 500:
        return {"state": DEGRADED, "detail": f"HTTP {response.status_code}"}
    if response.status_code in {200, 404, 410}:
        return {"state": HEALTHY, "detail": f"HTTP {response.status_code}"}
    return {"state": UNKNOWN, "detail": f"Unexpected HTTP {response.status_code}"}


async def _perform_live_probe(
    entry: dict[str, Any],
    platform_def: dict[str, Any],
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    try:
        if entry["scope"] == "email_account":
            return await _live_probe_email_account(platform_def, client)
        if entry["scope"] == "email_breach":
            return await _live_probe_email_breach(platform_def, client)
        return await _live_probe_username(platform_def, client)
    except httpx.TimeoutException as exc:
        return {"state": DEGRADED, "detail": type(exc).__name__}
    except httpx.HTTPError as exc:
        return {"state": DEGRADED, "detail": type(exc).__name__}
    except Exception as exc:  # pragma: no cover - safety net
        return {"state": UNKNOWN, "detail": type(exc).__name__}


async def _run_live_health(
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    use_cache: bool,
    cache_dir: Path | None,
    ttl_seconds: int,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int]:
    cache_payload = _read_live_cache(cache_dir) if use_cache else {}
    cache_hits = 0
    timeout = httpx.Timeout(10.0, connect=6.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=6)
    headers = {
        "User-Agent": f"Trackher/{__version__}",
        "Accept": "text/html,application/json,*/*",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=headers,
        follow_redirects=True,
        http2=False,
    ) as client:
        updated: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for entry, platform_def in entries:
            live_supported, live_reason = _eligible_for_live_probe(entry, platform_def)
            entry["live_supported"] = live_supported
            if not live_supported:
                entry["live_state"] = UNKNOWN
                entry["live_detail"] = live_reason
                updated.append((entry, platform_def))
                continue

            cached = _cached_live_result(entry, cache=cache_payload, ttl_seconds=ttl_seconds)
            if cached is not None:
                cache_hits += 1
                entry["live_state"] = str(cached.get("state", UNKNOWN))
                entry["live_detail"] = str(cached.get("detail", "Cached live result"))
                entry["live_checked_at"] = str(cached.get("checked_at", ""))
                entry["cache_hit"] = True
                updated.append((entry, platform_def))
                continue

            live_result = await _perform_live_probe(entry, platform_def, client)
            entry["live_state"] = str(live_result.get("state", UNKNOWN))
            entry["live_detail"] = str(live_result.get("detail", "Live probe completed"))
            entry["live_checked_at"] = _iso_now()
            entry["cache_hit"] = False
            cache_payload[_cache_key(entry)] = {
                "state": entry["live_state"],
                "detail": entry["live_detail"],
                "checked_at": entry["live_checked_at"],
            }
            updated.append((entry, platform_def))

    if use_cache:
        _write_live_cache(cache_payload, cache_dir)
    return updated, cache_hits


def _combine_state(entry: dict[str, Any], *, live_enabled: bool) -> None:
    if entry["offline_state"] == BROKEN:
        entry["state"] = BROKEN
        entry["detail"] = "; ".join(entry.get("issues", [])) or "Schema validation failed."
        return

    if live_enabled and entry.get("live_supported"):
        entry["state"] = str(entry.get("live_state", UNKNOWN))
        entry["detail"] = str(entry.get("live_detail", "Live probe completed"))
        return

    entry["state"] = entry["offline_state"]
    if live_enabled and not entry.get("live_supported"):
        entry["detail"] = str(entry.get("live_detail", "No safe live probe is defined for this detector"))
    else:
        entry["detail"] = "Schema and detector configuration look valid."


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in HEALTH_STATES}
    for item in items:
        counts[str(item.get("state", UNKNOWN))] = counts.get(str(item.get("state", UNKNOWN)), 0) + 1
    return counts


def _platform_items() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for platform_def in ACCOUNT_PLATFORMS:
        entries.append((_schema_health_email_account(platform_def), platform_def))
    for platform_def in BREACH_PLATFORMS:
        entries.append((_schema_health_email_breach(platform_def), platform_def))
    for platform_def in USERNAME_PLATFORMS:
        entries.append((_schema_health_username(platform_def), platform_def))
    return entries


def run_platform_health_check(
    *,
    live: bool = False,
    use_cache: bool = True,
    cache_dir: Path | None = None,
    ttl_seconds: int = CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    """Run schema-only or optional live platform health checks."""

    entries = _platform_items()
    cache_hits = 0
    if live:
        entries, cache_hits = asyncio.run(
            _run_live_health(
                entries,
                use_cache=use_cache,
                cache_dir=cache_dir,
                ttl_seconds=ttl_seconds,
            )
        )

    items: list[dict[str, Any]] = []
    for entry, _platform_def in entries:
        _combine_state(entry, live_enabled=live)
        items.append(entry)

    items.sort(key=lambda item: (HEALTH_STATES.index(str(item["state"])), item["scope"], item["platform"]))
    counts = _counts(items)
    payload = {
        "available": True,
        "live_enabled": live,
        "checked_at": _iso_now(),
        "cache_enabled": use_cache,
        "cache_hits": cache_hits,
        "cache_path": str(_cache_file(cache_dir)),
        "summary": _summary_line(counts),
        "counts": counts,
        "items": items,
    }
    _write_json_file(_summary_file(cache_dir), payload)
    return payload
    if not raw_name:
        issues.append(_issue("Missing required field: name"))
