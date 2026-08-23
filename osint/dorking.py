import urllib.parse

USERNAME_DORK_TEMPLATES = [
    {"engine": "Google", "type": "General Search", "url": "https://www.google.com/search?q={}"},
    {"engine": "Google", "type": "Exact Phrase Search", "url": "https://www.google.com/search?q=\"{}\""},
    {"engine": "Google", "type": "File Search (PDF, DOC)", "url": "https://www.google.com/search?q={}+filetype:pdf+OR+filetype:doc+OR+filetype:txt"},
    {"engine": "Google", "type": "Social Media Search", "url": "https://www.google.com/search?q={}+site:instagram.com+OR+site:twitter.com+OR+site:facebook.com"},
    {"engine": "Google", "type": "Kod Depolari (GitHub, GitLab)", "url": "https://www.google.com/search?q={}+site:github.com+OR+site:gitlab.com+OR+site:bitbucket.org"},
    {"engine": "Bing", "type": "General Search", "url": "https://www.bing.com/search?q={}"},
    {"engine": "DuckDuckGo", "type": "General Search", "url": "https://duckduckgo.com/?q={}"},
    {"engine": "Yandex", "type": "General Search", "url": "https://yandex.com/search/?text={}"}
]

EMAIL_DORK_TEMPLATES = [
    {"engine": "Google", "type": "Exact Email Search", "url": "https://www.google.com/search?q=\"{}\""},
    {"engine": "Google", "type": "Data Leak / Paste", "url": "https://www.google.com/search?q=\"{}\"+site:pastebin.com+OR+site:ghostbin.com+OR+site:hastebin.com"},
    {"engine": "Google", "type": "Kod Depolari", "url": "https://www.google.com/search?q=\"{}\"+site:github.com+OR+site:gitlab.com+OR+site:bitbucket.org"},
    {"engine": "Google", "type": "Dokumanlar", "url": "https://www.google.com/search?q=\"{}\"+filetype:pdf+OR+filetype:doc+OR+filetype:xls+OR+filetype:txt"},
    {"engine": "Google", "type": "Forum ve Topluluklar", "url": "https://www.google.com/search?q=\"{}\"+site:reddit.com+OR+site:medium.com+OR+site:quora.com"},
    {"engine": "Bing", "type": "Exact Email Search", "url": "https://www.bing.com/search?q=\"{}\""},
    {"engine": "DuckDuckGo", "type": "Exact Email Search", "url": "https://duckduckgo.com/?q=\"{}\""},
    {"engine": "Yandex", "type": "Exact Email Search", "url": "https://yandex.com/search/?text=\"{}\""},
]


def _looks_like_email(target: str) -> bool:
    return "@" in target and "." in target.rsplit("@", 1)[-1]


def generate_dorks(target: str) -> list[dict]:
    """Hedef kullanici adi veya e-posta icin dork URL'leri uretir."""
    encoded_target = urllib.parse.quote_plus(target)
    results = []
    templates = EMAIL_DORK_TEMPLATES if _looks_like_email(target) else USERNAME_DORK_TEMPLATES

    for template in templates:
        results.append(
            {
                "engine": template["engine"],
                "type": template["type"],
                "url": template["url"].format(encoded_target),
            }
        )

    return results
