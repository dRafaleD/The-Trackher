from __future__ import annotations
import asyncio
import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from utils.display import console

# Detection method per platform:
# check="404" means: if HTTP response is 404 -> not found (most reliable)
# check="content" means: 200 for both cases -> must scan body for negative keywords
# check="redirect" means: non-existent users get redirected elsewhere

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

USERNAME_PLATFORMS = [
    # --- Core Global Social Media ---
    {"name": "GitHub", "url": "https://github.com/{}", "check": "404"},
    {"name": "Twitter/X", "url": "https://twitter.com/{}", "check": "content"},
    {"name": "Instagram", "url": "https://www.instagram.com/{}/", "check": "content"},
    {"name": "TikTok", "url": "https://www.tiktok.com/@{}", "check": "content"},
    {"name": "Pinterest", "url": "https://www.pinterest.com/{}/", "check": "404"},
    {"name": "Reddit", "url": "https://www.reddit.com/user/{}/about.json", "check": "404"},
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
    {"name": "StackOverflow", "url": "https://stackoverflow.com/users/{}"},
    {"name": "HackerNews", "url": "https://news.ycombinator.com/user?id={}"},
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
    {"name": "XDA Developers", "url": "https://forum.xda-developers.com/m/{}"},
    
    # Oyun (Gaming)
    {"name": "Steam", "url": "https://steamcommunity.com/id/{}"},
    {"name": "Roblox", "url": "https://www.roblox.com/user.aspx?username={}"},
    {"name": "Xbox", "url": "https://xboxgamertag.com/search/{}"},
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
    {"name": "Goodreads", "url": "https://www.goodreads.com/user/show/{}"},
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
    {"name": "Badoo", "url": "https://badoo.com/profile/{}"},
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
    {"name": "CHIP Online", "url": "https://www.chip.com.tr/forum/member.php?u={}"},
    {"name": "Paticik", "url": "https://forum.paticik.com/profile/{}/"},
    
    # Yazılım, IT ve Hacker Forumları
    {"name": "Ubuntu Forums", "url": "https://ubuntuforums.org/member.php?u={}"},
    {"name": "LinuxQuestions", "url": "https://www.linuxquestions.org/questions/user/{}-1/"},
    {"name": "Raspberry Pi", "url": "https://forums.raspberrypi.com/memberlist.php?mode=viewprofile&un={}"},
    {"name": "Arduino Forum", "url": "https://forum.arduino.cc/u/{}/summary"},
    {"name": "StackExchange", "url": "https://stackexchange.com/users/{}"},
    {"name": "SuperUser", "url": "https://superuser.com/users/{}"},
    {"name": "ServerFault", "url": "https://serverfault.com/users/{}"},
    {"name": "AskUbuntu", "url": "https://askubuntu.com/users/{}"},
    {"name": "Codeforces", "url": "https://codeforces.com/profile/{}"},
    {"name": "TopCoder", "url": "https://www.topcoder.com/members/{}"},
    {"name": "CodeChef", "url": "https://www.codechef.com/users/{}"},
    {"name": "Hashnode", "url": "https://hashnode.com/@{}"},
    {"name": "SourceHut", "url": "https://sr.ht/~{}/"},
    {"name": "BlackHatWorld", "url": "https://www.blackhatworld.com/members/{}/"},
    {"name": "HackForums", "url": "https://hackforums.net/member.php?action=profile&uid={}"},
    
    # Kripto, Finans ve Ticaret
    {"name": "BitcoinTalk", "url": "https://bitcointalk.org/index.php?action=profile;u={}"},
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
    {"name": "NexusMods", "url": "https://www.nexusmods.com/users/{}"},
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
    {"name": "GBAtemp", "url": "https://gbatemp.net/members/?username={}"},
    {"name": "Se7enSins", "url": "https://www.se7ensins.com/members/?username={}"},
    {"name": "GOG Forum", "url": "https://www.gog.com/forum/user/{}"},
    {"name": "SteamREP", "url": "https://steamrep.com/search?q={}"},
    
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
    {"name": "FanFiction", "url": "https://www.fanfiction.net/u/{}/"},
    {"name": "ArchiveOfOurOwn", "url": "https://archiveofourown.org/users/{}/profile"},
    {"name": "RoyalRoad", "url": "https://www.royalroad.com/profile/{}"},
    {"name": "Letterboxd", "url": "https://letterboxd.com/{}/"},
    {"name": "Trakt", "url": "https://trakt.tv/users/{}"},
    {"name": "TV Time", "url": "https://www.tvtime.com/en/user/{}"},
    {"name": "BoardGameGeek", "url": "https://boardgamegeek.com/user/{}"},
    {"name": "Discogs", "url": "https://www.discogs.com/user/{}"},
    {"name": "RateYourMusic", "url": "https://rateyourmusic.com/~{}"},
    {"name": "MyFigureCollection", "url": "https://myfigurecollection.net/profile/{}"},
    {"name": "Untappd", "url": "https://untappd.com/user/{}"},
    {"name": "Vivino", "url": "https://www.vivino.com/users/{}"},
    
    # Fitness, Doğa ve Spor
    {"name": "Strava", "url": "https://www.strava.com/athletes/{}"},
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

# ------------------------------------------------------------------
# Negative keywords for "content" mode - false positive prevention
# ------------------------------------------------------------------
_NEGATIVE_KEYWORDS = [
    "page not found", "doesn't exist", "could not be found",
    "this summoner is not registered", "no player found", "no user found",
    "no such user", "profile not found", "this account does not exist",
    "we couldn't find", "player not found", "user not found",
    "this page is not available", "sorry, the page you were looking for",
    "that page doesn't exist", "the user could not be found",
    "no results found", "oops! that page can",
    "looking for doesn't exist", "this summoner doesn't appear",
    "hasn't been played", "hmm, this page doesn",
    # Turkish negative keywords
    "kayitli degil", "bulunamadi", "boyle bir kullanici yok",
    "kullanici bulunamadi", "sayfa bulunamadi",
    # Hacker News API special case: null response = not found
    "null",
]


async def check_single_username(username: str, platform: dict, client: httpx.AsyncClient) -> dict:
    """Check a single platform with the correct detection strategy."""
    url = platform["url"].format(username)
    method = platform.get("check", "404")
    result = {"platform": platform["name"], "url": url, "found": False}
    try:
        resp = await client.get(url, follow_redirects=True)

        if method == "404":
            # Reliable: site returns 404 when user does not exist
            result["found"] = resp.status_code == 200

        elif method == "content":
            # Unreliable: site returns 200 even when user is missing
            # So we ONLY mark found if 200 AND no negative keywords present
            if resp.status_code == 200:
                body = resp.text.lower()
                result["found"] = not any(kw in body for kw in _NEGATIVE_KEYWORDS)

    except Exception:
        pass  # Network error / timeout -> default False
    return result

async def check_username_async(username: str) -> list[dict]:
    """Main async scan - uses rotating browser headers and per-platform detection."""
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
                status = "[green]FOUND[/green]" if res["found"] else "[dim]---[/dim]"
                progress.update(task_id, advance=1, description=f"{status} {res['platform']}")
                
    return results


def run_username_check(username: str) -> list[dict]:
    return asyncio.run(check_username_async(username))
