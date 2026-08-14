from __future__ import annotations
import asyncio
import html
import re
import unicodedata
from urllib.parse import quote, unquote

import httpx
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from utils.display import console

# JSON probes require an exact username match. HTML probes require both a
# successful response and an exact username in visible page text.


def _discourse_platform(name: str, base_url: str) -> dict:
    return {
        "name": name,
        "url": f"{base_url}/u/{{}}/summary",
        "probe_url": f"{base_url}/u/{{}}.json",
        "check": "json",
        "json_path": "user.username",
    }


USERNAME_PLATFORMS = [
    # --- Core Global Social Media ---
    {
        "name": "GitHub",
        "url": "https://github.com/{}",
        "probe_url": "https://api.github.com/users/{}",
        "check": "json",
        "json_path": "login",
    },
    {"name": "Twitter/X", "url": "https://twitter.com/{}", "check": "content"},
    {"name": "Instagram", "url": "https://www.instagram.com/{}/", "check": "content"},
    {"name": "TikTok", "url": "https://www.tiktok.com/@{}", "check": "content"},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{}/", "check": "404"},
    {
        "name": "Reddit",
        "url": "https://www.reddit.com/user/{}/",
        "probe_url": "https://www.reddit.com/user/{}/about.json",
        "check": "json",
        "json_path": "data.name",
    },
    {"name": "Facebook", "url": "https://www.facebook.com/{}", "check": "content"},
    {"name": "Snapchat", "url": "https://www.snapchat.com/add/{}", "check": "content"},
    {"name": "Telegram", "url": "https://t.me/{}"},
    {"name": "VK", "url": "https://vk.com/{}"},
    {"name": "OK.ru", "url": "https://ok.ru/{}"},
    {"name": "Myspace", "url": "https://myspace.com/{}"},
    
    # Türk Siteleri & Forumlar
    {"name": "Ekşi Sözlük", "url": "https://eksisozluk.com/biri/{}"},
    {"name": "DonanımHaber", "url": "https://forum.donanimhaber.com/profil/{}"},
    {"name": "KızlarSoruyor", "url": "https://www.kizlarsoruyor.com/uye/{}"},
    {"name": "İnci Sözlük", "url": "http://www.incisozluk.com.tr/w/{}"},
    {"name": "R10.net", "url": "https://www.r10.net/members/{}"},
    {"name": "Technopat", "url": "https://www.technopat.net/sosyal/uye/{}"},
    {"name": "ShiftDelete", "url": "https://forum.shiftdelete.net/uyeler/{}"},
    
    # Video & Müzik & Yayın
    {"name": "YouTube", "url": "https://www.youtube.com/@{}"},
    {"name": "Twitch", "url": "https://www.twitch.tv/{}"},
    {"name": "SoundCloud", "url": "https://soundcloud.com/{}"},
    {"name": "Spotify", "url": "https://open.spotify.com/user/{}"},
    {"name": "Vimeo", "url": "https://vimeo.com/{}"},
    {"name": "Dailymotion", "url": "https://www.dailymotion.com/{}"},
    {"name": "Bandcamp", "url": "https://bandcamp.com/{}"},
    {"name": "Last.fm", "url": "https://www.last.fm/user/{}"},
    {"name": "Mixcloud", "url": "https://www.mixcloud.com/{}"},
    {"name": "Smule", "url": "https://www.smule.com/{}"},
    
    # Geliştirici & IT & Siber Güvenlik
    {"name": "GitLab", "url": "https://gitlab.com/{}"},
    {"name": "Bitbucket", "url": "https://bitbucket.org/{}/"},
    {"name": "Gitea", "url": "https://gitea.com/{}"},
    {
        "name": "HackerNews",
        "url": "https://news.ycombinator.com/user?id={}",
        "probe_url": "https://hacker-news.firebaseio.com/v0/user/{}.json",
        "check": "json",
        "json_path": "id",
    },
    {"name": "Kaggle", "url": "https://www.kaggle.com/{}"},
    {"name": "LeetCode", "url": "https://leetcode.com/{}"},
    {"name": "HackerRank", "url": "https://www.hackerrank.com/{}"},
    {"name": "TryHackMe", "url": "https://tryhackme.com/p/{}"},
    {"name": "Codecademy", "url": "https://www.codecademy.com/profiles/{}"},
    {"name": "Pastebin", "url": "https://pastebin.com/u/{}"},
    {"name": "DockerHub", "url": "https://hub.docker.com/u/{}"},
    {"name": "NPM", "url": "https://www.npmjs.com/~{}"},
    {"name": "PyPi", "url": "https://pypi.org/user/{}"},
    {"name": "Codepen", "url": "https://codepen.io/{}"},
    {"name": "Replit", "url": "https://replit.com/@{}"},
    
    # Oyun (Gaming)
    {"name": "Steam", "url": "https://steamcommunity.com/id/{}"},
    {"name": "PSNProfiles", "url": "https://psnprofiles.com/{}"},
    {"name": "NameMC (Minecraft)", "url": "https://namemc.com/profile/{}"},
    {"name": "Chess.com", "url": "https://www.chess.com/member/{}"},
    {"name": "Lichess", "url": "https://lichess.org/@/{}"},
    
    # Blog & Makale & Kitap & Tasarım
    {"name": "Medium", "url": "https://medium.com/@{}"},
    {"name": "Dev.to", "url": "https://dev.to/{}"},
    {"name": "Tumblr", "url": "https://{}.tumblr.com/"},
    {"name": "Blogger", "url": "https://{}.blogspot.com/"},
    {"name": "WordPress", "url": "https://{}.wordpress.com/"},
    {"name": "Substack", "url": "https://{}.substack.com/"},
    {"name": "Wattpad", "url": "https://www.wattpad.com/user/{}"},
    {"name": "Fandom", "url": "https://www.fandom.com/u/{}"},
    {"name": "Flickr", "url": "https://www.flickr.com/people/{}/"},
    {"name": "Dribbble", "url": "https://dribbble.com/{}"},
    {"name": "Behance", "url": "https://www.behance.net/{}"},
    {"name": "DeviantArt", "url": "https://www.deviantart.com/{}"},
    {"name": "ArtStation", "url": "https://www.artstation.com/{}"},
    {"name": "Sketchfab", "url": "https://sketchfab.com/{}"},
    
    # Anime & Hobi & Diğer
    {"name": "MyAnimeList", "url": "https://myanimelist.net/profile/{}"},
    {"name": "AniList", "url": "https://anilist.co/user/{}"},
    {"name": "Etsy", "url": "https://www.etsy.com/shop/{}"},
    {"name": "Linktree", "url": "https://linktr.ee/{}"},
    {"name": "About.me", "url": "https://about.me/{}"},
    {"name": "Patreon", "url": "https://www.patreon.com/{}"},
    {"name": "BuyMeACoffee", "url": "https://www.buymeacoffee.com/{}"},
    {"name": "Ko-fi", "url": "https://ko-fi.com/{}"},
    {"name": "Fiverr", "url": "https://www.fiverr.com/{}"},
    {"name": "Freelancer", "url": "https://www.freelancer.com/u/{}"},
    {"name": "TripAdvisor", "url": "https://www.tripadvisor.com/Profile/{}"},
    {"name": "Wikipedia", "url": "https://en.wikipedia.org/wiki/User:{}"},
    {"name": "Gravatar", "url": "https://en.gravatar.com/{}"},
    {"name": "Tinder", "url": "https://tinder.com/@{}"},
    {"name": "9GAG", "url": "https://9gag.com/u/{}"},
    {"name": "Imgur", "url": "https://imgur.com/user/{}"},
    {"name": "Giphy", "url": "https://giphy.com/{}"},
    
    # +100 YENI EKLENEN SITELER (Faz 2 Genişletmesi)
    
    # Türk Forumları ve Topluluklar (Genişletilmiş)
    {"name": "ForumTR", "url": "https://www.frmtr.com/members/{}.html"},
    {"name": "Turkmmo", "url": "https://forum.turkmmo.com/uye/{}/"},
    {"name": "DonanımArşivi", "url": "https://forum.donanimarsivi.com/uyeler/{}/"},
    {"name": "Memurlar.net", "url": "https://forum.memurlar.net/profil/{}/"},
    {"name": "KadınlarKulübü", "url": "https://www.kadinlarkulubu.com/uyeler/{}/"},
    {"name": "Paticik", "url": "https://forum.paticik.com/profile/{}/"},
    
    # Yazılım, IT ve Hacker Forumları
    {"name": "LinuxQuestions", "url": "https://www.linuxquestions.org/questions/user/{}-1/"},
    {"name": "Raspberry Pi", "url": "https://forums.raspberrypi.com/memberlist.php?mode=viewprofile&un={}"},
    _discourse_platform("Arduino Forum", "https://forum.arduino.cc"),
    {"name": "Codeforces", "url": "https://codeforces.com/profile/{}"},
    {"name": "TopCoder", "url": "https://www.topcoder.com/members/{}"},
    {"name": "CodeChef", "url": "https://www.codechef.com/users/{}"},
    {"name": "Hashnode", "url": "https://hashnode.com/@{}"},
    {"name": "SourceHut", "url": "https://sr.ht/~{}/"},
    
    # Kripto, Finans ve Ticaret
    {"name": "TradingView", "url": "https://www.tradingview.com/u/{}/"},
    {"name": "StockTwits", "url": "https://stocktwits.com/{}"},
    {"name": "CoinMarketCap", "url": "https://coinmarketcap.com/community/profile/{}/"},
    {"name": "Investing.com", "url": "https://www.investing.com/members/{}"},
    {"name": "eToro", "url": "https://www.etoro.com/people/{}"},
    
    # Yaratıcılar, Sanat ve Tasarım (Genişletilmiş)
    {"name": "500px", "url": "https://500px.com/p/{}"},
    {"name": "VSCO", "url": "https://vsco.co/{}/gallery"},
    {"name": "EyeEm", "url": "https://www.eyeem.com/u/{}"},
    {"name": "Houzz", "url": "https://www.houzz.com/user/{}"},
    {"name": "Coroflot", "url": "https://www.coroflot.com/{}"},
    {"name": "Carbonmade", "url": "https://{}.carbonmade.com/"},
    {"name": "Threadless", "url": "https://www.threadless.com/@{}"},
    {"name": "Redbubble", "url": "https://www.redbubble.com/people/{}"},
    {"name": "Society6", "url": "https://society6.com/{}"},
    
    # Oyun, E-Spor ve Modding (Genişletilmiş)
    {"name": "Faceit", "url": "https://www.faceit.com/en/players/{}"},
    {"name": "Tracker.gg", "url": "https://tracker.gg/valorant/profile/riot/{}/overview"},
    {"name": "IGN", "url": "https://www.ign.com/user/{}"},
    {"name": "GameSpot", "url": "https://www.gamespot.com/profile/{}/"},
    {"name": "Speedrun.com", "url": "https://www.speedrun.com/users/{}"},
    {"name": "ModDB", "url": "https://www.moddb.com/members/{}"},
    {"name": "Itch.io", "url": "https://{}.itch.io/"},
    {"name": "Kongregate", "url": "https://www.kongregate.com/accounts/{}"},
    {"name": "Newgrounds", "url": "https://{}.newgrounds.com/"},
    
    # +OYUN ODAKLI YENİ EKLENENLER (Riot, İstatistik, Forum)
    {"name": "OP.GG (LoL)", "url": "https://www.op.gg/summoners/tr/{}"},
    {"name": "Valorant (OP.GG)", "url": "https://valorant.op.gg/profile/{}"},
    {"name": "PUBG (OP.GG)", "url": "https://pubg.op.gg/user/{}"},
    {"name": "LeagueOfGraphs", "url": "https://www.leagueofgraphs.com/summoner/tr/{}"},
    {"name": "U.GG", "url": "https://u.gg/lol/profile/tr1/{}/overview"},
    {"name": "Fortnite Tracker", "url": "https://fortnitetracker.com/profile/all/{}"},
    {"name": "R6 Tracker", "url": "https://r6.tracker.network/profile/pc/{}"},
    {"name": "Apex Tracker", "url": "https://apex.tracker.gg/apex/profile/origin/{}/overview"},
    {"name": "Overbuff (Overwatch)", "url": "https://www.overbuff.com/players/pc/{}"},
    {"name": "Osu!", "url": "https://osu.ppy.sh/users/{}"},
    {"name": "TrueAchievements (Xbox)", "url": "https://www.trueachievements.com/gamer/{}"},
    {"name": "TrueTrophies (PSN)", "url": "https://www.truetrophies.com/gamer/{}"},
    {"name": "Exophase", "url": "https://www.exophase.com/user/{}/"},
    {"name": "GameFAQs", "url": "https://gamefaqs.gamespot.com/community/{}"},
    {"name": "GiantBomb", "url": "https://www.giantbomb.com/profile/{}/"},
    {"name": "Destructoid", "url": "https://www.destructoid.com/users/{}/"},
    {"name": "NintendoLife", "url": "https://www.nintendolife.com/users/{}"},
    {"name": "PushSquare", "url": "https://www.pushsquare.com/users/{}"},
    {"name": "PureXbox", "url": "https://www.purexbox.com/users/{}"},
    {"name": "MMORPG.com", "url": "https://forums.mmorpg.com/profile/{}"},
    {"name": "GOG Forum", "url": "https://www.gog.com/forum/user/{}"},
    
    # Video, Müzik ve Yayın (Genişletilmiş)
    {"name": "Rumble", "url": "https://rumble.com/c/{}"},
    {"name": "Odysee", "url": "https://odysee.com/@{}"},
    {"name": "Bitchute", "url": "https://www.bitchute.com/channel/{}/"},
    {"name": "Trovo", "url": "https://trovo.live/{}"},
    {"name": "Audiomack", "url": "https://audiomack.com/{}"},
    {"name": "ReverbNation", "url": "https://www.reverbnation.com/{}"},
    {"name": "Hearthis.at", "url": "https://hearthis.at/{}/"},
    
    # Okuma, Yazma, Kültür & Hobi
    {"name": "Quora", "url": "https://www.quora.com/profile/{}"},
    {"name": "Zhihu", "url": "https://www.zhihu.com/people/{}"},
    {"name": "LiveJournal", "url": "https://{}.livejournal.com/"},
    {"name": "ArchiveOfOurOwn", "url": "https://archiveofourown.org/users/{}/profile"},
    {"name": "Letterboxd", "url": "https://letterboxd.com/{}/"},
    {"name": "Trakt", "url": "https://trakt.tv/users/{}"},
    {"name": "BoardGameGeek", "url": "https://boardgamegeek.com/user/{}"},
    {"name": "Discogs", "url": "https://www.discogs.com/user/{}"},
    {"name": "RateYourMusic", "url": "https://rateyourmusic.com/~{}"},
    {"name": "MyFigureCollection", "url": "https://myfigurecollection.net/profile/{}"},
    {"name": "Untappd", "url": "https://untappd.com/user/{}"},
    {"name": "Vivino", "url": "https://www.vivino.com/users/{}"},
    
    # Fitness, Doğa ve Spor
    {"name": "Runkeeper", "url": "https://runkeeper.com/user/{}/profile"},
    {"name": "Bodybuilding.com", "url": "https://bodyspace.bodybuilding.com/{}"},
    {"name": "AllTrails", "url": "https://www.alltrails.com/members/{}"},
    {"name": "Komoot", "url": "https://www.komoot.com/user/{}"},
    
    # Haber, Aggregator & Genel
    {"name": "Digg", "url": "https://digg.com/@{}"},
    {"name": "Slashdot", "url": "https://slashdot.org/~{}"},
    {"name": "MetaFilter", "url": "https://www.metafilter.com/user/{}"},
    {"name": "Lobsters", "url": "https://lobste.rs/u/{}"},
    {"name": "Flipboard", "url": "https://flipboard.com/@{}"},
    {"name": "ProductHunt", "url": "https://www.producthunt.com/@{}"},
]


_ENTERTAINMENT_FORUM_PLATFORMS = [
    # Anime, manga, film ve dizi platformları
    {"name": "Anime-Planet", "url": "https://www.anime-planet.com/users/{}"},
    {
        "name": "Kitsu",
        "url": "https://kitsu.app/users/{}",
        "probe_url": "https://kitsu.io/api/edge/users?filter[name]={}",
        "check": "json_list",
        "accept": "application/vnd.api+json",
        "json_list_path": "data",
        "json_path": "attributes.name",
        "profile_id_path": "id",
        "profile_url": "https://kitsu.app/users/{}",
    },
    {
        "name": "Bangumi",
        "url": "https://bgm.tv/user/{}",
        "probe_url": "https://api.bgm.tv/v0/users/{}",
        "check": "json",
        "json_path": "username",
    },
    {"name": "Shikimori", "url": "https://shikimori.one/{}"},
    {"name": "MyDramaList", "url": "https://mydramalist.com/profile/{}"},
    {"name": "TMDB", "url": "https://www.themoviedb.org/u/{}"},
    {"name": "TasteDive", "url": "https://tastedive.com/users/{}"},
    {"name": "TV Tropes", "url": "https://tvtropes.org/pmwiki/pmwiki.php/Tropers/{}"},

    # Film/dizi ve Türkçe fantastik kültür forumları
    _discourse_platform("Trakt Forums", "https://forums.trakt.tv"),
    _discourse_platform("Kayıp Rıhtım Forum", "https://forum.kayiprihtim.com"),

    # Doğrulanabilir JSON kullanıcı profili sunan yabancı forumlar
    _discourse_platform("Discourse Meta", "https://meta.discourse.org"),
    _discourse_platform("Python Discuss", "https://discuss.python.org"),
    _discourse_platform("OpenAI Developer Community", "https://community.openai.com"),
    _discourse_platform("Mozilla Discourse", "https://discourse.mozilla.org"),
    _discourse_platform("Unreal Engine Forums", "https://forums.unrealengine.com"),
    _discourse_platform("Brave Community", "https://community.brave.com"),
    _discourse_platform("Elastic Discuss", "https://discuss.elastic.co"),
    _discourse_platform("Ubuntu Community Hub", "https://discourse.ubuntu.com"),
    _discourse_platform("Signal Community", "https://community.signalusers.org"),
    _discourse_platform("Obsidian Forum", "https://forum.obsidian.md"),
    _discourse_platform("Home Assistant Community", "https://community.home-assistant.io"),
    _discourse_platform("Hugging Face Forums", "https://discuss.huggingface.co"),
    _discourse_platform("PyTorch Forums", "https://discuss.pytorch.org"),
    _discourse_platform("Rust Users Forum", "https://users.rust-lang.org"),
    _discourse_platform("Jupyter Community", "https://discourse.jupyter.org"),
    _discourse_platform("Django Forum", "https://forum.djangoproject.com"),
    _discourse_platform("KDE Discuss", "https://discuss.kde.org"),
    _discourse_platform("Godot Forum", "https://forum.godotengine.org"),
    _discourse_platform("YazBel Forum", "https://forum.yazbel.com"),
    _discourse_platform("Pardus Forumları", "https://forum.pardus.org.tr"),
]

USERNAME_PLATFORMS.extend(_ENTERTAINMENT_FORUM_PLATFORMS)

_NEGATIVE_KEYWORDS = [
    "page not found", "not found", "doesn't exist", "does not exist",
    "could not be found", "page does not exist", "member not found",
    "this summoner is not registered", "no player found", "no user found",
    "no such user", "profile not found", "this account does not exist",
    "we couldn't find", "player not found", "user not found",
    "this page is not available", "sorry, the page you were looking for",
    "that page doesn't exist", "the user could not be found",
    "no results found", "oops! that page can",
    "looking for doesn't exist", "this summoner doesn't appear",
    "hasn't been played", "hmm, this page doesn", "unknown user",
    # Türkçe ve yaygın yabancı hata metinleri
    "kayitli degil", "bulunamadi", "boyle bir kullanici yok",
    "kullanici bulunamadi", "uye bulunamadi", "sayfa bulunamadi",
    "profil bulunamadi", "sayfa mevcut degil", "utilisateur introuvable",
    "usuario no encontrado", "benutzer nicht gefunden",
    "用户不存在", "用户不存在或已被删除",
]

_BLOCKED_KEYWORDS = [
    "just a moment", "attention required", "access denied",
    "enable javascript and cookies", "checking your browser",
    "verify you are human", "captcha",
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


def _check_json_response(
    username: str,
    platform: dict,
    response: httpx.Response,
    result: dict,
) -> dict:
    if response.status_code in {404, 410}:
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
    response: httpx.Response,
    result: dict,
) -> dict:
    if response.status_code in {404, 410}:
        return _set_result(result, "not_found", f"HTTP {response.status_code}")
    if response.status_code != 200:
        return _set_result(result, "unknown", f"HTTP {response.status_code}")

    visible_text = _visible_page_text(response.text)
    if _contains_block_marker(visible_text):
        return _set_result(result, "unknown", "Site otomatik taramayı engelledi")

    if _contains_negative_marker(visible_text):
        return _set_result(result, "not_found", "Bulunamadı işareti görüldü")

    if response.history and not _contains_exact_username(
        unquote(str(response.url)), username
    ):
        return _set_result(result, "not_found", "Genel sayfaya yönlendirildi")

    if _contains_exact_username(visible_text, username):
        return _set_result(result, "found", "Sayfada kullanıcı adı doğrulandı")

    return _set_result(result, "unknown", "Profil kanıtı bulunamadı")


async def check_single_username(username: str, platform: dict, client: httpx.AsyncClient) -> dict:
    """Bir platformda kullanıcı adını kanıta dayalı olarak doğrular."""
    encoded_username = quote(username.strip(), safe="._-~")
    url = platform["url"].format(encoded_username)
    probe_url = platform.get("probe_url", platform["url"]).format(encoded_username)
    method = platform.get("check", "html")
    result = {
        "platform": platform["name"],
        "url": url,
        "found": False,
        "status": "unknown",
        "detail": "",
    }

    try:
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
        return _check_html_response(username, response, result)
    except httpx.HTTPError as exc:
        return _set_result(result, "unknown", type(exc).__name__)


async def check_username_async(username: str) -> list[dict]:
    """Kullanıcı adını platformlara özel, kanıta dayalı yöntemlerle tarar."""
    username = username.strip()
    if not username:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    limits = httpx.Limits(max_connections=25, max_keepalive_connections=15)
    
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        task_id = progress.add_task(f"[cyan]Scanning: {username}...", total=len(USERNAME_PLATFORMS))
        
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
