"""Safe email OSINT checks and email service catalog loading."""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from osint.detector_runtime import (
    DetectorRegistry,
    normalize_breach_result,
    normalize_email_result,
    safe_execute,
)
from utils import __version__

EMAIL_PLATFORMS_PATH = Path(__file__).with_name("email_platforms.json")

FOUND = "FOUND"
NOT_FOUND = "NOT_FOUND"
POSSIBLE = "POSSIBLE"
UNKNOWN = "UNKNOWN"
MANUAL = "MANUAL"
ERROR = "ERROR"
NOT_CONFIGURED = "NOT_CONFIGURED"


def _base_result(platform: dict[str, Any], status: str, detail: str = "") -> dict[str, Any]:
    return normalize_email_result(platform, status, detail)


def _email_hash(text: str) -> str:
    payload = text.strip().casefold().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_json(response: httpx.Response) -> dict | list | None:
    try:
        return response.json()
    except ValueError:
        return None


def _json_value(data: object, path: str) -> object | None:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _format_profile_url(template: str, item: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        field_name = match.group(1)
        value = _json_value(item, field_name)
        if value is None:
            raise KeyError(field_name)
        return quote(str(value), safe=":/?&=%")

    return re.sub(r"\{([^{}]+)\}", replace, template)


def _extract_metadata(data: object, fields: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(fields, dict):
        return {}

    metadata: dict[str, str] = {}
    for key, path in fields.items():
        value = _json_value(data, str(path))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            metadata[str(key)] = text
    return metadata


def _format_email_template(value: object, email: str) -> str:
    raw_email = email.strip()
    return str(value).format(
        email=raw_email,
        email_quoted=quote(raw_email, safe=""),
    )


def _xml_value(element: ET.Element | None, path: str) -> object | None:
    if element is None:
        return None

    current = element
    parts = [part for part in str(path).split(".") if part]
    if parts and parts[0] == current.tag:
        parts = parts[1:]

    for part in parts:
        if part.startswith("@"):
            return current.attrib.get(part[1:])
        child = current.find(part)
        if child is None:
            return None
        current = child
    return (current.text or "").strip()


def _extract_xml_metadata(element: ET.Element, fields: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(fields, dict):
        return {}

    metadata: dict[str, str] = {}
    for key, path in fields.items():
        value = _xml_value(element, str(path))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            metadata[str(key)] = text
    return metadata


def _load_email_platforms() -> list[dict[str, Any]]:
    with open(EMAIL_PLATFORMS_PATH, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, list):
        raise ValueError("email_platforms.json root must be a list")
    return data


EMAIL_PLATFORMS = _load_email_platforms()
ACCOUNT_PLATFORMS = [item for item in EMAIL_PLATFORMS if item.get("section", "account") == "account"]
BREACH_PLATFORMS = [item for item in EMAIL_PLATFORMS if item.get("section") == "breach"]
ALL_SERVICES = [(item["name"], item) for item in EMAIL_PLATFORMS]
AUTOMATIC_ACCOUNT_PLATFORMS = [
    (item["name"], item) for item in ACCOUNT_PLATFORMS if item.get("check", "manual") != "manual"
]
PASSIVE_SERVICES = [(item["name"], item) for item in ACCOUNT_PLATFORMS if item.get("category") == "verified"]


async def check_gravatar(email: str, client: httpx.AsyncClient, platform: dict[str, Any] | None = None) -> dict[str, Any]:
    platform = platform or {"name": "Gravatar", "category": "verified"}
    digest = _email_hash(email)
    try:
        response = await client.get(
            f"https://www.gravatar.com/avatar/{digest}",
            params={"d": "404", "s": "1"},
        )
    except httpx.TimeoutException as exc:
        result = _base_result(platform, ERROR, type(exc).__name__)
        result["found"] = False
        return result
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__)

    if response.status_code == 200:
        result = _base_result(platform, FOUND, f"https://gravatar.com/{digest}")
        result["public_metadata"] = {
            "avatar_hash": digest,
            "hash_algorithm": "sha256",
            "profile_url": f"https://gravatar.com/{digest}",
        }
        return result
    if response.status_code == 404:
        return _base_result(platform, NOT_FOUND)
    return _base_result(platform, UNKNOWN, f"HTTP {response.status_code}")


async def check_heuristic(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    """Run a side-effect-free heuristic probe; positive evidence is only POSSIBLE."""
    probe_url = str(platform.get("probe_url", "")).format(email=quote(email.strip(), safe=""))
    if not probe_url:
        return _base_result(platform, MANUAL, "No automatic heuristic probe configured")

    try:
        response = await client.get(probe_url, follow_redirects=True)
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__)
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__)

    if response.status_code in set(platform.get("not_found_statuses", [404, 410])):
        return _base_result(platform, NOT_FOUND, f"HTTP {response.status_code}")
    if response.status_code != 200:
        return _base_result(platform, UNKNOWN, f"HTTP {response.status_code}")

    body = response.text.casefold()
    possible_markers = [str(item).casefold() for item in platform.get("possible_markers", [])]
    not_found_markers = [str(item).casefold() for item in platform.get("not_found_markers", [])]
    if any(marker in body for marker in not_found_markers):
        return _base_result(platform, NOT_FOUND, "Not-found marker observed")
    if any(marker in body for marker in possible_markers):
        return _base_result(platform, POSSIBLE, "Heuristic marker observed")
    return _base_result(platform, UNKNOWN, "Heuristic probe inconclusive")


async def check_public_profile_email(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    """Probe public profile APIs that expose email only when users make it public."""
    probe_url = str(platform.get("probe_url", "")).format(email=quote(email.strip(), safe=""))
    if not probe_url:
        return _base_result(platform, MANUAL, "No public profile probe configured")

    headers = {"User-Agent": f"Trackher/{__version__}", "Accept": "application/json"}
    headers.update({str(key): str(value) for key, value in platform.get("headers", {}).items()})

    try:
        response = await client.get(probe_url, follow_redirects=True, headers=headers)
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__)
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__)

    if response.status_code != 200:
        return _base_result(platform, UNKNOWN, f"HTTP {response.status_code}")

    data = _safe_json(response)
    if data is None:
        return _base_result(platform, UNKNOWN, "Search response was not valid JSON")

    items_path = str(platform.get("items_path", "items"))
    items = _json_value(data, items_path) if items_path else data
    if not isinstance(items, list):
        return _base_result(platform, UNKNOWN, "Search response shape was unexpected")

    normalized_email = email.strip().casefold()
    profile_url_field = str(platform.get("profile_url_field", "url"))
    profile_url_template = str(platform.get("profile_url_template", ""))
    profile_email_field = str(platform.get("profile_email_field", "email"))
    label_field = str(platform.get("label_field", "login"))
    inspected_profiles = 0

    for item in items[: int(platform.get("profile_check_limit", 5))]:
        if not isinstance(item, dict):
            continue
        profile_url = _json_value(item, profile_url_field)
        if profile_url_template:
            try:
                profile_url = _format_profile_url(profile_url_template, item)
            except KeyError:
                continue
        if not isinstance(profile_url, str) or not profile_url:
            continue

        try:
            profile_response = await client.get(profile_url, follow_redirects=True, headers=headers)
        except httpx.TimeoutException as exc:
            return _base_result(platform, ERROR, type(exc).__name__)
        except httpx.HTTPError as exc:
            return _base_result(platform, ERROR, type(exc).__name__)

        if profile_response.status_code != 200:
            continue
        inspected_profiles += 1

        profile_data = _safe_json(profile_response)
        if profile_data is None:
            continue
        public_email = _json_value(profile_data, profile_email_field)
        if isinstance(public_email, str) and public_email.strip().casefold() == normalized_email:
            label = _json_value(item, label_field)
            status = FOUND if platform.get("category") == "verified" else POSSIBLE
            detail = "Public profile email matched exactly"
            if isinstance(label, str) and label.strip():
                detail = f"Public profile email matched exactly ({label.strip()})"
            result = _base_result(platform, status, detail)
            metadata = _extract_metadata(profile_data, platform.get("profile_metadata_fields"))
            if isinstance(label, str) and label.strip():
                metadata.setdefault("username", label.strip())
            if metadata:
                result["public_metadata"] = metadata
            return result

    if inspected_profiles:
        return _base_result(platform, UNKNOWN, "No exact public-email match; private accounts remain undetectable")
    return _base_result(platform, UNKNOWN, "Search results were inconclusive")


async def check_documented_email_lookup(
    email: str,
    client: httpx.AsyncClient,
    platform: dict[str, Any],
) -> dict[str, Any]:
    """Run a documented, read-only email lookup API."""
    probe_url = str(platform.get("probe_url", "")).strip()
    if not probe_url:
        return _base_result(platform, MANUAL, "No documented lookup probe configured")

    params = {
        str(key): _format_email_template(value, email)
        for key, value in dict(platform.get("probe_params", {})).items()
    }
    headers = {"User-Agent": f"Trackher/{__version__}"}
    headers.update({str(key): str(value) for key, value in platform.get("headers", {}).items()})

    api_key_env = str(platform.get("api_key_env", "")).strip()
    if api_key_env:
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            return _base_result(platform, NOT_CONFIGURED, f"{api_key_env} not configured")
        api_key_param = str(platform.get("api_key_param", "api_key")).strip() or "api_key"
        params[api_key_param] = api_key

    try:
        response = await client.get(probe_url, params=params, follow_redirects=True, headers=headers)
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__)
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__)

    if response.status_code != 200:
        return _base_result(platform, UNKNOWN, f"HTTP {response.status_code}")

    response_format = str(platform.get("response_format", "xml")).strip().casefold()
    if response_format != "xml":
        return _base_result(platform, UNKNOWN, "Unsupported documented lookup response format")

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return _base_result(platform, UNKNOWN, "Lookup response was not valid XML")

    error_node = root.find(".//err")
    if error_node is not None:
        error_code = str(error_node.attrib.get("code", "")).strip()
        error_message = str(error_node.attrib.get("msg", "")).strip() or "Lookup failed"
        not_found_codes = {str(code) for code in platform.get("not_found_error_codes", [])}
        invalid_key_codes = {str(code) for code in platform.get("invalid_key_error_codes", [])}
        if error_code in not_found_codes:
            return _base_result(platform, NOT_FOUND, error_message)
        if error_code in invalid_key_codes:
            return _base_result(platform, ERROR, error_message)
        return _base_result(platform, UNKNOWN, error_message)

    success_path = str(platform.get("success_path", "")).strip()
    success_value = _xml_value(root, success_path) if success_path else None
    if success_path and success_value is None:
        return _base_result(platform, UNKNOWN, "Lookup response shape was unexpected")

    status = FOUND if platform.get("category") == "verified" else POSSIBLE
    detail = str(platform.get("success_detail", "Documented public lookup matched exactly")).strip()
    label_path = str(platform.get("label_path", "")).strip()
    if label_path:
        label = _xml_value(root, label_path)
        if isinstance(label, str) and label.strip():
            detail = f"{detail} ({label.strip()})"

    result = _base_result(platform, status, detail)
    metadata = _extract_xml_metadata(root, platform.get("profile_metadata_fields"))
    if metadata:
        result["public_metadata"] = metadata
    return result


async def check_manual(_email: str, _client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    return _base_result(platform, MANUAL, "Manual investigation required")


async def check_haveibeenpwned(email: str, client: httpx.AsyncClient, platform: dict[str, Any] | None = None) -> dict[str, Any]:
    platform = platform or {"name": "Have I Been Pwned", "category": "verified", "section": "breach"}
    api_key = os.environ.get("HIBP_API_KEY", "").strip()
    if not api_key:
        return {
            **normalize_breach_result(
                platform,
                NOT_CONFIGURED,
                "HIBP_API_KEY not configured",
            ),
        }
    if re.fullmatch(r"[0-9a-fA-F]{32}", api_key) is None:
        return {
            **normalize_breach_result(
                platform,
                ERROR,
                "HIBP_API_KEY format is invalid",
            ),
        }

    encoded_email = quote(email.strip(), safe="")
    try:
        response = await client.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{encoded_email}",
            params={"truncateResponse": "true"},
            headers={
                "hibp-api-key": api_key,
                "User-Agent": f"Trackher/{__version__}",
                "Accept": "application/json",
            },
        )
    except httpx.TimeoutException as exc:
        status = ERROR
        detail = type(exc).__name__
        breaches: list[str] = []
    except httpx.HTTPError as exc:
        status = ERROR
        detail = type(exc).__name__
        breaches = []
    else:
        if response.status_code == 404:
            status = NOT_FOUND
            detail = "No known breaches"
            breaches = []
        elif response.status_code == 401:
            status = ERROR
            detail = "HIBP API key rejected"
            breaches = []
        elif response.status_code == 429:
            status = ERROR
            detail = "HIBP rate limit exceeded"
            breaches = []
        elif response.status_code != 200:
            status = UNKNOWN
            detail = f"HTTP {response.status_code}"
            breaches = []
        else:
            data = _safe_json(response)
            if not isinstance(data, list):
                status = UNKNOWN
                detail = "Unexpected HIBP response"
                breaches = []
            else:
                breaches = [str(item.get("Name", "")) for item in data if isinstance(item, dict)]
                breaches = [name for name in breaches if name]
                status = FOUND if breaches else NOT_FOUND
                detail = f"{len(breaches)} breaches" if breaches else "No known breaches"

    return normalize_breach_result(
        platform,
        status,
        detail,
        extra={"breaches": breaches},
    )


ACCOUNT_DETECTORS = DetectorRegistry()
ACCOUNT_DETECTORS.register("documented_email_lookup", check_documented_email_lookup)
ACCOUNT_DETECTORS.register("gravatar", check_gravatar)
ACCOUNT_DETECTORS.register("heuristic", check_heuristic)
ACCOUNT_DETECTORS.register("public_profile_email", check_public_profile_email)
ACCOUNT_DETECTORS.register("manual", check_manual)

BREACH_DETECTORS = DetectorRegistry()
BREACH_DETECTORS.register("hibp", check_haveibeenpwned)

# Backward-compatible aliases for existing callers/tests.
CHECKS = ACCOUNT_DETECTORS
BREACH_CHECKS = BREACH_DETECTORS


async def check_account_platform(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    check_name = str(platform.get("check", "manual"))
    check_fn = ACCOUNT_DETECTORS.get(check_name) or ACCOUNT_DETECTORS.get("manual")
    assert check_fn is not None
    result = await safe_execute(
        lambda: check_fn(email, client, platform),
        on_error=lambda exc: normalize_email_result(
            platform,
            ERROR,
            type(exc).__name__,
        ),
    )
    if platform.get("category") != "verified" and result.get("status") == FOUND:
        result["status"] = POSSIBLE
        result["found"] = False
        result["detail"] = result.get("detail") or "Non-verified detector cannot return FOUND"
    return result


async def check_breach_platform(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    check_name = str(platform.get("check", "hibp"))
    check_fn = BREACH_DETECTORS.get(check_name) or BREACH_DETECTORS.get("hibp")
    assert check_fn is not None
    return await safe_execute(
        lambda: check_fn(email, client, platform),
        on_error=lambda exc: normalize_breach_result(
            platform,
            ERROR,
            type(exc).__name__,
        ),
    )
