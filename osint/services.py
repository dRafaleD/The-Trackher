"""
Dijital Ayak İzi Temizleyici — Platform Servis Kontrolleri

Her servis için asenkron kontrol fonksiyonu tanımlar.
E-posta adresinin ilgili platformda kayıtlı olup olmadığını
HTTP istekleri aracılığıyla tespit eder.

Toplam: 110 platform (80 global + 30 Türk)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx


# ─────────────────────────────────────────────────────────────────
# Yardımcı
# ─────────────────────────────────────────────────────────────────

def _md5(text: str) -> str:
    """Verilen metni MD5 hash'ine çevirir (Gravatar için)."""
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


def _safe_json(response: httpx.Response) -> dict | list | None:
    """Yanıtı JSON olarak ayrıştırmayı dener, başarısız olursa None döndürür."""
    try:
        return response.json()
    except Exception:
        return None


def _err(service: str, detail: str = "Bağlantı hatası") -> dict:
    """Hata durumunda standart döndürme dict'i."""
    return {"service": service, "found": False, "detail": detail}


def _found(service: str, detail: str = "Hesap kayıtlı") -> dict:
    return {"service": service, "found": True, "detail": detail}


def _not_found(service: str, detail: str = "") -> dict:
    return {"service": service, "found": False, "detail": detail}


# ═══════════════════════════════════════════════════════════════════
#  1 — GRAVATAR
# ═══════════════════════════════════════════════════════════════════

async def check_gravatar(email: str, client: httpx.AsyncClient) -> dict:
    s = "Gravatar"
    try:
        h = _md5(email)
        resp = await client.get(f"https://www.gravatar.com/avatar/{h}?d=404&s=1")
        if resp.status_code == 200:
            return _found(s, f"https://gravatar.com/{h}")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  2 — GITHUB
# ═══════════════════════════════════════════════════════════════════

async def check_github(email: str, client: httpx.AsyncClient) -> dict:
    s = "GitHub"
    try:
        resp = await client.get(
            f"https://api.github.com/search/users?q={email}+in:email",
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict) and data.get("total_count", 0) > 0:
            items = data.get("items", [])
            user = items[0]["login"] if items else "—"
            return _found(s, f"Kullanıcı: {user}")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  3 — SPOTIFY
# ═══════════════════════════════════════════════════════════════════

async def check_spotify(email: str, client: httpx.AsyncClient) -> dict:
    s = "Spotify"
    try:
        resp = await client.get(
            f"https://spclient.wg.spotify.com/signup/public/v1/account?validate=1&email={email}"
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict) and data.get("status") == 20:
            return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  4 — PINTEREST
# ═══════════════════════════════════════════════════════════════════

async def check_pinterest(email: str, client: httpx.AsyncClient) -> dict:
    s = "Pinterest"
    try:
        resp = await client.get(
            "https://www.pinterest.com/resource/EmailExistsResource/get/",
            params={
                "source_url": "/",
                "data": json.dumps({"options": {"email": email}}),
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            exists = data.get("resource_response", {}).get("data", False)
            if exists:
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  5 — TWITTER / X
# ═══════════════════════════════════════════════════════════════════

async def check_twitter(email: str, client: httpx.AsyncClient) -> dict:
    s = "Twitter / X"
    try:
        resp = await client.get(
            f"https://api.twitter.com/i/users/email_available.json?email={email}"
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict) and data.get("taken"):
            return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  6 — DUOLINGO
# ═══════════════════════════════════════════════════════════════════

async def check_duolingo(email: str, client: httpx.AsyncClient) -> dict:
    s = "Duolingo"
    try:
        resp = await client.get(
            "https://www.duolingo.com/2017-06-30/users", params={"email": email}
        )
        data = _safe_json(resp)
        if resp.status_code == 200 and data:
            users = data.get("users", [])
            if users:
                uname = users[0].get("username", "—")
                return _found(s, f"Kullanıcı: {uname}")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  7 — ADOBE
# ═══════════════════════════════════════════════════════════════════

async def check_adobe(email: str, client: httpx.AsyncClient) -> dict:
    s = "Adobe"
    try:
        resp = await client.post(
            "https://auth.services.adobe.com/signin/v2/users/accounts",
            json={"username": email},
            headers={"Content-Type": "application/json", "X-IMS-ClientId": "adobedotcom2"},
        )
        data = _safe_json(resp)
        if resp.status_code == 200 and data:
            if isinstance(data, list) and len(data) > 0:
                return _found(s)
            if isinstance(data, dict) and data.get("accounts"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  8 — IMGUR
# ═══════════════════════════════════════════════════════════════════

async def check_imgur(email: str, client: httpx.AsyncClient) -> dict:
    s = "Imgur"
    try:
        resp = await client.get(f"https://imgur.com/signin/ajax_email_check?email={email}")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            avail = data.get("data", {}).get("available", True)
            if not avail:
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  9 — WORDPRESS
# ═══════════════════════════════════════════════════════════════════

async def check_wordpress(email: str, client: httpx.AsyncClient) -> dict:
    s = "WordPress"
    try:
        resp = await client.post(
            "https://wordpress.com/wp-login.php?action=lostpassword",
            data={"user_login": email},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        body = resp.text.lower()
        if "check your email" in body or "e-posta" in body:
            return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  10 — DISCORD
# ═══════════════════════════════════════════════════════════════════

async def check_discord(email: str, client: httpx.AsyncClient) -> dict:
    s = "Discord"
    try:
        resp = await client.post(
            "https://discord.com/api/v9/auth/register",
            json={
                "email": email, "username": "probe_digitalayakizi",
                "password": "ProbeP@ss123!", "consent": True,
                "date_of_birth": "1990-01-01",
            },
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            errs = data.get("errors", {}).get("email", {}).get("_errors", [])
            for e in errs:
                if "already" in e.get("message", "").lower():
                    return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  11 — TUMBLR
# ═══════════════════════════════════════════════════════════════════

async def check_tumblr(email: str, client: httpx.AsyncClient) -> dict:
    s = "Tumblr"
    try:
        resp = await client.post(
            "https://www.tumblr.com/forgotpassword",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict) and data.get("error") is None:
            return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  12 — INSTAGRAM
# ═══════════════════════════════════════════════════════════════════

async def check_instagram(email: str, client: httpx.AsyncClient) -> dict:
    s = "Instagram"
    try:
        resp = await client.post(
            "https://www.instagram.com/accounts/web_create_ajax/attempt/",
            data={"email": email},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.instagram.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("errors", {}).get("email"):
                return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  13 — HAVE I BEEN PWNED
# ═══════════════════════════════════════════════════════════════════

async def check_haveibeenpwned(email: str, client: httpx.AsyncClient) -> dict:
    s = "Have I Been Pwned"
    try:
        resp = await client.get(
            f"https://haveibeenpwned.com/unifiedsearch/{email}",
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            if data and isinstance(data, dict):
                breaches = data.get("Breaches", [])
                c = len(breaches)
                if c > 0:
                    names = ", ".join(b.get("Name", "") for b in breaches[:3])
                    sfx = f" +{c - 3} daha" if c > 3 else ""
                    return _found(s, f"{c} ihlal: {names}{sfx}")
        elif resp.status_code == 401:
            return _not_found(s, "API anahtarı gerekli")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  14 — MICROSOFT (Outlook / Hotmail / Live)
# ═══════════════════════════════════════════════════════════════════

async def check_microsoft(email: str, client: httpx.AsyncClient) -> dict:
    s = "Microsoft"
    try:
        resp = await client.post(
            "https://login.live.com/GetCredentialType.srf",
            json={
                "username": email,
                "uaid": "a]b]c]d]e]f",
                "isOtherIdpSupported": True,
                "checkPhones": False,
                "isRemoteNGCSupported": True,
                "isCookieBannerShown": False,
                "isFidoSupported": False,
                "flowToken": "",
            },
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if_exists = data.get("IfExistsResult", 1)
            # 0 = hesap var, 1 = yok, 5 = farklı sağlayıcı, 6 = var
            if if_exists in (0, 6):
                return _found(s, "Microsoft hesabı bulundu")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  15 — NETFLIX
# ═══════════════════════════════════════════════════════════════════

async def check_netflix(email: str, client: httpx.AsyncClient) -> dict:
    s = "Netflix"
    try:
        resp = await client.post(
            "https://auth.netflix.com/login",
            data={"userLoginId": email, "password": "probe_fake_pw_123"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.netflix.com/login",
            },
        )
        body = resp.text.lower()
        # Yanlış şifre hatası = hesap var
        if "incorrect password" in body or "password" in body and "forgot" in body:
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  16 — AMAZON
# ═══════════════════════════════════════════════════════════════════

async def check_amazon(email: str, client: httpx.AsyncClient) -> dict:
    s = "Amazon"
    try:
        resp = await client.post(
            "https://www.amazon.com/ap/signin",
            data={"email": email, "create": "0", "appActionToken": ""},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.amazon.com/ap/signin",
            },
        )
        body = resp.text.lower()
        if "password" in body and ("enter" in body or "forgot" in body):
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  17 — DROPBOX
# ═══════════════════════════════════════════════════════════════════

async def check_dropbox(email: str, client: httpx.AsyncClient) -> dict:
    s = "Dropbox"
    try:
        resp = await client.post(
            "https://www.dropbox.com/ajax_check_email",
            data={"email": email, "is_checking_existing_email": "true"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.dropbox.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            status = data.get("status", "")
            if status == "error" or data.get("registered"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  18 — GITLAB
# ═══════════════════════════════════════════════════════════════════

async def check_gitlab(email: str, client: httpx.AsyncClient) -> dict:
    s = "GitLab"
    try:
        resp = await client.get(
            f"https://gitlab.com/users/sign_up?user[email]={email}",
            headers={"Accept": "text/html"},
        )
        body = resp.text.lower()
        if "has already been taken" in body or "already been taken" in body:
            return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  19 — REDDIT
# ═══════════════════════════════════════════════════════════════════

async def check_reddit(email: str, client: httpx.AsyncClient) -> dict:
    s = "Reddit"
    try:
        resp = await client.post(
            "https://www.reddit.com/api/check_email.json",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.reddit.com/register/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("json", {}).get("errors"):
                return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  20 — TWITCH
# ═══════════════════════════════════════════════════════════════════

async def check_twitch(email: str, client: httpx.AsyncClient) -> dict:
    s = "Twitch"
    try:
        resp = await client.post(
            "https://passport.twitch.tv/usernames/check",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("userExists") or "already" in str(data).lower():
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  21 — SNAPCHAT
# ═══════════════════════════════════════════════════════════════════

async def check_snapchat(email: str, client: httpx.AsyncClient) -> dict:
    s = "Snapchat"
    try:
        resp = await client.post(
            "https://accounts.snapchat.com/accounts/merlin/check_email",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("email_taken") or data.get("status_code") == "ALREADY_TAKEN":
                return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  22 — TIKTOK
# ═══════════════════════════════════════════════════════════════════

async def check_tiktok(email: str, client: httpx.AsyncClient) -> dict:
    s = "TikTok"
    try:
        resp = await client.get(
            "https://www.tiktok.com/api/user/check_email_registered/",
            params={"email": email},
            headers={"Referer": "https://www.tiktok.com/login/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("data", {}).get("is_registered"):
                return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  23 — LINKEDIN
# ═══════════════════════════════════════════════════════════════════

async def check_linkedin(email: str, client: httpx.AsyncClient) -> dict:
    s = "LinkedIn"
    try:
        resp = await client.get(
            f"https://www.linkedin.com/sales/gmail/profile/viewByEmail/{email}",
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            if data and isinstance(data, dict) and data.get("profile"):
                return _found(s, "Profil bulundu")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  24 — EBAY
# ═══════════════════════════════════════════════════════════════════

async def check_ebay(email: str, client: httpx.AsyncClient) -> dict:
    s = "eBay"
    try:
        resp = await client.post(
            "https://signin.ebay.com/ws/eBayISAPI.dll?SignIn",
            data={"userid": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://signin.ebay.com/",
            },
        )
        body = resp.text.lower()
        if "password" in body and "enter" in body:
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  25 — ROBLOX
# ═══════════════════════════════════════════════════════════════════

async def check_roblox(email: str, client: httpx.AsyncClient) -> dict:
    s = "Roblox"
    try:
        resp = await client.get(
            f"https://auth.roblox.com/v1/usernames/validate?request.email={email}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if "already" in str(data).lower() or data.get("code") == 1:
                return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  26 — EPIC GAMES
# ═══════════════════════════════════════════════════════════════════

async def check_epicgames(email: str, client: httpx.AsyncClient) -> dict:
    s = "Epic Games"
    try:
        resp = await client.get(
            f"https://www.epicgames.com/id/api/account/lookup?email={email}",
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap tespit edildi")
        elif resp.status_code == 404:
            return _not_found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  27 — STEAM
# ═══════════════════════════════════════════════════════════════════

async def check_steam(email: str, client: httpx.AsyncClient) -> dict:
    s = "Steam"
    try:
        resp = await client.post(
            "https://store.steampowered.com/join/ajaxcheckemailverified",
            data={"email": email, "captchagid": -1},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://store.steampowered.com/join/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            avail = data.get("bAvailable", True)
            if not avail:
                return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  28 — ZOOM
# ═══════════════════════════════════════════════════════════════════

async def check_zoom(email: str, client: httpx.AsyncClient) -> dict:
    s = "Zoom"
    try:
        resp = await client.get(
            f"https://zoom.us/account/user/email-check?email={email}",
            headers={"Accept": "application/json", "Referer": "https://zoom.us/signup"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("existed") or data.get("status") is False:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  29 — FIGMA
# ═══════════════════════════════════════════════════════════════════

async def check_figma(email: str, client: httpx.AsyncClient) -> dict:
    s = "Figma"
    try:
        resp = await client.post(
            "https://www.figma.com/api/session/check_email",
            json={"email": email},
            headers={"Content-Type": "application/json", "Referer": "https://www.figma.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == 200 or data.get("type") in ("user", "google"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  30 — NOTION
# ═══════════════════════════════════════════════════════════════════

async def check_notion(email: str, client: httpx.AsyncClient) -> dict:
    s = "Notion"
    try:
        resp = await client.post(
            "https://www.notion.so/api/v3/getAssetsForEmail",
            json={"email": email},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("hasAccount") or data.get("userId"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  31 — PATREON
# ═══════════════════════════════════════════════════════════════════

async def check_patreon(email: str, client: httpx.AsyncClient) -> dict:
    s = "Patreon"
    try:
        resp = await client.post(
            "https://www.patreon.com/api/auth/login",
            json={"data": {"email": email, "password": "fakepw_probe_123"}},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if resp.status_code == 401:
            # 401 = e-posta var ama şifre yanlış
            return _found(s, "Hesap tespit edildi")
        if data and isinstance(data, dict):
            errs = data.get("errors", [])
            for e in errs:
                msg = str(e).lower()
                if "password" in msg or "incorrect" in msg:
                    return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  32 — QUORA
# ═══════════════════════════════════════════════════════════════════

async def check_quora(email: str, client: httpx.AsyncClient) -> dict:
    s = "Quora"
    try:
        resp = await client.post(
            "https://www.quora.com/webnode2/server_call_POST?formkey=unknown",
            data={"email": email, "json": '{"args":[],"kwargs":{}}'},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.quora.com/",
            },
        )
        body = resp.text.lower()
        if "exists" in body or "true" in body:
            return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  33 — EVERNOTE
# ═══════════════════════════════════════════════════════════════════

async def check_evernote(email: str, client: httpx.AsyncClient) -> dict:
    s = "Evernote"
    try:
        resp = await client.get(
            f"https://www.evernote.com/Registration.action?email={email}",
            headers={"Accept": "text/html"},
        )
        body = resp.text.lower()
        if "already" in body and "account" in body:
            return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  34 — LAST.FM
# ═══════════════════════════════════════════════════════════════════

async def check_lastfm(email: str, client: httpx.AsyncClient) -> dict:
    s = "Last.fm"
    try:
        resp = await client.get(
            f"https://www.last.fm/join/partial/validate?email={email}",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            email_err = data.get("email", {})
            if isinstance(email_err, dict) and email_err.get("valid") is False:
                return _found(s, "E-posta kayıtlı")
            elif isinstance(email_err, str) and "already" in email_err.lower():
                return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  35 — VIMEO
# ═══════════════════════════════════════════════════════════════════

async def check_vimeo(email: str, client: httpx.AsyncClient) -> dict:
    s = "Vimeo"
    try:
        resp = await client.get(
            f"https://vimeo.com/_rv/viewer/email?email={email}",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("exists") or data.get("is_registered"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  36 — DAILYMOTION
# ═══════════════════════════════════════════════════════════════════

async def check_dailymotion(email: str, client: httpx.AsyncClient) -> dict:
    s = "Dailymotion"
    try:
        resp = await client.get(
            f"https://www.dailymotion.com/ajax/emailcheck?email={email}",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("exists") or data.get("status") == "taken":
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  37 — CHESS.COM
# ═══════════════════════════════════════════════════════════════════

async def check_chesscom(email: str, client: httpx.AsyncClient) -> dict:
    s = "Chess.com"
    try:
        resp = await client.get(
            f"https://www.chess.com/callback/email/available?email={email}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            avail = data.get("isEmailAvailable", True)
            if not avail:
                return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  38 — STRAVA
# ═══════════════════════════════════════════════════════════════════

async def check_strava(email: str, client: httpx.AsyncClient) -> dict:
    s = "Strava"
    try:
        resp = await client.post(
            "https://www.strava.com/athletes/email_unique",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        body = resp.text.strip().lower()
        if body == "false":
            return _found(s, "E-posta kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  39 — SOUNDCLOUD
# ═══════════════════════════════════════════════════════════════════

async def check_soundcloud(email: str, client: httpx.AsyncClient) -> dict:
    s = "SoundCloud"
    try:
        resp = await client.post(
            "https://soundcloud.com/connect/session",
            data={"client_id": "iZIs9mchVcX5lhVRyQGGAYlNPVldzAoX", "email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code in (200, 401, 403):
            data = _safe_json(resp)
            if data and "password" in str(data).lower():
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  40 — DEEZER
# ═══════════════════════════════════════════════════════════════════

async def check_deezer(email: str, client: httpx.AsyncClient) -> dict:
    s = "Deezer"
    try:
        resp = await client.get(
            f"https://api.deezer.com/email?email={email}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  41 — CANVA
# ═══════════════════════════════════════════════════════════════════

async def check_canva(email: str, client: httpx.AsyncClient) -> dict:
    s = "Canva"
    try:
        resp = await client.post(
            "https://www.canva.com/_ajax/email/check",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.canva.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("registered") or data.get("exists"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  42 — WATTPAD
# ═══════════════════════════════════════════════════════════════════

async def check_wattpad(email: str, client: httpx.AsyncClient) -> dict:
    s = "Wattpad"
    try:
        resp = await client.get(
            f"https://www.wattpad.com/api/v3/users/validate?email={email}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            # 409 veya error ile e-posta alınmışsa
            if resp.status_code in (409, 422):
                return _found(s, "E-posta kullanımda")
            if data.get("status") == "taken" or "taken" in str(data).lower():
                return _found(s, "E-posta kullanımda")
        if resp.status_code in (409, 422):
            return _found(s, "E-posta kullanımda")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  43 — YAHOO
# ═══════════════════════════════════════════════════════════════════

async def check_yahoo(email: str, client: httpx.AsyncClient) -> dict:
    s = "Yahoo"
    try:
        resp = await client.post(
            "https://login.yahoo.com/",
            data={"username": email, "signin": "Next", "persistent": "y"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://login.yahoo.com/",
            },
        )
        body = resp.text.lower()
        if "password" in body and ("challenge" in body or "verify" in body):
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  44 — PROTONMAIL
# ═══════════════════════════════════════════════════════════════════

async def check_protonmail(email: str, client: httpx.AsyncClient) -> dict:
    s = "ProtonMail"
    try:
        resp = await client.get(
            f"https://account.proton.me/api/users/available?Name={email.split('@')[0]}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if resp.status_code == 409 or (data and data.get("Code") == 2500):
            return _found(s, "Kullanıcı adı alınmış")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  45 — FLICKR
# ═══════════════════════════════════════════════════════════════════

async def check_flickr(email: str, client: httpx.AsyncClient) -> dict:
    s = "Flickr"
    try:
        resp = await client.post(
            "https://identity-api.flickr.com/email-check",
            json={"email": email},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("exists") or data.get("emailTaken"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  46 — BITBUCKET / ATLASSIAN
# ═══════════════════════════════════════════════════════════════════

async def check_bitbucket(email: str, client: httpx.AsyncClient) -> dict:
    s = "Atlassian / Bitbucket"
    try:
        resp = await client.post(
            "https://id.atlassian.com/gateway/api/check-email",
            json={"email": email},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("exists") or data.get("action") == "login":
                return _found(s, "Atlassian hesabı bulundu")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  47 — MOZILLA / FIREFOX ACCOUNTS
# ═══════════════════════════════════════════════════════════════════

async def check_mozilla(email: str, client: httpx.AsyncClient) -> dict:
    s = "Mozilla / Firefox"
    try:
        resp = await client.post(
            "https://accounts.firefox.com/v1/account/status",
            json={"email": email},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("exists"):
                return _found(s, "Firefox hesabı bulundu")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  48 — HUBSPOT
# ═══════════════════════════════════════════════════════════════════

async def check_hubspot(email: str, client: httpx.AsyncClient) -> dict:
    s = "HubSpot"
    try:
        resp = await client.post(
            "https://api.hubspot.com/login-verify/check-email",
            json={"email": email},
            headers={"Content-Type": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("ok") or data.get("status") == "EXISTING":
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  49 — BOOKING.COM
# ═══════════════════════════════════════════════════════════════════

async def check_booking(email: str, client: httpx.AsyncClient) -> dict:
    s = "Booking.com"
    try:
        resp = await client.post(
            "https://account.booking.com/api/identity/check",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://account.booking.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("accountExists") or data.get("hasExistingAccount"):
                return _found(s)
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  50 — TRELLO
# ═══════════════════════════════════════════════════════════════════

async def check_trello(email: str, client: httpx.AsyncClient) -> dict:
    s = "Trello"
    try:
        resp = await client.get(
            f"https://trello.com/1/search/members?query={email}",
            headers={"Accept": "application/json"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, list) and len(data) > 0:
            uname = data[0].get("username", "—")
            return _found(s, f"Kullanıcı: {uname}")
        return _not_found(s)
    except Exception:
        return _err(s)



# ═══════════════════════════════════════════════════════════════════
#  EK KÜRESEL PLATFORMLAR
# ═══════════════════════════════════════════════════════════════════

async def check_vk(email: str, client: httpx.AsyncClient) -> dict:
    """VK (VKontakte) hesabı kontrolü."""
    s = "VK"
    try:
        resp = await client.post(
            "https://vk.com/login",
            data={"act": "recovery", "email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Referer": "https://vk.com/"},
        )
        body = resp.text.lower()
        if "password" in body or "sent" in body or "email" in body and resp.status_code == 200:
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_badoo(email: str, client: httpx.AsyncClient) -> dict:
    """Badoo hesabı kontrolü."""
    s = "Badoo"
    try:
        resp = await client.post(
            "https://badoo.com/api/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://badoo.com/",
                     "Origin": "https://badoo.com"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "ok" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        if resp.status_code == 200:
            return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_tinder(email: str, client: httpx.AsyncClient) -> dict:
    """Tinder hesabı kontrolü."""
    s = "Tinder"
    try:
        resp = await client.post(
            "https://api.gotinder.com/v2/auth/email/otp",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://tinder.com/",
                     "Origin": "https://tinder.com"},
        )
        data = _safe_json(resp)
        if resp.status_code in (200, 201):
            return _found(s, "Hesap kayıtlı")
        if data and isinstance(data, dict):
            if data.get("error") and "not found" not in str(data).lower():
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_medium(email: str, client: httpx.AsyncClient) -> dict:
    """Medium hesabı kontrolü."""
    s = "Medium"
    try:
        resp = await client.post(
            "https://medium.com/_/api/users/profile/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://medium.com/",
                     "Origin": "https://medium.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("payload"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_devto(email: str, client: httpx.AsyncClient) -> dict:
    """Dev.to (developer community) hesabı kontrolü."""
    s = "Dev.to"
    try:
        resp = await client.post(
            "https://dev.to/users/password",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://dev.to/enter"},
        )
        if resp.status_code == 200:
            body = resp.text.lower()
            if "email" in body or "sent" in body or "success" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_stackoverflow(email: str, client: httpx.AsyncClient) -> dict:
    """Stack Overflow hesabı kontrolü."""
    s = "Stack Overflow"
    try:
        resp = await client.post(
            "https://stackoverflow.com/users/forgot-password",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Referer": "https://stackoverflow.com/"},
        )
        if resp.status_code == 200:
            body = resp.text.lower()
            if "email" in body or "sent" in body or "check" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_dribbble(email: str, client: httpx.AsyncClient) -> dict:
    """Dribbble tasarım platformu hesabı kontrolü."""
    s = "Dribbble"
    try:
        resp = await client.post(
            "https://dribbble.com/sessions",
            data={"action": "forgot", "login": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Referer": "https://dribbble.com/"},
        )
        if resp.status_code in (200, 302):
            body = resp.text.lower()
            if "email" in body or "sent" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_etsy(email: str, client: httpx.AsyncClient) -> dict:
    """Etsy el yapımı ürünler platformu hesabı kontrolü."""
    s = "Etsy"
    try:
        resp = await client.post(
            "https://www.etsy.com/api/v3/ajax/member/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "x-csrf-token": "not-needed",
                     "Referer": "https://www.etsy.com/",
                     "Origin": "https://www.etsy.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("sent"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_airbnb(email: str, client: httpx.AsyncClient) -> dict:
    """Airbnb hesabı kontrolü."""
    s = "Airbnb"
    try:
        resp = await client.post(
            "https://www.airbnb.com/api/v2/users/forgot_password",
            json={"email": email, "locale": "tr"},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.airbnb.com/",
                     "Origin": "https://www.airbnb.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("message"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_uber(email: str, client: httpx.AsyncClient) -> dict:
    """Uber hesabı kontrolü."""
    s = "Uber"
    try:
        resp = await client.post(
            "https://auth.uber.com/v2/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://auth.uber.com/",
                     "Origin": "https://auth.uber.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_paypal(email: str, client: httpx.AsyncClient) -> dict:
    """PayPal hesabı kontrolü."""
    s = "PayPal"
    try:
        resp = await client.post(
            "https://www.paypal.com/auth/validateEmail",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.paypal.com/",
                     "Origin": "https://www.paypal.com"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            # PayPal: email varsa "isEmailAvailable": false döner
            if data.get("isEmailAvailable") is False:
                return _found(s, "Hesap kayıtlı")
            if data.get("isValid") or resp.status_code == 200:
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_binance(email: str, client: httpx.AsyncClient) -> dict:
    """Binance kripto borsası hesabı kontrolü."""
    s = "Binance"
    try:
        resp = await client.post(
            "https://accounts.binance.com/bapi/accounts/v1/public/authcenter/"
            "send-code/forget-password",
            json={"email": email, "validateCodeType": 1},
            headers={"Content-Type": "application/json",
                     "Referer": "https://accounts.binance.com/",
                     "Origin": "https://accounts.binance.com"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success"):
                return _found(s, "Hesap kayıtlı")
            code = data.get("code", "")
            if code not in ("000000",) and "not" not in str(data).lower():
                return _found(s, "Hesap tespit edildi")
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_coinbase(email: str, client: httpx.AsyncClient) -> dict:
    """Coinbase kripto borsası hesabı kontrolü."""
    s = "Coinbase"
    try:
        resp = await client.post(
            "https://api.coinbase.com/v2/auth/reset_password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.coinbase.com/",
                     "Origin": "https://www.coinbase.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("data") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_coursera(email: str, client: httpx.AsyncClient) -> dict:
    """Coursera online eğitim platformu hesabı kontrolü."""
    s = "Coursera"
    try:
        resp = await client.post(
            "https://www.coursera.org/api/login/v3",
            json={"email": email, "password": "FakeProbe123!"},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.coursera.org/",
                     "Origin": "https://www.coursera.org"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            msg = str(data).lower()
            # Yanlış şifre = hesap var
            if "password" in msg or "incorrect" in msg or "invalid" in msg:
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_udemy(email: str, client: httpx.AsyncClient) -> dict:
    """Udemy online kurs platformu hesabı kontrolü."""
    s = "Udemy"
    try:
        resp = await client.post(
            "https://www.udemy.com/api-2.0/auth/forgot-password/",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.udemy.com/",
                     "Origin": "https://www.udemy.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("detail") and "not" not in str(data.get("detail", "")).lower():
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_academia(email: str, client: httpx.AsyncClient) -> dict:
    """Academia.edu akademik platform hesabı kontrolü."""
    s = "Academia.edu"
    try:
        resp = await client.post(
            "https://www.academia.edu/forgot_password",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Referer": "https://www.academia.edu/"},
        )
        if resp.status_code in (200, 302):
            body = resp.text.lower()
            if "sent" in body or "email" in body or "reset" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_researchgate(email: str, client: httpx.AsyncClient) -> dict:
    """ResearchGate akademik ağ hesabı kontrolü."""
    s = "ResearchGate"
    try:
        resp = await client.post(
            "https://www.researchgate.net/application.ResetPasswordController"
            ".sendPasswordReset.html",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.researchgate.net/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("status") == "success":
                return _found(s, "Hesap kayıtlı")
        if resp.status_code == 200:
            body = resp.text.lower()
            if "sent" in body or "reset" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_scribd(email: str, client: httpx.AsyncClient) -> dict:
    """Scribd dijital kütüphane hesabı kontrolü."""
    s = "Scribd"
    try:
        resp = await client.post(
            "https://www.scribd.com/login",
            data={"email": email, "password": "FakeProbe123!"},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.scribd.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            msg = str(data).lower()
            if "password" in msg or "incorrect" in msg:
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_producthunt(email: str, client: httpx.AsyncClient) -> dict:
    """Product Hunt teknoloji platformu hesabı kontrolü."""
    s = "Product Hunt"
    try:
        resp = await client.post(
            "https://api.producthunt.com/v1/oauth/token",
            json={"email": email, "password": "FakeProbe123!",
                  "grant_type": "password"},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.producthunt.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            msg = str(data).lower()
            if "password" in msg or "invalid_grant" in msg:
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_kickstarter(email: str, client: httpx.AsyncClient) -> dict:
    """Kickstarter kitlesel fonlama platformu hesabı kontrolü."""
    s = "Kickstarter"
    try:
        resp = await client.post(
            "https://www.kickstarter.com/forgot_password",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.kickstarter.com/"},
        )
        if resp.status_code == 200:
            body = resp.text.lower()
            if "sent" in body or "email" in body or "reset" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_fiverr(email: str, client: httpx.AsyncClient) -> dict:
    """Fiverr freelance iş platformu hesabı kontrolü."""
    s = "Fiverr"
    try:
        resp = await client.post(
            "https://www.fiverr.com/api/v1/public/users/password_reset_request",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.fiverr.com/",
                     "Origin": "https://www.fiverr.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("status") == "ok":
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_upwork(email: str, client: httpx.AsyncClient) -> dict:
    """Upwork freelance platformu hesabı kontrolü."""
    s = "Upwork"
    try:
        resp = await client.post(
            "https://www.upwork.com/ab/account-security/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.upwork.com/",
                     "Origin": "https://www.upwork.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("ok"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_freelancer(email: str, client: httpx.AsyncClient) -> dict:
    """Freelancer.com iş platformu hesabı kontrolü."""
    s = "Freelancer"
    try:
        resp = await client.post(
            "https://www.freelancer.com/ajax/users/recover-password.php",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.freelancer.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("result"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_deviantart(email: str, client: httpx.AsyncClient) -> dict:
    """DeviantArt sanat platformu hesabı kontrolü."""
    s = "DeviantArt"
    try:
        resp = await client.post(
            "https://www.deviantart.com/users/forgot_password",
            data={"username": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.deviantart.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        if resp.status_code == 200:
            body = resp.text.lower()
            if "sent" in body or "reset" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_artstation(email: str, client: httpx.AsyncClient) -> dict:
    """ArtStation profesyonel sanat portföyü platformu hesabı kontrolü."""
    s = "ArtStation"
    try:
        resp = await client.post(
            "https://www.artstation.com/api/v2/users/password_reset",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.artstation.com/",
                     "Origin": "https://www.artstation.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("status") == "ok":
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_500px(email: str, client: httpx.AsyncClient) -> dict:
    """500px fotoğrafçılık platformu hesabı kontrolü."""
    s = "500px"
    try:
        resp = await client.post(
            "https://api.500px.com/v1/users/forgot_password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://500px.com/",
                     "Origin": "https://500px.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("message"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_codecademy(email: str, client: httpx.AsyncClient) -> dict:
    """Codecademy programlama eğitim platformu hesabı kontrolü."""
    s = "Codecademy"
    try:
        resp = await client.post(
            "https://www.codecademy.com/api/v1/user_sessions/forgot_password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.codecademy.com/",
                     "Origin": "https://www.codecademy.com"},
        )
        if resp.status_code in (200, 201):
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("status") == "ok":
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_crunchbase(email: str, client: httpx.AsyncClient) -> dict:
    """Crunchbase iş ve startup platformu hesabı kontrolü."""
    s = "Crunchbase"
    try:
        resp = await client.post(
            "https://www.crunchbase.com/api/v4/entity_auth/forgot_password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.crunchbase.com/",
                     "Origin": "https://www.crunchbase.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("result"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_linktree(email: str, client: httpx.AsyncClient) -> dict:
    """Linktree biyografi link platformu hesabı kontrolü."""
    s = "Linktree"
    try:
        resp = await client.post(
            "https://linktr.ee/api/user/forgot-password/request",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://linktr.ee/",
                     "Origin": "https://linktr.ee"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("message"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_behance(email: str, client: httpx.AsyncClient) -> dict:
    """Behance (Adobe) tasarım portföy platformu hesabı kontrolü."""
    s = "Behance"
    try:
        # Behance Adobe ID kullanır
        resp = await client.post(
            "https://accounts.adobe.com/api/v1/send-password-reset",
            json={"username": email, "client_id": "behance"},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.behance.net/",
                     "Origin": "https://www.behance.net"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("result"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  TÜRK PLATFORMLARI
# ═══════════════════════════════════════════════════════════════════

async def check_trendyol(email: str, client: httpx.AsyncClient) -> dict:
    """Trendyol hesabı kontrolü — şifre sıfırlama endpoint'i."""
    s = "Trendyol"
    try:
        resp = await client.post(
            "https://public.trendyol.com/auth-web-core/password-reset/send-mail",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.trendyol.com/",
                "Origin": "https://www.trendyol.com",
            },
        )
        data = _safe_json(resp)
        # 200 veya success = hesap var
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        if data and isinstance(data, dict):
            if data.get("success") or data.get("result"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_hepsiburada(email: str, client: httpx.AsyncClient) -> dict:
    """Hepsiburada hesabı kontrolü — üyelik doğrulama."""
    s = "Hepsiburada"
    try:
        resp = await client.post(
            "https://giris.hepsiburada.com/giris/v4/authenticate",
            json={"UserName": email, "Password": "Probe123!Fake", "RememberMe": False},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://giris.hepsiburada.com/",
                "Origin": "https://giris.hepsiburada.com",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            # Yanlış şifre hatası = hesap var
            errors = data.get("Errors", []) or data.get("errors", [])
            msg = str(errors).lower()
            if "password" in msg or "sifre" in msg or "şifre" in msg:
                return _found(s, "Hesap tespit edildi")
            if data.get("IsAuthenticated"):
                return _found(s, "Hesap kayıtlı")
        if resp.status_code in (401, 400):
            # 401 = kimlik bilgileri yanlış ama hesap var
            if resp.status_code == 401:
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_sahibinden(email: str, client: httpx.AsyncClient) -> dict:
    """Sahibinden.com hesabı kontrolü."""
    s = "Sahibinden"
    try:
        resp = await client.post(
            "https://www.sahibinden.com/ajax/user/login",
            data={"login": email, "password": "FakeProbe123!"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.sahibinden.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            msg = str(data).lower()
            # Hatalı şifre mesajı = hesap var
            if "sifre" in msg or "parola" in msg or "password" in msg:
                return _found(s, "Hesap tespit edildi")
            err_code = data.get("errorCode", "")
            if err_code in ("WRONG_PASSWORD", "INVALID_PASSWORD"):
                return _found(s, "Hesap tespit edildi")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_eksisozluk(email: str, client: httpx.AsyncClient) -> dict:
    """Ekşi Sözlük hesabı kontrolü — şifre sıfırlama."""
    s = "Ekşi Sözlük"
    try:
        resp = await client.post(
            "https://eksisozluk.com/usercontrols/login/forgotpassword",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://eksisozluk.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("Success") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        # 200 ve body içinde "gönderildi" gibi ifadeler
        body = resp.text.lower()
        if "gönderildi" in body or "sent" in body:
            return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_n11(email: str, client: httpx.AsyncClient) -> dict:
    """N11.com hesabı kontrolü."""
    s = "N11"
    try:
        resp = await client.post(
            "https://www.n11.com/ajax/useractions/forgotpassword",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.n11.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
            msg = str(data).lower()
            if "gönderildi" in msg or "sent" in msg:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_gittigidiyor(email: str, client: httpx.AsyncClient) -> dict:
    """GittiGidiyor hesabı kontrolü."""
    s = "GittiGidiyor"
    try:
        resp = await client.post(
            "https://www.gittigidiyor.com/gg-auth/forgotpassword",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.gittigidiyor.com/",
                "Origin": "https://www.gittigidiyor.com",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or resp.status_code == 200:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_yemeksepeti(email: str, client: httpx.AsyncClient) -> dict:
    """Yemeksepeti hesabı kontrolü."""
    s = "Yemeksepeti"
    try:
        resp = await client.post(
            "https://www.yemeksepeti.com/api/v1/users/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.yemeksepeti.com/",
                "Origin": "https://www.yemeksepeti.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("IsSuccess") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_ciceksepeti(email: str, client: httpx.AsyncClient) -> dict:
    """Çiçeksepeti hesabı kontrolü."""
    s = "Çiçeksepeti"
    try:
        resp = await client.post(
            "https://www.ciceksepeti.com/api/account/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.ciceksepeti.com/",
                "Origin": "https://www.ciceksepeti.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("isSuccess") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_getir(email: str, client: httpx.AsyncClient) -> dict:
    """Getir hesabı kontrolü."""
    s = "Getir"
    try:
        resp = await client.post(
            "https://getir.com/api/v1/users/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://getir.com/",
                "Origin": "https://getir.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("result") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_dolap(email: str, client: httpx.AsyncClient) -> dict:
    """Dolap (ikinci el moda) hesabı kontrolü."""
    s = "Dolap"
    try:
        resp = await client.post(
            "https://dolap.com/api/user/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://dolap.com/",
                "Origin": "https://dolap.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_sikayetvar(email: str, client: httpx.AsyncClient) -> dict:
    """Şikayetvar hesabı kontrolü."""
    s = "Şikayetvar"
    try:
        resp = await client.post(
            "https://www.sikayetvar.com/api/users/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.sikayetvar.com/",
                "Origin": "https://www.sikayetvar.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
            msg = str(data).lower()
            if "gönderildi" in msg or "sent" in msg:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_onedio(email: str, client: httpx.AsyncClient) -> dict:
    """Onedio hesabı kontrolü."""
    s = "Onedio"
    try:
        resp = await client.post(
            "https://onedio.com/api/user/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://onedio.com/",
                "Origin": "https://onedio.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_akakce(email: str, client: httpx.AsyncClient) -> dict:
    """Akakçe fiyat karşılaştırma platformu hesabı kontrolü."""
    s = "Akakçe"
    try:
        resp = await client.post(
            "https://www.akakce.com/ajax/forgot-password.html",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.akakce.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("result") == 1 or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        body = resp.text.lower()
        if "gönderildi" in body or "başarı" in body or "sent" in body:
            return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_izlesene(email: str, client: httpx.AsyncClient) -> dict:
    """İzlesene video platformu hesabı kontrolü."""
    s = "İzlesene"
    try:
        resp = await client.post(
            "https://www.izlesene.com/ajax/forgot-password",
            data={"email": email},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.izlesene.com/",
            },
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "ok" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        body = resp.text.lower()
        if "gönderildi" in body or "sent" in body:
            return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_bitaksi(email: str, client: httpx.AsyncClient) -> dict:
    """BiTaksi uygulama hesabı kontrolü."""
    s = "BiTaksi"
    try:
        resp = await client.post(
            "https://api.bitaksi.com/user/forgot-password",
            json={"email": email},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.bitaksi.com/",
                "Origin": "https://www.bitaksi.com",
            },
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
#  EK TÜRK PLATFORMLARI
# ═══════════════════════════════════════════════════════════════════

async def check_papara(email: str, client: httpx.AsyncClient) -> dict:
    """Papara dijital cüzdan hesabı kontrolü."""
    s = "Papara"
    try:
        resp = await client.post(
            "https://merchant.papara.com/api/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.papara.com/",
                     "Origin": "https://www.papara.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("succeeded") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_iyzico(email: str, client: httpx.AsyncClient) -> dict:
    """iyzico ödeme platformu hesabı kontrolü."""
    s = "iyzico"
    try:
        resp = await client.post(
            "https://merchant.iyzipay.com/api/v1/auth/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.iyzico.com/",
                     "Origin": "https://www.iyzico.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_enuygun(email: str, client: httpx.AsyncClient) -> dict:
    """Enuygun seyahat karşılaştırma platformu hesabı kontrolü."""
    s = "Enuygun"
    try:
        resp = await client.post(
            "https://www.enuygun.com/api/users/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.enuygun.com/",
                     "Origin": "https://www.enuygun.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_obilet(email: str, client: httpx.AsyncClient) -> dict:
    """Obilet otobüs bileti platformu hesabı kontrolü."""
    s = "Obilet"
    try:
        resp = await client.post(
            "https://api.obilet.com/api/v2/Users/ForgotPassword",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.obilet.com/",
                     "Origin": "https://www.obilet.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("IsSuccess") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_biletix(email: str, client: httpx.AsyncClient) -> dict:
    """Biletix etkinlik bileti platformu hesabı kontrolü."""
    s = "Biletix"
    try:
        resp = await client.post(
            "https://www.biletix.com/api/user/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.biletix.com/",
                     "Origin": "https://www.biletix.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_kitapyurdu(email: str, client: httpx.AsyncClient) -> dict:
    """Kitapyurdu online kitap mağazası hesabı kontrolü."""
    s = "Kitapyurdu"
    try:
        resp = await client.post(
            "https://www.kitapyurdu.com/ajax/user/forgot-password",
            data={"email": email},
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.kitapyurdu.com/"},
        )
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("status") == "success" or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        if resp.status_code == 200:
            body = resp.text.lower()
            if "gönderildi" in body or "sent" in body:
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_dr(email: str, client: httpx.AsyncClient) -> dict:
    """D&R kitap müzik platform hesabı kontrolü."""
    s = "D&R"
    try:
        resp = await client.post(
            "https://www.dr.com.tr/api/account/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.dr.com.tr/",
                     "Origin": "https://www.dr.com.tr"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_armut(email: str, client: httpx.AsyncClient) -> dict:
    """Armut.com ev hizmetleri platformu hesabı kontrolü."""
    s = "Armut"
    try:
        resp = await client.post(
            "https://armut.com/api/v4/auth/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://armut.com/",
                     "Origin": "https://armut.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_modanisa(email: str, client: httpx.AsyncClient) -> dict:
    """Modanisa moda platformu hesabı kontrolü."""
    s = "Modanisa"
    try:
        resp = await client.post(
            "https://www.modanisa.com/tr/api/v1/user/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.modanisa.com/",
                     "Origin": "https://www.modanisa.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_defacto(email: str, client: httpx.AsyncClient) -> dict:
    """DeFacto moda mağazası hesabı kontrolü."""
    s = "DeFacto"
    try:
        resp = await client.post(
            "https://www.defacto.com.tr/api/users/password/forgot",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.defacto.com.tr/",
                     "Origin": "https://www.defacto.com.tr"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("isSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_lcwaikiki(email: str, client: httpx.AsyncClient) -> dict:
    """LC Waikiki moda mağazası hesabı kontrolü."""
    s = "LC Waikiki"
    try:
        resp = await client.post(
            "https://www.lcwaikiki.com/tr-TR/api/v1/auth/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.lcwaikiki.com/",
                     "Origin": "https://www.lcwaikiki.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("IsSuccess") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_boyner(email: str, client: httpx.AsyncClient) -> dict:
    """Boyner moda ve alışveriş merkezi hesabı kontrolü."""
    s = "Boyner"
    try:
        resp = await client.post(
            "https://www.boyner.com.tr/api/account/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.boyner.com.tr/",
                     "Origin": "https://www.boyner.com.tr"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("IsSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_migros(email: str, client: httpx.AsyncClient) -> dict:
    """Migros online market hesabı kontrolü."""
    s = "Migros Online"
    try:
        resp = await client.post(
            "https://www.migros.com.tr/rest/user/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.migros.com.tr/",
                     "Origin": "https://www.migros.com.tr"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("successful") or data.get("success"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_carrefoursa(email: str, client: httpx.AsyncClient) -> dict:
    """CarrefourSA online market hesabı kontrolü."""
    s = "CarrefourSA"
    try:
        resp = await client.post(
            "https://www.carrefoursa.com/api/v2/users/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.carrefoursa.com/",
                     "Origin": "https://www.carrefoursa.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("IsSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


async def check_pttavm(email: str, client: httpx.AsyncClient) -> dict:
    """PTT AVM marketplace hesabı kontrolü."""
    s = "PTT AVM"
    try:
        resp = await client.post(
            "https://www.pttavm.com/api/user/forgot-password",
            json={"email": email},
            headers={"Content-Type": "application/json",
                     "Referer": "https://www.pttavm.com/",
                     "Origin": "https://www.pttavm.com"},
        )
        if resp.status_code == 200:
            return _found(s, "Hesap kayıtlı")
        data = _safe_json(resp)
        if data and isinstance(data, dict):
            if data.get("success") or data.get("IsSuccess"):
                return _found(s, "Hesap kayıtlı")
        return _not_found(s)
    except Exception:
        return _err(s)


# ═══════════════════════════════════════════════════════════════════
# TÜM SERVİSLERİN LİSTESİ — 110 Platform (80 global + 30 Türk)
# ═══════════════════════════════════════════════════════════════════

ALL_SERVICES: list[tuple[str, Any]] = [
    # Geliştirici Platformları
    ("GitHub",              check_github),
    ("GitLab",              check_gitlab),
    ("Atlassian / Bitbucket", check_bitbucket),
    ("Figma",               check_figma),
    ("Notion",              check_notion),
    ("Trello",              check_trello),
    ("HubSpot",             check_hubspot),

    # Sosyal Medya
    ("Twitter / X",         check_twitter),
    ("Instagram",           check_instagram),
    ("TikTok",              check_tiktok),
    ("Snapchat",            check_snapchat),
    ("Pinterest",           check_pinterest),
    ("LinkedIn",            check_linkedin),
    ("Reddit",              check_reddit),
    ("Tumblr",              check_tumblr),
    ("Quora",               check_quora),

    # Eğlence & Medya
    ("Spotify",             check_spotify),
    ("Netflix",             check_netflix),
    ("Twitch",              check_twitch),
    ("SoundCloud",          check_soundcloud),
    ("Deezer",              check_deezer),
    ("Vimeo",               check_vimeo),
    ("Dailymotion",         check_dailymotion),
    ("Last.fm",             check_lastfm),
    ("Flickr",              check_flickr),
    ("Wattpad",             check_wattpad),
    ("Imgur",               check_imgur),

    # Oyun
    ("Discord",             check_discord),
    ("Steam",               check_steam),
    ("Epic Games",          check_epicgames),
    ("Roblox",              check_roblox),
    ("Chess.com",           check_chesscom),

    # Büyük Teknoloji
    ("Microsoft",           check_microsoft),
    ("Adobe",               check_adobe),
    ("Apple (ProtonMail)",  check_protonmail),
    ("Mozilla / Firefox",   check_mozilla),
    ("Yahoo",               check_yahoo),
    ("Zoom",                check_zoom),
    ("Canva",               check_canva),

    # Alışveriş & Seyahat
    ("Amazon",              check_amazon),
    ("eBay",                check_ebay),
    ("Booking.com",         check_booking),

    # Depolama & Üretkenlik
    ("Dropbox",             check_dropbox),
    ("WordPress",           check_wordpress),
    ("Evernote",            check_evernote),

    # Diğer
    ("Gravatar",            check_gravatar),
    ("Patreon",             check_patreon),
    ("Strava",              check_strava),
    ("Duolingo",            check_duolingo),

    # Güvenlik
    ("Have I Been Pwned",   check_haveibeenpwned),

    # ── Ek Küresel Platformlar ─────────────────────────────────────
    ("VK",                  check_vk),
    ("Badoo",               check_badoo),
    ("Tinder",              check_tinder),
    ("Medium",              check_medium),
    ("Dev.to",              check_devto),
    ("Stack Overflow",      check_stackoverflow),
    ("Dribbble",            check_dribbble),
    ("Etsy",               check_etsy),
    ("Airbnb",              check_airbnb),
    ("Uber",               check_uber),
    ("PayPal",              check_paypal),
    ("Binance",             check_binance),
    ("Coinbase",            check_coinbase),
    ("Coursera",            check_coursera),
    ("Udemy",               check_udemy),
    ("Academia.edu",        check_academia),
    ("ResearchGate",        check_researchgate),
    ("Scribd",              check_scribd),
    ("Product Hunt",        check_producthunt),
    ("Kickstarter",         check_kickstarter),
    ("Fiverr",              check_fiverr),
    ("Upwork",              check_upwork),
    ("Freelancer",          check_freelancer),
    ("DeviantArt",          check_deviantart),
    ("ArtStation",          check_artstation),
    ("500px",               check_500px),
    ("Codecademy",          check_codecademy),
    ("Crunchbase",          check_crunchbase),
    ("Linktree",            check_linktree),
    ("Behance",             check_behance),

    # ── Türk Platformları (Orijinal 15) ────────────────────────────
    ("Trendyol",            check_trendyol),
    ("Hepsiburada",         check_hepsiburada),
    ("Sahibinden",          check_sahibinden),
    ("Ekşi Sözlük",        check_eksisozluk),
    ("N11",                 check_n11),
    ("GittiGidiyor",        check_gittigidiyor),
    ("Yemeksepeti",         check_yemeksepeti),
    ("Çiçeksepeti",         check_ciceksepeti),
    ("Getir",               check_getir),
    ("Dolap",               check_dolap),
    ("Şikayetvar",          check_sikayetvar),
    ("Onedio",              check_onedio),
    ("Akakçe",              check_akakce),
    ("İzlesene",            check_izlesene),
    ("BiTaksi",             check_bitaksi),

    # ── Türk Platformları (Yeni 15) ────────────────────────────────
    ("Papara",              check_papara),
    ("iyzico",              check_iyzico),
    ("Enuygun",             check_enuygun),
    ("Obilet",              check_obilet),
    ("Biletix",             check_biletix),
    ("Kitapyurdu",          check_kitapyurdu),
    ("D&R",                 check_dr),
    ("Armut",               check_armut),
    ("Modanisa",            check_modanisa),
    ("DeFacto",             check_defacto),
    ("LC Waikiki",          check_lcwaikiki),
    ("Boyner",              check_boyner),
    ("Migros Online",       check_migros),
    ("CarrefourSA",         check_carrefoursa),
    ("PTT AVM",             check_pttavm),
]
