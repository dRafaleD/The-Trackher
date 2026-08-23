"""Safe email OSINT checks and email service catalog loading."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit

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
NO_PUBLIC_EVIDENCE = "NO_PUBLIC_EVIDENCE"


def _base_result(
    platform: dict[str, Any],
    status: str,
    detail: str = "",
    cause: str | None = None,
) -> dict[str, Any]:
    if cause == "rate_limited":
        detail = "Site paused; skipped because of rate limiting."
    result = normalize_email_result(platform, status, detail)
    if cause:
        result["diagnostic_cause"] = cause
        if status in {UNKNOWN, ERROR, NOT_CONFIGURED}:
            result["unknown_cause"] = cause
    return result


def _http_unknown_cause(status_code: int) -> str:
    if status_code == 429:
        return "rate_limited"
    if status_code in {401, 403}:
        return "forbidden"
    if status_code >= 500:
        return "server_error"
    return "unexpected_status"


def _error_cause(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "network_error"
    return "detector_error"


def _email_evidence(detector: str, result: dict[str, Any]) -> dict[str, str]:
    evidence = {
        "detector": detector,
        "status": str(result.get("status", UNKNOWN)),
        "detail": str(result.get("detail", "")),
    }
    cause = result.get("unknown_cause") or result.get("diagnostic_cause")
    if cause:
        evidence["cause"] = str(cause)
    return evidence


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
        result = _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
        result["found"] = False
        return result
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

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
    return _base_result(
        platform,
        UNKNOWN,
        f"HTTP {response.status_code}",
        _http_unknown_cause(response.status_code),
    )


async def check_heuristic(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    """Run a side-effect-free heuristic probe; positive evidence is only POSSIBLE."""
    probe_url = str(platform.get("probe_url", "")).format(email=quote(email.strip(), safe=""))
    if not probe_url:
        return _base_result(platform, MANUAL, "No automatic heuristic probe configured")

    try:
        response = await client.get(probe_url, follow_redirects=True)
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

    if response.status_code in set(platform.get("not_found_statuses", [404, 410])):
        return _base_result(platform, NOT_FOUND, f"HTTP {response.status_code}")
    if response.status_code != 200:
        return _base_result(
            platform,
            UNKNOWN,
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code),
        )

    body = response.text.casefold()
    possible_markers = [str(item).casefold() for item in platform.get("possible_markers", [])]
    not_found_markers = [str(item).casefold() for item in platform.get("not_found_markers", [])]
    if any(marker in body for marker in not_found_markers):
        return _base_result(platform, NOT_FOUND, "Not-found marker observed")
    if any(marker in body for marker in possible_markers):
        return _base_result(platform, POSSIBLE, "Heuristic marker observed")
    return _base_result(platform, UNKNOWN, "Heuristic probe inconclusive", "no_decisive_marker")


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
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

    if response.status_code != 200:
        return _base_result(
            platform,
            UNKNOWN,
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code),
        )

    data = _safe_json(response)
    if data is None:
        return _base_result(platform, UNKNOWN, "Search response was not valid JSON", "parser_mismatch")

    items_path = str(platform.get("items_path", "items"))
    items = _json_value(data, items_path) if items_path else data
    if not isinstance(items, list):
        return _base_result(platform, UNKNOWN, "Search response shape was unexpected", "parser_mismatch")

    normalized_email = email.strip().casefold()
    profile_url_field = str(platform.get("profile_url_field", "url"))
    profile_url_template = str(platform.get("profile_url_template", ""))
    profile_email_field = str(platform.get("profile_email_field", "email"))
    label_field = str(platform.get("label_field", "login"))
    inspected_profiles = 0
    attempted_profiles = 0
    profile_failure_causes: list[str] = []
    profile_configuration_failed = False

    for item in items[: int(platform.get("profile_check_limit", 5))]:
        if not isinstance(item, dict):
            continue
        profile_url = _json_value(item, profile_url_field)
        if profile_url_template:
            try:
                profile_url = _format_profile_url(profile_url_template, item)
            except KeyError:
                profile_configuration_failed = True
                continue
        if not isinstance(profile_url, str) or not profile_url:
            continue

        attempted_profiles += 1
        try:
            profile_response = await client.get(profile_url, follow_redirects=True, headers=headers)
        except httpx.TimeoutException as exc:
            return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
        except httpx.HTTPError as exc:
            return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

        if profile_response.status_code != 200:
            profile_failure_causes.append(_http_unknown_cause(profile_response.status_code))
            continue
        profile_data = _safe_json(profile_response)
        if profile_data is None:
            profile_failure_causes.append("parser_mismatch")
            continue
        inspected_profiles += 1
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
        return _base_result(
            platform,
            NO_PUBLIC_EVIDENCE,
            "No exact public-email match; a private account may still exist",
        )
    if attempted_profiles:
        cause = profile_failure_causes[0] if profile_failure_causes else "parser_mismatch"
        return _base_result(
            platform,
            UNKNOWN,
            "Public profile candidates were found but could not be verified",
            cause,
        )
    if profile_configuration_failed:
        return _base_result(
            platform,
            UNKNOWN,
            "Public profile URL configuration could not be resolved",
            "parser_mismatch",
        )
    return _base_result(
        platform,
        NO_PUBLIC_EVIDENCE,
        "No publicly indexed profile exposed this email; a private account may still exist",
    )


async def check_github_commit_email(
    email: str,
    client: httpx.AsyncClient,
    platform: dict[str, Any],
) -> dict[str, Any]:
    """Search GitHub's public commit index for an exact author-email match."""
    headers = {
        "User-Agent": f"Trackher/{__version__}",
        "Accept": "application/vnd.github+json",
    }
    try:
        response = await client.get(
            "https://api.github.com/search/commits",
            params={"q": f"author-email:{email.strip()}", "per_page": "1"},
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

    if response.status_code != 200:
        return _base_result(
            platform,
            UNKNOWN,
            f"GitHub commit search HTTP {response.status_code}",
            _http_unknown_cause(response.status_code),
        )
    data = _safe_json(response)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return _base_result(platform, UNKNOWN, "GitHub commit search shape was unexpected", "parser_mismatch")
    if not data["items"]:
        return _base_result(
            platform,
            NO_PUBLIC_EVIDENCE,
            "No exact public commit-author email match",
        )

    item = data["items"][0]
    public_email = _json_value(item, "commit.author.email")
    if not isinstance(public_email, str) or public_email.strip().casefold() != email.strip().casefold():
        return _base_result(platform, UNKNOWN, "Commit search did not return an exact email", "parser_mismatch")

    result = _base_result(platform, POSSIBLE, "Exact email found in GitHub public commit metadata")
    metadata = _extract_metadata(
        item,
        {
            "username": "author.login",
            "profile_url": "author.html_url",
            "commit_url": "html_url",
            "commit_sha": "sha",
        },
    )
    metadata["public_email"] = public_email.strip()
    result["public_metadata"] = metadata
    return result


async def check_public_text_email(
    email: str,
    client: httpx.AsyncClient,
    platform: dict[str, Any],
) -> dict[str, Any]:
    """Check a documented exact-email endpoint that returns public text evidence."""
    probe_url = _format_email_template(platform.get("probe_url", ""), email)
    if not probe_url:
        return _base_result(platform, MANUAL, "No public text endpoint configured")
    try:
        response = await client.get(probe_url, follow_redirects=True)
    except httpx.TimeoutException as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

    if response.status_code in set(platform.get("not_found_statuses", [404, 410])):
        return _base_result(platform, NO_PUBLIC_EVIDENCE, f"HTTP {response.status_code}; no opt-in public record")
    if response.status_code != 200:
        return _base_result(
            platform,
            UNKNOWN,
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code),
        )
    marker = str(platform.get("found_marker", "")).strip()
    if marker and marker not in response.text:
        return _base_result(platform, UNKNOWN, "Public record marker was missing", "parser_mismatch")
    status = FOUND if platform.get("category") == "verified" else POSSIBLE
    result = _base_result(platform, status, "Exact opt-in public email record found")
    result["public_metadata"] = {"public_email": email.strip(), "record_url": str(response.url)}
    return result


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
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))
    except httpx.HTTPError as exc:
        return _base_result(platform, ERROR, type(exc).__name__, _error_cause(exc))

    if response.status_code != 200:
        return _base_result(
            platform,
            UNKNOWN,
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code),
        )

    response_format = str(platform.get("response_format", "xml")).strip().casefold()
    if response_format != "xml":
        return _base_result(platform, UNKNOWN, "Unsupported documented lookup response format", "parser_mismatch")

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return _base_result(platform, UNKNOWN, "Lookup response was not valid XML", "parser_mismatch")

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
        return _base_result(platform, UNKNOWN, "Lookup response shape was unexpected", "parser_mismatch")

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


async def check_manual(email: str, _client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    """Build a side-effect-free, site-scoped public search lead."""
    result = _base_result(platform, MANUAL, "No safe passive account endpoint; exact public search is available")
    hostname = urlsplit(str(platform.get("url", ""))).hostname or ""
    if hostname:
        query = quote_plus(f'"{email.strip()}" site:{hostname}')
        result["investigation_url"] = f"https://www.google.com/search?q={query}"
        result["investigation_method"] = "exact_public_web_search"
    return result


def _mail_provider(mx_hosts: list[str]) -> str:
    joined = " ".join(mx_hosts).casefold()
    providers = (
        ("Google Workspace", ("google.com", "googlemail.com")),
        ("Microsoft 365", ("mail.protection.outlook.com",)),
        ("Proton Mail", ("protonmail.ch", "protonmail.com")),
        ("Zoho Mail", ("zoho.com", "zoho.eu")),
        ("Fastmail", ("messagingengine.com",)),
    )
    for provider, markers in providers:
        if any(marker in joined for marker in markers):
            return provider
    return ""


async def check_email_domain(email: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Resolve passive MX evidence without claiming that a mailbox exists."""
    domain = email.strip().rsplit("@", 1)[-1].strip().casefold()
    result: dict[str, Any] = {
        "domain": domain,
        "status": UNKNOWN,
        "mail_routable": None,
        "detail": "",
        "mx_hosts": [],
    }
    if not domain or domain == email.strip().casefold():
        result.update(status="INVALID", mail_routable=False, detail="Invalid email domain")
        return result

    try:
        response = await client.get(
            "https://dns.google/resolve",
            params={"name": domain, "type": "MX"},
            headers={"Accept": "application/dns-json"},
        )
    except httpx.TimeoutException:
        result.update(detail="MX lookup timed out", unknown_cause="timeout")
        return result
    except httpx.HTTPError:
        result.update(detail="MX lookup failed", unknown_cause="network_error")
        return result

    if response.status_code != 200:
        result.update(
            detail=f"MX lookup HTTP {response.status_code}",
            unknown_cause=_http_unknown_cause(response.status_code),
        )
        return result

    data = _safe_json(response)
    if not isinstance(data, dict):
        result.update(detail="MX response was not valid JSON", unknown_cause="parser_mismatch")
        return result

    dns_status = data.get("Status")
    if dns_status == 3:
        result.update(
            status="DOMAIN_NOT_FOUND",
            mail_routable=False,
            detail="Email domain does not exist (NXDOMAIN)",
        )
        return result
    if dns_status != 0:
        result.update(detail=f"DNS lookup returned status {dns_status}", unknown_cause="dns_error")
        return result

    mx_hosts: list[str] = []
    null_mx = False
    for answer in data.get("Answer", []):
        if not isinstance(answer, dict) or answer.get("type") != 15:
            continue
        raw_value = str(answer.get("data", "")).strip()
        parts = raw_value.split(maxsplit=1)
        raw_host = parts[1] if len(parts) == 2 else parts[0]
        if raw_host == ".":
            null_mx = True
            continue
        host = raw_host.rstrip(".")
        if host:
            mx_hosts.append(host)

    if null_mx:
        result.update(status="NO_MAIL", mail_routable=False, detail="Domain explicitly rejects email")
        return result
    if not mx_hosts:
        result.update(
            status="NO_MX",
            detail="No explicit MX record; mailbox existence cannot be inferred",
        )
        return result

    provider = _mail_provider(mx_hosts)
    result.update(
        status="MX_FOUND",
        mail_routable=True,
        detail=f"{len(mx_hosts)} MX record(s) found",
        mx_hosts=mx_hosts,
    )
    if provider:
        result["provider"] = provider
    return result


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
        cause = "timeout"
    except httpx.HTTPError as exc:
        status = ERROR
        detail = type(exc).__name__
        breaches = []
        cause = "network_error"
    else:
        cause = ""
        if response.status_code == 404:
            status = NOT_FOUND
            detail = "No known breaches"
            breaches = []
        elif response.status_code == 401:
            status = ERROR
            detail = "HIBP API key rejected"
            breaches = []
            cause = "forbidden"
        elif response.status_code == 429:
            status = ERROR
            detail = "HIBP rate limit exceeded"
            breaches = []
            cause = "rate_limited"
        elif response.status_code != 200:
            status = UNKNOWN
            detail = f"HTTP {response.status_code}"
            breaches = []
            cause = _http_unknown_cause(response.status_code)
        else:
            data = _safe_json(response)
            if not isinstance(data, list):
                status = UNKNOWN
                detail = "Unexpected HIBP response"
                breaches = []
                cause = "parser_mismatch"
            else:
                breaches = [str(item.get("Name", "")) for item in data if isinstance(item, dict)]
                breaches = [name for name in breaches if name]
                status = FOUND if breaches else NOT_FOUND
                detail = f"{len(breaches)} breaches" if breaches else "No known breaches"

    extra: dict[str, Any] = {"breaches": breaches}
    if cause:
        extra["diagnostic_cause"] = cause
        if status in {UNKNOWN, ERROR, NOT_CONFIGURED}:
            extra["unknown_cause"] = cause
    return normalize_breach_result(
        platform,
        status,
        detail,
        extra=extra,
    )


ACCOUNT_DETECTORS = DetectorRegistry()
ACCOUNT_DETECTORS.register("documented_email_lookup", check_documented_email_lookup)
ACCOUNT_DETECTORS.register("github_commit_email", check_github_commit_email)
ACCOUNT_DETECTORS.register("gravatar", check_gravatar)
ACCOUNT_DETECTORS.register("heuristic", check_heuristic)
ACCOUNT_DETECTORS.register("public_text_email", check_public_text_email)
ACCOUNT_DETECTORS.register("public_profile_email", check_public_profile_email)
ACCOUNT_DETECTORS.register("manual", check_manual)

BREACH_DETECTORS = DetectorRegistry()
BREACH_DETECTORS.register("hibp", check_haveibeenpwned)

# Backward-compatible aliases for existing callers/tests.
CHECKS = ACCOUNT_DETECTORS
BREACH_CHECKS = BREACH_DETECTORS


async def check_account_platform(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    primary_check = str(platform.get("check", "manual"))
    raw_chain = platform.get("detector_chain", [primary_check])
    detector_chain = [str(item).strip() for item in raw_chain] if isinstance(raw_chain, list) else [primary_check]
    detector_chain = [item for index, item in enumerate(detector_chain) if item and item not in detector_chain[:index]]
    if primary_check not in detector_chain:
        detector_chain.insert(0, primary_check)
    default_attempts = 1 if primary_check == "manual" else 2
    try:
        attempts = max(1, min(int(platform.get("retry_attempts", default_attempts)), 3))
    except (TypeError, ValueError):
        attempts = default_attempts

    evidence: list[dict[str, str]] = []
    retryable_causes = {"timeout", "network_error", "server_error"}
    result: dict[str, Any] = _base_result(platform, UNKNOWN)
    unresolved_result: dict[str, Any] | None = None
    unresolved_detector = primary_check
    detector_used = primary_check

    for check_name in detector_chain:
        check_fn = ACCOUNT_DETECTORS.get(check_name) or ACCOUNT_DETECTORS.get("manual")
        assert check_fn is not None
        for attempt in range(attempts):
            result = await safe_execute(
                lambda: check_fn(email, client, platform),
                on_error=lambda exc: _base_result(
                    platform,
                    ERROR,
                    type(exc).__name__,
                    _error_cause(exc),
                ),
            )
            if platform.get("category") != "verified" and result.get("status") == FOUND:
                result["status"] = POSSIBLE
                result["found"] = False
                result["detail"] = result.get("detail") or "Non-verified detector cannot return FOUND"
            evidence.append(_email_evidence(check_name, result))
            cause = str(result.get("unknown_cause", ""))
            if cause not in retryable_causes or attempt + 1 == attempts:
                break
            await asyncio.sleep(0.15 * (attempt + 1))

        detector_used = check_name
        status = result.get("status")
        if str(result.get("unknown_cause", "")) == "rate_limited":
            unresolved_result = result
            unresolved_detector = check_name
            break
        if status in {UNKNOWN, ERROR, NOT_CONFIGURED}:
            unresolved_result = result
            unresolved_detector = check_name
            continue
        if status == NO_PUBLIC_EVIDENCE and check_name != detector_chain[-1]:
            continue
        break

    if unresolved_result is not None and result.get("status") == NO_PUBLIC_EVIDENCE:
        result = unresolved_result
        detector_used = unresolved_detector
    result["detector_used"] = detector_used
    result["fallback_used"] = detector_used != primary_check
    result["attempts"] = len(evidence)
    if len(evidence) > 1 or len(detector_chain) > 1:
        result["evidence"] = evidence
    return result


async def check_breach_platform(email: str, client: httpx.AsyncClient, platform: dict[str, Any]) -> dict[str, Any]:
    check_name = str(platform.get("check", "hibp"))
    check_fn = BREACH_DETECTORS.get(check_name) or BREACH_DETECTORS.get("hibp")
    assert check_fn is not None
    try:
        attempts = max(1, min(int(platform.get("retry_attempts", 2)), 3))
    except (TypeError, ValueError):
        attempts = 2

    evidence: list[dict[str, str]] = []
    retryable_causes = {"timeout", "network_error", "server_error"}
    result: dict[str, Any] = normalize_breach_result(platform, UNKNOWN)
    for attempt in range(attempts):
        result = await safe_execute(
            lambda: check_fn(email, client, platform),
            on_error=lambda exc: normalize_breach_result(
                platform,
                ERROR,
                type(exc).__name__,
                extra={"unknown_cause": _error_cause(exc), "diagnostic_cause": _error_cause(exc)},
            ),
        )
        evidence.append(_email_evidence(check_name, result))
        cause = str(result.get("unknown_cause", ""))
        if cause not in retryable_causes or attempt + 1 == attempts:
            break
        await asyncio.sleep(0.15 * (attempt + 1))

    result["detector_used"] = check_name
    result["attempts"] = len(evidence)
    if len(evidence) > 1:
        result["evidence"] = evidence
    return result
