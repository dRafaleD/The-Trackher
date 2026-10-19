"""Structured public-profile evidence; no username-in-body heuristics."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import parse_qsl, quote, urlsplit
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
        if tag in ('script', 'style', 'noscript', 'template'):
            self.ignored += 1
        if self.ignored:
            return
        node = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
        node['auxiliary'] = (any(parent.get('auxiliary') for parent in self.stack)
                             or tag in ('footer', 'article')
                             or bool(re.search(r'(?:^|[\s_-])(?:comments?|replies|feed)(?:$|[\s_-])', str(node['attrs'].get('class', ''))[:256], re.I)))
        self.nodes.append(node)
        if tag not in ('meta', 'link', 'img', 'input', 'br', 'hr', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'col'):
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignored:
            if tag in ('script', 'style', 'noscript', 'template'):
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
            if node.get('auxiliary'):
                continue
            if node['tag'] != rule['tag']:
                continue
            attrs = node['attrs']
            if rule.get('class') not in (None, *str(attrs.get('class', '')).split()):
                continue
            expected = {k: v.replace('{username}', username) for k, v in rule.get('attrs', {}).items()}
            if any(_text(str(attrs.get(k, ''))) != _text(v) for k, v in expected.items()):
                continue
            if any(
                not any(_text(str(attrs.get(key, ''))) == _text(value.replace('{username}', username))
                        for value in alternatives)
                for key, alternatives in rule.get('attrs_any', {}).items()
            ):
                continue
            if 'text' in rule and _text(node['text']) != _text(rule['text'].replace('{username}', username)):
                continue
            if 'text_suffix' in rule and not _text(node['text']).endswith(_text(rule['text_suffix'].replace('{username}', username))):
                continue
            if 'text_suffix_any' in rule and not any(
                _text(node['text']).endswith(_text(suffix.replace('{username}', username)))
                for suffix in rule['text_suffix_any']
            ):
                continue
            if 'text_prefix' in rule and not _text(node['text']).startswith(_text(rule['text_prefix'].replace('{username}', username))):
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
    osu_numeric_profile = (platform.get('profile_format') == 'osu_profile'
                           and re.fullmatch(r'/users/[1-9][0-9]*', actual.path.rstrip('/')))
    patreon_profile = (platform.get('profile_format') == 'patreon_profile'
                       and actual.path.rstrip('/').casefold() in {
                           '/' + username.casefold(), '/c/' + username.casefold(), '/cw/' + username.casefold()})
    allowed_hosts = [host.replace('{username}', username).casefold() for host in platform['profile_allowed_hosts']]
    if (actual.scheme not in ('http', 'https')
            or actual.hostname not in allowed_hosts
            or (actual.path.rstrip('/').casefold() != expected.path.rstrip('/').casefold()
                and not osu_numeric_profile and not patreon_profile)
            or (expected.query and sorted(parse_qsl(actual.query)) != sorted(parse_qsl(expected.query)))):
        return unknown('Profile redirected away from its configured address', 'redirect_changed')
    body = response.text
    # Captured YouTube channel HTML exceeds 2 MB due to inline page data.
    # Keep a finite, site-specific ceiling; other formats retain their limit.
    max_chars = 3_000_000 if platform.get('profile_format') == 'youtube_channel' else 2_000_000
    if len(body) > max_chars:
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
    if platform.get('profile_format') == 'patreon_profile':
        # The current route, canonical and OG URL must describe the same page.
        profile_url = 'https://' + actual.netloc + actual.path.rstrip('/')
        if not all(doc.matches(rule, username) for rule in (
                {'tag': 'link', 'attrs': {'rel': 'canonical', 'href': profile_url}},
                {'tag': 'meta', 'attrs': {'property': 'og:url', 'content': profile_url}})):
            return unknown('Patreon profile route metadata did not agree')
    missing_rules = platform.get('profile_missing_evidence', [])
    if missing_rules and all(doc.matches(rule, username) for rule in missing_rules):
        return ('not_found', 'Site-specific missing-profile evidence verified', 'soft_404')
    if platform.get('profile_format') in ('instagram_state', 'pinterest_state'):
        from osint.embedded_profiles import missing_profile_state
        detail = missing_profile_state(body, username, platform['profile_format'], str(response.url))
        if detail:
            rules = platform.get('profile_evidence', [])
            if rules and all(doc.matches(rule, username) for rule in rules):
                return unknown('Conflicting profile and missing-profile evidence')
            return ('not_found', detail, 'soft_404')
    if platform.get('profile_format') == 'osu_profile':
        # A username may redirect to a numeric user ID. Both URL metadata fields
        # must bind that ID; configured rules still require the requested name.
        if not osu_numeric_profile:
            return unknown('osu! numeric profile address could not be verified')
        profile_url = 'https://osu.ppy.sh' + actual.path.rstrip('/')
        if not all(doc.matches(rule, username) for rule in (
                {'tag': 'link', 'attrs': {'rel': 'canonical', 'href': profile_url}},
                {'tag': 'meta', 'attrs': {'property': 'og:url', 'content': profile_url}})):
            return unknown('osu! profile ID metadata does not match its address')
    if platform.get('profile_format') == 'youtube_channel':
        # Handles use channel-ID canonical URLs. Pin the ID format and require
        # exact agreement between canonical and Open Graph, in addition to the
        # requested handle's alternate mobile link in the configured rules.
        canonicals = [n['attrs'].get('href', '') for n in doc.nodes
                      if n['tag'] == 'link' and n['attrs'].get('rel') == 'canonical']
        if len(canonicals) != 1 or not re.fullmatch(
                r'https://www\.youtube\.com/channel/UC[A-Za-z0-9_-]{22}', canonicals[0]):
            return unknown('YouTube channel identifier could not be verified')
        if not any(n['tag'] == 'meta' and n['attrs'].get('property') == 'og:url'
                   and n['attrs'].get('content') == canonicals[0] for n in doc.nodes):
            return unknown('YouTube channel metadata disagrees with its canonical ID')
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
        response.extensions['trackher_profile_document'] = doc
        return ('found', 'Site-specific structured profile evidence verified', None)
    return unknown('No verified site-specific profile evidence')
