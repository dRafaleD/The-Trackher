"""Yan etkisiz e-posta izi kontrolleri ve servis kataloğu.

E-posta hesabı varlığını sınamak için parola sıfırlama, OTP, sahte kayıt veya
sahte oturum açma isteği gönderilmez. Bu tür bir istek gerektiren servisler
katalogda görünür fakat ağ isteği yapılmadan ``unknown`` sonucu alır.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

from utils import __version__


ServiceCheck = Callable[[str, httpx.AsyncClient], Awaitable[dict[str, Any]]]


def _md5(text: str) -> str:
    """Gravatar protokolünün istediği e-posta özetini üretir."""
    payload = text.strip().casefold().encode("utf-8")
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def _safe_json(response: httpx.Response) -> dict | list | None:
    try:
        return response.json()
    except ValueError:
        return None


def _unknown(service: str, detail: str = "Sonuç doğrulanamadı") -> dict[str, Any]:
    return {
        "service": service,
        "found": False,
        "status": "unknown",
        "detail": detail,
    }


def _found(
    service: str,
    detail: str = "Hesap kayıtlı",
    *,
    verified: bool = False,
) -> dict[str, Any]:
    """Açık kanıt yoksa pozitif sonucu güvenli biçimde belirsiz sayar."""
    if not verified:
        return _unknown(
            service,
            "Platform yanıtı hesap var izlenimi veriyor, ancak doğrulanmış değil",
        )
    return {
        "service": service,
        "found": True,
        "status": "found",
        "detail": detail,
    }


def _not_found(service: str, detail: str = "") -> dict[str, Any]:
    return {
        "service": service,
        "found": False,
        "status": "not_found",
        "detail": detail,
    }


def _skipped(service: str, detail: str) -> dict[str, Any]:
    return {
        "service": service,
        "found": False,
        "status": "skipped",
        "detail": detail,
    }


async def check_gravatar(email: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Gravatar'ın belgelenmiş ``d=404`` davranışıyla avatarı kontrol eder."""
    service = "Gravatar"
    digest = _md5(email)
    try:
        response = await client.get(
            f"https://www.gravatar.com/avatar/{digest}",
            params={"d": "404", "s": "1"},
        )
    except httpx.HTTPError as exc:
        return _unknown(service, type(exc).__name__)

    if response.status_code == 200:
        return _found(
            service,
            f"https://gravatar.com/{digest}",
            verified=True,
        )
    if response.status_code == 404:
        return _not_found(service)
    return _unknown(service, f"HTTP {response.status_code}")


async def check_haveibeenpwned(
    email: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Yalnızca kullanıcı bir HIBP API anahtarı sağladıysa resmî API'yi çağırır."""
    service = "Have I Been Pwned"
    api_key = os.environ.get("HIBP_API_KEY", "").strip()
    if not api_key:
        return _unknown(service, "İsteğe bağlı HIBP_API_KEY tanımlı değil")
    if re.fullmatch(r"[0-9a-fA-F]{32}", api_key) is None:
        return _unknown(service, "HIBP_API_KEY biçimi geçersiz")

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
    except httpx.HTTPError as exc:
        return _unknown(service, type(exc).__name__)

    if response.status_code == 404:
        return _not_found(service, "Bilinen ihlal kaydı yok")
    if response.status_code == 401:
        return _unknown(service, "HIBP API anahtarı geçersiz")
    if response.status_code == 429:
        return _unknown(service, "HIBP hız sınırı aşıldı")
    if response.status_code != 200:
        return _unknown(service, f"HTTP {response.status_code}")

    data = _safe_json(response)
    if not isinstance(data, list):
        return _unknown(service, "Beklenmeyen HIBP yanıtı")

    names = [str(item.get("Name", "")) for item in data if isinstance(item, dict)]
    names = [name for name in names if name]
    if not names:
        return _not_found(service, "Bilinen ihlal kaydı yok")

    preview = ", ".join(names[:3])
    suffix = f" +{len(names) - 3} daha" if len(names) > 3 else ""
    return _found(
        service,
        f"{len(names)} ihlal: {preview}{suffix} (Kaynak: haveibeenpwned.com)",
        verified=True,
    )


def _disabled_check(service: str) -> ServiceCheck:
    async def check(_email: str, _client: httpx.AsyncClient) -> dict[str, Any]:
        return _skipped(
            service,
            "Yan etkili hesap kurtarma/oturum isteği güvenlik için gönderilmedi",
        )

    check.__name__ = f"disabled_{service.casefold().replace(' ', '_')}"
    return check


_SERVICE_CATALOG = [
    "GitHub", "GitLab", "Atlassian / Bitbucket", "Figma", "Notion", "Trello",
    "HubSpot", "Twitter / X", "Instagram", "TikTok", "Snapchat", "Pinterest",
    "LinkedIn", "Reddit", "Tumblr", "Quora", "Spotify", "Netflix", "Twitch",
    "SoundCloud", "Deezer", "Vimeo", "Dailymotion", "Last.fm", "Flickr",
    "Wattpad", "Imgur", "Discord", "Steam", "Epic Games", "Roblox",
    "Chess.com", "Microsoft", "Adobe", "ProtonMail", "Mozilla / Firefox",
    "Yahoo", "Zoom", "Canva", "Amazon", "eBay", "Booking.com", "Dropbox",
    "WordPress", "Evernote", "Gravatar", "Patreon", "Strava", "Duolingo",
    "Have I Been Pwned", "VK", "Badoo", "Tinder", "Medium", "Dev.to",
    "Stack Overflow", "Dribbble", "Etsy", "Airbnb", "Uber", "PayPal",
    "Binance", "Coinbase", "Coursera", "Udemy", "Academia.edu",
    "ResearchGate", "Scribd", "Product Hunt", "Kickstarter", "Fiverr",
    "Upwork", "Freelancer", "DeviantArt", "ArtStation", "500px",
    "Codecademy", "Crunchbase", "Linktree", "Behance", "Trendyol",
    "Hepsiburada", "Sahibinden", "Ekşi Sözlük", "N11", "Sorbil",
    "Yemeksepeti", "Çiçeksepeti", "Getir", "Dolap", "Şikayetvar", "Onedio",
    "Akakçe", "İzlesene", "BiTaksi", "Papara", "iyzico", "Enuygun",
    "Obilet", "Biletix", "Kitapyurdu", "D&R", "Armut", "Modanisa",
    "DeFacto", "LC Waikiki", "Boyner", "Migros Online", "CarrefourSA",
    "PTT AVM",
]

_PASSIVE_BY_NAME: dict[str, ServiceCheck] = {
    "Gravatar": check_gravatar,
    "Have I Been Pwned": check_haveibeenpwned,
}

ALL_SERVICES: list[tuple[str, ServiceCheck]] = [
    (name, _PASSIVE_BY_NAME.get(name) or _disabled_check(name))
    for name in _SERVICE_CATALOG
]

PASSIVE_SERVICE_FUNCTIONS = frozenset(_PASSIVE_BY_NAME.values())
PASSIVE_SERVICES = [
    (name, check_fn)
    for name, check_fn in ALL_SERVICES
    if check_fn in PASSIVE_SERVICE_FUNCTIONS
]
