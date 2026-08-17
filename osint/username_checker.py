from __future__ import annotations

import asyncio
import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote, unquote

import httpx
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from osint.detector_runtime import (
    DetectorRegistry,
    normalize_username_result,
    safe_execute,
)
from utils import __version__
from utils.display import console
from utils.helpers import is_valid_username_query
from utils.profiles import select_username_platforms


PLATFORMS_PATH = Path(__file__).with_name("platforms.json")
ENTERTAINMENT_FORUM_COUNT = 30


def _normalize_pattern(value: str) -> str:
    return value.replace("{username}", "{}")


def _load_platform_definitions() -> list[dict]:
    with open(PLATFORMS_PATH, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)

    if not isinstance(data, list):
        raise ValueError("platforms.json koku liste olmalidir")

    definitions: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Her platform tanimi JSON nesnesi olmalidir")

        runtime_entry = {
            "name": str(item["name"]),
            "url": _normalize_pattern(str(item["url_pattern"])),
            "error_type": str(item.get("error_type", "message")),
            "reliability": str(item.get("reliability", "unreliable")),
        }

        if "probe_url_pattern" in item:
            runtime_entry["probe_url"] = _normalize_pattern(str(item["probe_url_pattern"]))
        if "profile_url_pattern" in item:
            runtime_entry["profile_url"] = _normalize_pattern(str(item["profile_url_pattern"]))
        for key in (
            "check",
            "accept",
            "json_path",
            "json_list_path",
            "query_body",
            "profile_id_path",
            "error_msg",
            "expected_status",
            "actions",
            "metadata_fields",
            "not_found_markers",
            "not_found_url_contains",
            "raw_found_markers",
            "raw_not_found_markers",
            "allow_title_username_match",
            "disable_html_found",
        ):
            if key in item:
                runtime_entry[key] = item[key]

        definitions.append(runtime_entry)

    return definitions


USERNAME_PLATFORMS = _load_platform_definitions()
_ENTERTAINMENT_FORUM_PLATFORMS = USERNAME_PLATFORMS[-ENTERTAINMENT_FORUM_COUNT:]

_NEGATIVE_KEYWORDS = [
    "page not found",
    "not found",
    "doesn't exist",
    "does not exist",
    "could not be found",
    "page does not exist",
    "member not found",
    "this summoner is not registered",
    "no player found",
    "no user found",
    "no such user",
    "profile not found",
    "this account does not exist",
    "we couldn't find",
    "player not found",
    "user not found",
    "this page is not available",
    "sorry, the page you were looking for",
    "that page doesn't exist",
    "the user could not be found",
    "no results found",
    "oops! that page can",
    "looking for doesn't exist",
    "this summoner doesn't appear",
    "hasn't been played",
    "hmm, this page doesn",
    "unknown user",
    "kayitli degil",
    "bulunamadi",
    "boyle bir kullanici yok",
    "kullanici bulunamadi",
    "uye bulunamadi",
    "sayfa bulunamadi",
    "profil bulunamadi",
    "sayfa mevcut degil",
    "utilisateur introuvable",
    "usuario no encontrado",
    "benutzer nicht gefunden",
    "用户不存在",
    "用户不存在或已被删除",
]

_BLOCKED_KEYWORDS = [
    "just a moment",
    "attention required",
    "access denied",
    "enable javascript and cookies",
    "checking your browser",
    "verify you are human",
    "captcha",
    "client challenge",
    "verify you are a human",
]


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _visible_page_text(page: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
    title = title_match.group(1) if title_match else ""
    return re.sub(r"\s+", " ", f"{title} {_visible_body_text(page)}")


def _visible_body_text(page: str) -> str:
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", page, flags=re.I | re.S)
    body_source = body_match.group(1) if body_match else page
    body = re.sub(
        r"<(head|title|script|style|noscript|svg)\b[^>]*>.*?</\1>",
        " ",
        body_source,
        flags=re.I | re.S,
    )
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body)


def _contains_exact_username(text: str, username: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_username = _normalize_text(username).strip()
    if not normalized_username:
        return False
    pattern = rf"(?<![\w.-]){re.escape(normalized_username)}(?![\w.-])"
    return re.search(pattern, normalized_text) is not None


def _contains_negative_marker(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(keyword) in normalized for keyword in _NEGATIVE_KEYWORDS)


def _contains_block_marker(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(keyword) in normalized for keyword in _BLOCKED_KEYWORDS)


def _json_value(data: object, path: str) -> object | None:
    if path == "":
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def _extract_metadata(data: object, fields: dict[str, object] | None) -> dict[str, str]:
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


def _format_platform_value(value: object, username: str) -> object:
    if isinstance(value, str):
        return value.replace("{username}", username.strip())
    if isinstance(value, list):
        return [_format_platform_value(item, username) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _format_platform_value(item, username)
            for key, item in value.items()
        }
    return value


def _set_result(result: dict, status: str, detail: str = "", cause: str | None = None) -> dict:
    result["status"] = status
    result["found"] = status == "found"
    result["detail"] = detail
    if cause:
        result["diagnostic_cause"] = cause
        if status == "unknown":
            result["unknown_cause"] = cause
    return result


def _http_unknown_cause(status_code: int, text: str = "") -> str:
    if status_code == 429:
        return "rate_limited"
    if status_code == 403:
        return "bot_blocked" if _contains_block_marker(text) else "forbidden"
    if status_code == 503 and _contains_block_marker(text):
        return "bot_blocked"
    return "unexpected_status"


def _exception_cause(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "network_error"
    if isinstance(exc, (KeyError, IndexError, TypeError, ValueError)):
        return "parser_mismatch"
    return "unknown"


def _platform_markers(platform: dict, key: str) -> list[str]:
    raw = platform.get(key, [])
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def _formatted_platform_markers(platform: dict, key: str, username: str) -> list[str]:
    return [
        _normalize_text(str(_format_platform_value(marker, username)))
        for marker in _platform_markers(platform, key)
    ]


def _url_contains_not_found_marker(platform: dict, url: str) -> bool:
    normalized_url = _normalize_text(url)
    return any(
        _normalize_text(marker) in normalized_url
        for marker in _platform_markers(platform, "not_found_url_contains")
    )


def _contains_platform_negative_marker(platform: dict, text: str, username: str) -> bool:
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in _formatted_platform_markers(platform, "not_found_markers", username))


def _contains_platform_raw_marker(platform: dict, key: str, text: str, username: str) -> bool:
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in _formatted_platform_markers(platform, key, username))


def _expected_statuses(platform: dict, default: tuple[int, ...]) -> set[int]:
    raw = platform.get("expected_status", list(default))
    if isinstance(raw, int):
        return {raw}
    if isinstance(raw, list):
        return {int(item) for item in raw}
    return set(default)


def _check_json_response(
    username: str,
    platform: dict,
    response: httpx.Response,
    result: dict,
) -> dict:
    not_found_statuses = _expected_statuses(platform, (404, 410))
    if response.status_code in not_found_statuses:
        return _set_result(result, "not_found", f"HTTP {response.status_code}", "soft_404")
    if response.status_code != 200:
        return _set_result(
            result,
            "unknown",
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code, response.text),
        )

    try:
        data = response.json()
    except ValueError:
        return _set_result(result, "unknown", "Geçersiz JSON yanıtı", "parser_mismatch")

    method = platform.get("check")
    if method == "json_list":
        items = _json_value(data, platform["json_list_path"])
        if not isinstance(items, list):
            return _set_result(result, "unknown", "JSON listesi bulunamadı", "parser_mismatch")

        for item in items:
            value = _json_value(item, platform["json_path"])
            if _normalize_text(value) != _normalize_text(username):
                continue

            profile_id = _json_value(item, platform.get("profile_id_path", "id"))
            if profile_id is not None and platform.get("profile_url"):
                result["url"] = platform["profile_url"].format(profile_id)
            metadata = _extract_metadata(item, platform.get("metadata_fields"))
            metadata.setdefault("username", username.strip())
            if metadata:
                result["public_metadata"] = metadata
            return _set_result(result, "found", "JSON kullanıcı adı eşleşti")

        return _set_result(result, "not_found", "JSON eşleşmesi yok", "soft_404")

    value = _json_value(data, platform["json_path"])
    if _normalize_text(value) == _normalize_text(username):
        metadata = _extract_metadata(data, platform.get("metadata_fields"))
        metadata.setdefault("username", username.strip())
        if metadata:
            result["public_metadata"] = metadata
        return _set_result(result, "found", "JSON kullanıcı adı eşleşti")
    return _set_result(result, "not_found", "JSON eşleşmesi yok", "soft_404")


def _check_html_response(
    username: str,
    platform: dict,
    response: httpx.Response,
    result: dict,
) -> dict:
    not_found_statuses = _expected_statuses(platform, (404, 410))
    if response.status_code in not_found_statuses:
        return _set_result(result, "not_found", f"HTTP {response.status_code}", "soft_404")
    if response.status_code != 200:
        return _set_result(
            result,
            "unknown",
            f"HTTP {response.status_code}",
            _http_unknown_cause(response.status_code, response.text),
        )

    visible_text = _visible_page_text(response.text)
    visible_body = _visible_body_text(response.text)
    raw_text = response.text
    if _contains_block_marker(visible_text):
        return _set_result(result, "unknown", "Site otomatik taramayı engelledi", "bot_blocked")

    if _url_contains_not_found_marker(platform, str(response.url)):
        return _set_result(result, "not_found", "Genel arama sayfasına yönlendirildi", "redirect_changed")

    if _contains_platform_raw_marker(platform, "raw_not_found_markers", raw_text, username):
        return _set_result(result, "not_found", "Bulunamadı işareti görüldü", "soft_404")

    if (
        platform.get("error_type", "message") == "message"
        and (
            _contains_negative_marker(visible_text)
            or _contains_platform_negative_marker(platform, visible_text, username)
        )
    ):
        return _set_result(result, "not_found", "Bulunamadı işareti görüldü", "soft_404")

    if response.history and not _contains_exact_username(unquote(str(response.url)), username):
        return _set_result(result, "not_found", "Genel sayfaya yönlendirildi", "redirect_changed")

    if _contains_platform_raw_marker(platform, "raw_found_markers", raw_text, username):
        return _set_result(result, "found", "Ham yanıt işaretleri kullanıcıyı doğruladı")

    if platform.get("disable_html_found") is True:
        return _set_result(result, "unknown", "Profil kanıtı bulunamadı", "parser_mismatch")

    if _contains_exact_username(visible_body, username) or (
        platform.get("allow_title_username_match") is True and _contains_exact_username(visible_text, username)
    ):
        return _set_result(result, "found", "Sayfada kullanıcı adı doğrulandı")

    return _set_result(result, "unknown", "Profil kanıtı bulunamadı", "parser_mismatch")


async def _run_json_detector(
    username: str,
    platform: dict,
    client: httpx.AsyncClient,
    result: dict,
) -> dict:
    request_headers = {"Accept": platform.get("accept", "application/json")}
    response = await client.get(
        platform["probe_url"].format(quote(username.strip(), safe="._-~")),
        follow_redirects=True,
        headers=request_headers,
    )
    return _check_json_response(username, platform, response, result)


async def _run_graphql_detector(
    username: str,
    platform: dict,
    client: httpx.AsyncClient,
    result: dict,
) -> dict:
    request_headers = {"Accept": platform.get("accept", "application/json")}
    body = _format_platform_value(platform.get("query_body", {}), username)
    response = await client.post(
        platform["probe_url"],
        follow_redirects=True,
        headers=request_headers,
        json=body,
    )
    return _check_json_response(username, platform, response, result)


async def _run_html_detector(
    username: str,
    platform: dict,
    client: httpx.AsyncClient,
    result: dict,
) -> dict:
    response = await client.get(
        platform.get("probe_url", platform["url"]).format(quote(username.strip(), safe="._-~")),
        follow_redirects=True,
    )
    return _check_html_response(username, platform, response, result)


USERNAME_DETECTORS = DetectorRegistry()
USERNAME_DETECTORS.register("html", _run_html_detector)
USERNAME_DETECTORS.register("content", _run_html_detector)
USERNAME_DETECTORS.register("404", _run_html_detector)
USERNAME_DETECTORS.register("json", _run_json_detector)
USERNAME_DETECTORS.register("json_list", _run_json_detector)
USERNAME_DETECTORS.register("graphql", _run_graphql_detector)


async def check_single_username(username: str, platform: dict, client: httpx.AsyncClient) -> dict:
    """Bir platformda kullanıcı adını kanıta dayalı olarak doğrular."""
    result = normalize_username_result(platform)

    try:
        encoded_username = quote(username.strip(), safe="._-~")
        url_template = platform["url"]
        result["url"] = url_template.format(encoded_username)
        method = str(platform.get("check", "html"))
        detector = USERNAME_DETECTORS.get(method)
        if detector is None:
            return _set_result(result, "unknown", f"Desteklenmeyen detector tipi: {method}", "unsupported_detector")
        return await safe_execute(
            lambda: detector(username, platform, client, result),
            on_error=lambda exc: _set_result(result, "unknown", type(exc).__name__, _exception_cause(exc)),
        )
    except httpx.HTTPError as exc:
        return _set_result(result, "unknown", type(exc).__name__, _exception_cause(exc))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return _set_result(
            result,
            "unknown",
            f"Platform yapılandırma hatası: {type(exc).__name__}",
            _exception_cause(exc),
        )


async def check_username_async(
    username: str,
    *,
    profile: str = "standard",
) -> list[dict]:
    """Kullanıcı adını platformlara özel, kanıta dayalı yöntemlerle tarar."""
    username = username.strip()
    if not is_valid_username_query(username):
        return []

    headers = {
        "User-Agent": f"Trackher/{__version__}",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
    }
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    platforms = select_username_platforms(profile, USERNAME_PLATFORMS)
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task(
            f"[cyan]Scanning: {username}...",
            total=len(platforms),
        )

        async with httpx.AsyncClient(
            headers=headers,
            limits=limits,
            timeout=httpx.Timeout(12.0, connect=8.0),
            follow_redirects=True,
        ) as client:
            tasks = [check_single_username(username, plat, client) for plat in platforms]

            for coro in asyncio.as_completed(tasks):
                res = await coro
                results.append(res)
                if res["status"] == "found":
                    status = "[green]FOUND[/green]"
                elif res["status"] == "unknown":
                    status = "[yellow]?[/yellow]"
                else:
                    status = "[dim]---[/dim]"
                progress.update(task_id, advance=1, description=f"{status} {res['platform']}")

    return results


def run_username_check(username: str, *, profile: str = "standard") -> list[dict]:
    return asyncio.run(check_username_async(username, profile=profile))
