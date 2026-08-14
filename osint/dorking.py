import urllib.parse
from utils.display import console

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
        
    return results
