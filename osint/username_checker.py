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

from utils import __version__
from utils.display import console
from utils.helpers import is_valid_username_query


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
            "profile_id_path",
            "error_msg",
            "expected_status",
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
    body = re.sub(
        r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>",
        " ",
        page,
        flags=re.I | re.S,
    )
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", f"{title} {body}")


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
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_result(result: dict, status: str, detail: str = "") -> dict:
    result["status"] = status
    result["found"] = status == "found"
    result["detail"] = detail
    return result


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
        return _set_result(result, "not_found", f"HTTP {response.status_code}")
    if response.status_code != 200:
        return _set_result(result, "unknown", f"HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        return _set_result(result, "unknown", "Geçersiz JSON yanıtı")

    method = platform.get("check")
    if method == "json_list":
        items = _json_value(data, platform["json_list_path"])
        if not isinstance(items, list):
            return _set_result(result, "unknown", "JSON listesi bulunamadı")

        for item in items:
            value = _json_value(item, platform["json_path"])
            if _normalize_text(value) != _normalize_text(username):
                continue

            profile_id = _json_value(item, platform.get("profile_id_path", "id"))
            if profile_id is not None and platform.get("profile_url"):
                result["url"] = platform["profile_url"].format(profile_id)
            return _set_result(result, "found", "JSON kullanıcı adı eşleşti")

        return _set_result(result, "not_found", "JSON eşleşmesi yok")

    value = _json_value(data, platform["json_path"])
    if _normalize_text(value) == _normalize_text(username):
        return _set_result(result, "found", "JSON kullanıcı adı eşleşti")
    return _set_result(result, "not_found", "JSON eşleşmesi yok")


def _check_html_response(
    username: str,
    platform: dict,
    response: httpx.Response,
    result: dict,
) -> dict:
    not_found_statuses = _expected_statuses(platform, (404, 410))
    if response.status_code in not_found_statuses:
        return _set_result(result, "not_found", f"HTTP {response.status_code}")
    if response.status_code != 200:
        return _set_result(result, "unknown", f"HTTP {response.status_code}")

    visible_text = _visible_page_text(response.text)
    if _contains_block_marker(visible_text):
        return _set_result(result, "unknown", "Site otomatik taramayı engelledi")

    if platform.get("error_type", "message") == "message" and _contains_negative_marker(visible_text):
        return _set_result(result, "not_found", "Bulunamadı işareti görüldü")

    if response.history and not _contains_exact_username(unquote(str(response.url)), username):
        return _set_result(result, "not_found", "Genel sayfaya yönlendirildi")

    if _contains_exact_username(visible_text, username):
        return _set_result(result, "found", "Sayfada kullanıcı adı doğrulandı")

    return _set_result(result, "unknown", "Profil kanıtı bulunamadı")


async def check_single_username(username: str, platform: dict, client: httpx.AsyncClient) -> dict:
    """Bir platformda kullanıcı adını kanıta dayalı olarak doğrular."""
    result = {
        "platform": str(platform.get("name", "Bilinmeyen")),
        "url": "",
        "found": False,
        "status": "unknown",
        "detail": "",
        "reliability": str(platform.get("reliability", "unreliable")),
    }

    try:
        encoded_username = quote(username.strip(), safe="._-~")
        url_template = platform["url"]
        result["url"] = url_template.format(encoded_username)
        probe_url = platform.get("probe_url", url_template).format(encoded_username)
        method = platform.get("check", "html")
        request_headers = (
            {"Accept": platform.get("accept", "application/json")}
            if method in {"json", "json_list"}
            else None
        )
        response = await client.get(
            probe_url,
            follow_redirects=True,
            headers=request_headers,
        )
        if method in {"json", "json_list"}:
            return _check_json_response(username, platform, response, result)
        return _check_html_response(username, platform, response, result)
    except httpx.HTTPError as exc:
        return _set_result(result, "unknown", type(exc).__name__)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return _set_result(result, "unknown", f"Platform yapılandırma hatası: {type(exc).__name__}")


async def check_username_async(username: str) -> list[dict]:
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
            total=len(USERNAME_PLATFORMS),
        )

        async with httpx.AsyncClient(
            headers=headers,
            limits=limits,
            timeout=httpx.Timeout(12.0, connect=8.0),
            follow_redirects=True,
        ) as client:
            tasks = [check_single_username(username, plat, client) for plat in USERNAME_PLATFORMS]

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


def run_username_check(username: str) -> list[dict]:
    return asyncio.run(check_username_async(username))
