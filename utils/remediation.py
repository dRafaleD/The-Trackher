"""Build safe remediation / privacy actions from catalog metadata."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any
from urllib.parse import urlparse


_ALLOWED_SCHEMES = {"http", "https"}


def _normalize_name(value: object) -> str:
    return str(value).strip().casefold()


def _valid_url(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        return ""
    return text


def _catalog_index(items: Iterable[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _normalize_name(item.get(field, ""))
        if key:
            indexed[key] = item
    return indexed


def _resolve_action_url(action: dict[str, Any], context: dict[str, Any]) -> str:
    if "url_field" in action:
        url_value = context.get(str(action.get("url_field", "")), "")
    elif "url_template" in action:
        try:
            url_value = str(action["url_template"]).format_map(context)
        except (KeyError, ValueError):
            return ""
    else:
        url_value = action.get("url", "")
    return _valid_url(url_value)


def _normalize_action(action: dict[str, Any], context: dict[str, Any]) -> dict[str, str] | None:
    url = _resolve_action_url(action, context)
    if not url:
        return None

    label = str(action.get("label") or action.get("type") or "Action").strip()
    action_type = str(action.get("type") or label).strip()
    if not label:
        return None

    return {
        "type": action_type,
        "label": label,
        "url": url,
    }


def _actions_from_catalog(entry: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    actions = entry.get("actions", [])
    if not isinstance(actions, list):
        return []

    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        item = _normalize_action(action, context)
        if not item:
            continue
        signature = (item["type"], item["label"], item["url"])
        if signature in seen:
            continue
        seen.add(signature)
        normalized.append(item)
    return normalized


def _remediation_context(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    context = dict(item)
    context["source"] = source
    context.setdefault("platform", item.get("platform", item.get("service", "")))
    context.setdefault("service", item.get("service", item.get("platform", "")))
    context.setdefault("status", str(item.get("status", "")).upper())
    context.setdefault("found_url", item.get("url", ""))
    return context


def _collect_username_actions(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    from osint.username_checker import USERNAME_PLATFORMS

    platform_map = _catalog_index(USERNAME_PLATFORMS, "name")
    username_data = report_data.get("osint_username")
    if not isinstance(username_data, dict):
        return []

    results = username_data.get("results", [])
    if not isinstance(results, list):
        return []

    items: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", "")).strip().casefold()
        if status not in {"found", "possible"}:
            continue

        platform_name = str(result.get("platform", "")).strip()
        catalog_entry = platform_map.get(_normalize_name(platform_name))
        if not catalog_entry:
            continue

        actions = _actions_from_catalog(
            catalog_entry,
            _remediation_context(result, source="username"),
        )
        if not actions:
            continue

        items.append(
            {
                "source": "username",
                "platform": platform_name,
                "status": str(result.get("status", "FOUND")).upper(),
                "actions": actions,
            }
        )
    return items


def _collect_email_actions(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    from osint.services import EMAIL_PLATFORMS

    platform_map = _catalog_index(EMAIL_PLATFORMS, "name")
    email_data = report_data.get("osint_email")
    if not isinstance(email_data, dict):
        return []

    results = email_data.get("results", {})
    if not isinstance(results, dict):
        return []

    items: list[dict[str, Any]] = []

    accounts = results.get("accounts", [])
    if isinstance(accounts, list):
        for result in accounts:
            if not isinstance(result, dict):
                continue
            status = str(result.get("status", "")).strip().upper()
            if status not in {"FOUND", "POSSIBLE"}:
                continue

            service_name = str(result.get("service", "")).strip()
            catalog_entry = platform_map.get(_normalize_name(service_name))
            if not catalog_entry:
                continue

            actions = _actions_from_catalog(
                catalog_entry,
                _remediation_context(result, source="email"),
            )
            if not actions:
                continue

            items.append(
                {
                    "source": "email",
                    "platform": service_name,
                    "status": status,
                    "actions": actions,
                }
            )

    breaches = results.get("breaches", [])
    if isinstance(breaches, list):
        for result in breaches:
            if not isinstance(result, dict):
                continue
            if str(result.get("status", "")).strip().upper() != "FOUND":
                continue

            provider_name = str(result.get("service", "")).strip()
            catalog_entry = platform_map.get(_normalize_name(provider_name))
            if not catalog_entry:
                continue

            actions = _actions_from_catalog(
                catalog_entry,
                _remediation_context(result, source="breach"),
            )
            if not actions:
                continue

            items.append(
                {
                    "source": "breach",
                    "platform": provider_name,
                    "status": "FOUND",
                    "actions": actions,
                }
            )

    return items


def build_remediation_report(report_data: dict[str, Any]) -> dict[str, Any]:
    """Build a safe remediation payload from scan evidence and catalog metadata."""

    items = _collect_username_actions(report_data) + _collect_email_actions(report_data)
    action_count = sum(len(item.get("actions", [])) for item in items)
    return {
        "available": bool(items),
        "item_count": len(items),
        "action_count": action_count,
        "items": items,
    }


def html_escape(value: object) -> str:
    """Expose HTML escaping for report rendering helpers."""

    return escape(str(value), quote=True)
