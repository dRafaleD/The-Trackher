"""Bounded, site-specific public HTML state; never execute page scripts."""
from html.parser import HTMLParser
import json
from urllib.parse import parse_qsl, urlsplit


class _JsonScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.current = None
        self.blocked = 0
        self.total = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('noscript', 'template', 'footer', 'article'):
            self.blocked += 1
        if tag == 'script':
            attrs = dict(attrs)
            if not self.blocked and attrs.get('type') == 'application/json':
                if len(self.scripts) >= 64:
                    raise ValueError('Too many embedded profile scripts')
                self.current = {'attrs': attrs, 'parts': []}

    def handle_data(self, value):
        if self.current is not None:
            self.total += len(value)
            if self.total > 2_000_000:
                raise ValueError('Embedded profile data exceeds limit')
            self.current['parts'].append(value)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.current['text'] = ''.join(self.current.pop('parts'))
            self.scripts.append(self.current)
            self.current = None
        if tag in ('noscript', 'template', 'footer', 'article') and self.blocked:
            self.blocked -= 1


def _documents(body):
    parser = _JsonScripts()
    parser.feed(body)
    return parser.scripts


def _initial_routes(value):
    """Only active initial-route records, not error strings in shared assets."""
    stack = [(value, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if visited > 50_000 or depth > 40:
            raise ValueError('Embedded route traversal exceeds limit')
        if isinstance(item, dict):
            info = item.get('initialRouteInfo')
            if isinstance(info, dict) and isinstance(info.get('route'), dict):
                yield info['route']
            stack.extend((child, depth + 1) for key, child in item.items() if key != 'initialRouteInfo')
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _instagram_missing(documents, username):
    routes = []
    for document in documents:
        if 'data-sjs' not in document['attrs']:
            continue
        routes.extend(_initial_routes(json.loads(document['text'])))
    if len(routes) != 1:
        return False
    route = routes[0]
    if (route.get('url', '').casefold() != f'/{username}/'.casefold()
            or route.get('canonicalRouteName') != 'comet.igweb.PolarisErrorRoute'
            or route.get('tracePolicy') != 'polaris.httpErrorPage'
            or route.get('polarisRouteConfig', {}).get('pageID') != 'httpErrorPage'):
        return False
    for key in ('rootView', 'hostableView'):
        view = route.get(key, {})
        props = view.get('props', {})
        if (view.get('resource', {}).get('__dr') != 'PolarisErrorRoot.react'
                or props.get('page_type') != 'PROFILE'
                or props.get('show_lox_redesigned_404_page') is not True
                or 'restricted_age' not in props or props['restricted_age'] is not None
                or 'failure_reason' not in props or props['failure_reason'] is not None
                or props.get('page_logging', {}).get('name') != 'httpErrorPage'):
            return False
    return True


def _pinterest_missing(documents, username, expected_url):
    selected = {}
    for script_id in ('__PWS_DATA__', '__PWS_INITIAL_PROPS__'):
        found = [d for d in documents if d['attrs'].get('id') == script_id]
        if len(found) != 1:
            return False
        selected[script_id] = json.loads(found[0]['text'])
    data = selected['__PWS_DATA__']
    context = data.get('context', {})
    if (data.get('initialHandlerId') != 'www/[username].js'
            or context.get('current_url', '').rstrip('/').casefold() != expected_url.rstrip('/').casefold()
            or context.get('path', '').casefold() != f'/{username}/'.casefold()
            or context.get('is_authenticated') is not False):
        return False
    resources = selected['__PWS_INITIAL_PROPS__'].get('initialReduxState', {}).get('resources', {}).get('UserResource', {})
    if not isinstance(resources, dict) or len(resources) > 100:
        return False
    matches = []
    for key, row in resources.items():
        options = json.loads(key)
        if not isinstance(options, list) or not all(isinstance(p, list) and len(p) == 2 for p in options):
            continue
        pairs = dict(options)
        if str(pairs.get('username', '')).casefold() == username.casefold() and pairs.get('field_set_key') == 'unauth_profile':
            matches.append(row)
    if len(matches) != 1:
        return False
    row = matches[0]
    error = row.get('error', {})
    if row.get('fetching') is not False or 'data' not in row or row['data'] is not None or type(error.get('httpStatus')) is not int or error['httpStatus'] != 404:
        return False
    message = error.get('message', '')
    if not isinstance(message, str) or not message.startswith('404 - '):
        return False
    detail = message[6:]
    for _ in range(3):
        if not isinstance(detail, str):
            break
        detail = json.loads(detail)
    return (isinstance(detail, dict) and detail.get('status') == 'failure'
            and type(detail.get('code')) is int and detail['code'] == 30
            and detail.get('message') == 'User not found.'
            and detail.get('endpoint_name') == 'v3_get_user_handler'
            and 'data' in detail and detail['data'] is None)


def missing_profile_state(body, username, profile_format, expected_url):
    try:
        documents = _documents(body)
        if profile_format == 'instagram_state' and _instagram_missing(documents, username):
            return 'Instagram active profile route reports a profile-specific 404'
        if profile_format == 'pinterest_state' and _pinterest_missing(documents, username, expected_url):
            return 'Pinterest requested UserResource reports user-not-found (code 30)'
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        pass
    return None


def evaluate_hackernews(username, response):
    """The API may omit inactive users; independently verify the public page."""
    from osint.profile_evidence import ProfileDocument
    url = urlsplit(str(response.url))
    if url.scheme != 'https' or url.netloc != 'news.ycombinator.com' or url.path != '/user' or parse_qsl(url.query) != [('id', username)]:
        return 'unknown', 'HackerNews profile redirected away from the requested identity', 'redirect_changed'
    if response.status_code in (200, 404) and response.text.strip() == 'No such user.':
        return 'not_found', 'HackerNews public profile explicitly reports no such user', 'soft_404'
    if response.status_code != 200:
        cause = 'rate_limited' if response.status_code == 429 else 'forbidden' if response.status_code in (401, 403) else 'unexpected_status'
        return 'unknown', f'HackerNews profile HTTP {response.status_code}', cause
    if len(response.text) > 500_000:
        return 'unknown', 'HackerNews profile exceeds parser limit', 'parser_mismatch'
    doc = ProfileDocument()
    doc.feed(response.text)
    titles = ' '.join(n['text'] for n in doc.nodes if n['tag'] == 'title').casefold()
    if any(marker in titles for marker in ('just a moment', 'client challenge', 'access denied', 'attention required')):
        return 'unknown', 'HackerNews returned a browser challenge', 'bot_blocked'
    canonical = f'https://news.ycombinator.com/user?id={username}'
    title = f'Profile: {username} | Hacker News'
    matches = [
        any(n['tag'] == 'link' and n['attrs'].get('rel') == 'canonical' and n['attrs'].get('href') == canonical for n in doc.nodes),
        any(n['tag'] == 'title' and n['text'].strip() == title for n in doc.nodes),
        any(n['tag'] == 'a' and 'hnuser' in str(n['attrs'].get('class', '')).split() and n['attrs'].get('href') == f'user?id={username}' for n in doc.nodes),
    ]
    if all(matches):
        return 'found', 'HackerNews canonical URL, profile title and user link agree exactly', None
    return 'unknown', 'HackerNews public profile identity could not be verified', 'parser_mismatch'
