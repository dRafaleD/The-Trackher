"""Structured public-profile evidence; no username-in-body heuristics."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree


def _text(value):
    return unicodedata.normalize('NFC', ' '.join(value.split())).casefold()


class ProfileDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.ignored += 1
        if self.ignored:
            return
        node = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
        self.nodes.append(node)
        if tag not in ('meta', 'link', 'img', 'input', 'br', 'hr', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'col'):
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignored:
            if tag in ('script', 'style', 'noscript'):
                self.ignored -= 1
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.ignored:
            # Only profile-relevant text containers, not every ancestor.
            for node in self.stack:
                if node['tag'] in ('title', 'h1', 'h2', 'div', 'span'):
                    node['text'] += data

    def matches(self, rule, username):
        for node in self.nodes:
            if node['tag'] != rule['tag']:
                continue
            attrs = node['attrs']
            if rule.get('class') not in (None, *str(attrs.get('class', '')).split()):
                continue
            expected = {k: v.replace('{username}', username) for k, v in rule.get('attrs', {}).items()}
            if any(_text(str(attrs.get(k, ''))) != _text(v) for k, v in expected.items()):
                continue
            if 'text' in rule and _text(node['text']) != _text(rule['text'].replace('{username}', username)):
                continue
            if rule.get('nonempty') and not node['text'].strip():
                continue
            return True
        return False


def evaluate_profile(username, platform, response):
    """Return (status, explanation, diagnostic cause) for opted-in sites."""
    unknown = lambda detail, cause='parser_mismatch': ('unknown', detail, cause)
    if response.status_code == 429:
        return unknown('Site rate limited the request', 'rate_limited')
    expected = urlsplit(platform.get('probe_url', platform['url']).format(quote(username.strip(), safe='._-~')))
    actual = urlsplit(str(response.url))
    if actual.hostname not in platform['profile_allowed_hosts'] or actual.path.rstrip('/').casefold() != expected.path.rstrip('/').casefold():
        return unknown('Profile redirected away from its configured address', 'redirect_changed')
    body = response.text
    if len(body) > 2_000_000:
        return unknown('Profile response exceeds parser size limit')
    doc = ProfileDocument()
    doc.feed(body)
    titles = ' '.join(n['text'] for n in doc.nodes if n['tag'] == 'title').casefold()
    if any(marker in titles for marker in ('just a moment', 'client challenge', 'access denied', 'attention required')):
        return unknown('Browser challenge instead of a profile', 'bot_blocked')
    if response.status_code in platform.get('profile_not_found_statuses', []):
        return ('not_found', f'Profile HTTP {response.status_code}', 'soft_404')
    if response.status_code != 200:
        return unknown(f'HTTP {response.status_code}', 'unexpected_status')
    if platform.get('profile_format') == 'steam_xml':
        if '<!doctype' in body.casefold() or '<!entity' in body.casefold():
            return unknown('Unsupported XML document declaration')
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            return unknown('Invalid Steam profile XML')
        if root.tag == 'response' and root.findtext('error') == 'The specified profile could not be found.':
            return ('not_found', 'Steam missing-profile XML error', 'soft_404')
        steam_id = root.findtext('steamID64', '')
        if root.tag == 'profile' and re.fullmatch(r'\d{17}', steam_id) and _text(root.findtext('customURL', '')) == _text(username):
            return ('found', 'Steam ID and requested vanity URL verified', None)
        return unknown('Steam profile identity could not be verified')
    rules = platform.get('profile_evidence', [])
    if rules and all(doc.matches(rule, username) for rule in rules):
        return ('found', 'Site-specific structured profile evidence verified', None)
    return unknown('No verified site-specific profile evidence')
