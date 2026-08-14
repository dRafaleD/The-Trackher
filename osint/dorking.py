import urllib.parse

from osint.username_checker import USERNAME_PLATFORMS

DORK_TEMPLATES = [
    {"engine": "Google", "type": "Genel Arama", "url": "https://www.google.com/search?q={}"},
    {"engine": "Google", "type": "Tırnak İçi Arama", "url": "https://www.google.com/search?q=\"{}\""},
    {"engine": "Google", "type": "Dosya Arama (PDF, DOC)", "url": "https://www.google.com/search?q={}+filetype:pdf+OR+filetype:doc+OR+filetype:txt"},
    {"engine": "Google", "type": "Sosyal Medya Arama", "url": "https://www.google.com/search?q={}+site:instagram.com+OR+site:twitter.com+OR+site:facebook.com"},
    {"engine": "Google", "type": "Kod Depoları (GitHub, GitLab)", "url": "https://www.google.com/search?q={}+site:github.com+OR+site:gitlab.com+OR+site:bitbucket.org"},
    {"engine": "Bing", "type": "Genel Arama", "url": "https://www.bing.com/search?q={}"},
    {"engine": "DuckDuckGo", "type": "Genel Arama", "url": "https://duckduckgo.com/?q={}"},
    {"engine": "Yandex", "type": "Genel Arama", "url": "https://yandex.com/search/?text={}"}
]

PLATFORM_DORK_CHUNK_SIZE = 12

PRIORITY_EMAIL_TRACE_DOMAINS = [
    # Eğitim, kurs, sertifika ve öğrenme abonelikleri
    "sorbil.org",
    "udemy.com",
    "coursera.org",
    "edx.org",
    "khanacademy.org",
    "skillshare.com",
    "linkedin.com",
    "pluralsight.com",
    "codecademy.com",
    "datacamp.com",
    "brilliant.org",
    "masterclass.com",
    "domestika.org",
    "futurelearn.com",
    "udacity.com",
    "freecodecamp.org",
    "educative.io",
    "memrise.com",
    "duolingo.com",
    "busuu.com",
    "babbel.com",
    "alison.com",
    "openlearning.com",
    "classcentral.com",
    "maven.com",
    "teachable.com",
    "kajabi.com",
    "btkakademi.gov.tr",
    "turkcellakademi.com",
    "bilgeis.net",
    "istanbulisletmeenstitusu.com",
    "enstitu.istanbul",
    "universiteplus.com",
    # İçerik, medya, üretkenlik ve üyelik/abonelik servisleri
    "netflix.com",
    "disneyplus.com",
    "primevideo.com",
    "spotify.com",
    "youtube.com",
    "blutv.com",
    "exxen.com",
    "todtv.com.tr",
    "gain.tv",
    "mubi.com",
    "puhutv.com",
    "storytel.com",
    "scribd.com",
    "everand.com",
    "audible.com",
    "canva.com",
    "notion.so",
    "figma.com",
    "adobe.com",
    "dropbox.com",
    "zoom.us",
    "grammarly.com",
    "quillbot.com",
    "medium.com",
    "substack.com",
    "patreon.com",
]


def _looks_like_email(target: str) -> bool:
    return "@" in target and "." in target.rsplit("@", 1)[-1]


def _platform_domain(platform: dict) -> str | None:
    try:
        rendered_url = platform["url"].format("probe")
    except (KeyError, IndexError, ValueError):
        return None

    host = urllib.parse.urlparse(rendered_url).netloc.lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("probe."):
        host = host[6:]
    return host


def get_username_platform_domains() -> list[str]:
    """Kullanıcı adı platformlarından benzersiz arama domainleri çıkarır."""
    seen: set[str] = set()
    domains: list[str] = []
    for platform in USERNAME_PLATFORMS:
        domain = _platform_domain(platform)
        if domain and domain not in seen:
            domains.append(domain)
            seen.add(domain)
    return domains


def get_priority_email_trace_domains() -> list[str]:
    """E-posta izi için öncelikli eğitim ve abonelik domainlerini döndürür."""
    seen: set[str] = set()
    domains: list[str] = []
    for domain in PRIORITY_EMAIL_TRACE_DOMAINS:
        normalized = domain.lower().removeprefix("www.")
        if normalized and normalized not in seen:
            domains.append(normalized)
            seen.add(normalized)
    return domains


def get_email_trace_domains() -> list[str]:
    """E-posta dork'larında aranacak tüm domainleri tek havuzda toplar."""
    seen: set[str] = set()
    domains: list[str] = []
    for domain in get_priority_email_trace_domains() + get_username_platform_domains():
        if domain not in seen:
            domains.append(domain)
            seen.add(domain)
    return domains


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _email_platform_dorks(target: str) -> list[dict]:
    encoded_target = urllib.parse.quote_plus(f'"{target}"')
    dorks = []

    for index, domains in enumerate(
        _chunks(get_email_trace_domains(), PLATFORM_DORK_CHUNK_SIZE),
        start=1,
    ):
        site_query = "+OR+".join(f"site:{domain}" for domain in domains)
        dorks.append({
            "engine": "Google",
            "type": f"Eğitim/Abonelik + Platform Arama #{index}",
            "url": f"https://www.google.com/search?q={encoded_target}+{site_query}",
        })

    return dorks

def generate_dorks(target: str) -> list[dict]:
    """Hedef (email veya username) için dork URL'leri üretir."""
    encoded_target = urllib.parse.quote_plus(target)
    results = []
    
    for template in DORK_TEMPLATES:
        url = template["url"].format(encoded_target)
        results.append({
            "engine": template["engine"],
            "type": template["type"],
            "url": url
        })

    if _looks_like_email(target):
        results.extend(_email_platform_dorks(target))
        
    return results
