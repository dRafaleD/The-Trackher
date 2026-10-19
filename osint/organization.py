"""Bounded public homepage references and passive brand certificate candidates."""
import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx

from osint.domain_research import normalize_domain
from utils.public_data import public_url

TOTAL_TIMEOUT = 25
MAX_BODY = 2_000_000
LIMITATIONS = 'Published references do not prove ownership; certificate similarity does not prove impersonation.'


def _row(domain, platform, url, status='unknown', **metadata):
    return {'platform': platform, 'queried_username': domain, 'url': url,
            'status': status, 'found': status == 'found',
            'detail': metadata.get('detail', ''),
            'public_metadata': {'limitations': LIMITATIONS, **metadata},
            'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            'evidence_type': 'published_reference' if platform == 'Organization footprint' else 'certificate_candidate'}


def _unknown(domain, platform, url, cause, detail):
    row = _row(domain, platform, url, detail=detail)
    row['detail'] = detail
    row['unknown_cause'] = cause
    return [row]


class _ResponseTooLarge(ValueError):
    pass


async def _bounded_get(client, url, **kwargs):
    if isinstance(client, httpx.AsyncClient):
        async with client.stream('GET', url, **kwargs) as response:
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BODY:
                    raise _ResponseTooLarge('Response size limit exceeded')
                chunks.append(chunk)
            headers = {key: value for key, value in response.headers.items() if key not in {'content-encoding', 'content-length'}}
            return httpx.Response(response.status_code, headers=headers,
                                  content=b''.join(chunks), request=response.request)
    # Scheduler wrappers expose get only; own default clients always stream.
    response = await client.get(url, **kwargs)
    if len(response.content) > MAX_BODY:
        raise _ResponseTooLarge('Response size limit exceeded')
    return response


async def _public_addresses(domain):
    records = await asyncio.get_running_loop().getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    addresses = {item[4][0] for item in records}
    if not addresses or not all(ipaddress.ip_address(value).is_global for value in addresses):
        return ''
    return sorted(addresses, key=lambda value: (':' in value, value))[0]


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.nodes = 0
        self.title = []

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 10000 or len(self.stack) > 256:
            raise ValueError('HTML complexity limit exceeded')
        attrs = dict(attrs)
        hidden = (tag in {'script', 'style', 'noscript', 'template'} or 'hidden' in attrs
                  or attrs.get('aria-hidden', '').lower() == 'true'
                  or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', attrs.get('style', ''), re.I)))
        excluded = hidden or any(value for _, value in self.stack)
        if tag == 'a' and not excluded and len(self.links) < 300:
            self.links.append(attrs.get('href', ''))
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, excluded))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if any(tag == 'title' for tag, _ in self.stack) and len(self.title) < 20:
            self.title.append(data[:200])


def _catalog_patterns():
    entries = json.loads(Path(__file__).with_name('platforms.json').read_text(encoding='utf-8'))
    result = []
    for entry in entries:
        template = entry.get('url_pattern', '')
        if '{username}' in template:
            result.append((entry['name'], re.compile('^' + re.escape(template.rstrip('/')).replace(re.escape('{username}'), r'[^/?#]{1,100}') + '/?$', re.I)))
    return result


def _certificate_time(value):
    """crt.sh log entry timestamps are UTC, distinct from certificate validity."""
    if not isinstance(value, str) or len(value) > 80:
        return ''
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return ''


async def research_organization(domain, client=None):
    domain = normalize_domain(domain)
    url = 'https://' + domain + '/'
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as raw:
            return await research_organization(domain, raw)

    async def run():
        current_url = url
        root = domain.removeprefix('www.')
        visited = set()
        for hop in range(3):
            parsed = urlsplit(current_url)
            host = parsed.hostname
            address = await _public_addresses(host)
            if not address:
                return _unknown(domain, 'Organization footprint', current_url, 'unsafe_target', 'Domain resolves to a non-public address.')
            # Pin every validated hop. TLS verifies its original host via SNI.
            authority = '[' + address + ']' if ':' in address else address
            pinned = urlunsplit(('https', authority, parsed.path or '/', parsed.query, ''))
            response = await _bounded_get(client, pinned, follow_redirects=False,
                                        headers={'Host': host}, extensions={'sni_hostname': host})
            visited.add(current_url)
            if not response.is_redirect:
                break
            target = public_url(urljoin(current_url, response.headers.get('location', '')))
            destination = urlsplit(target)
            if (not target or destination.scheme != 'https' or destination.port not in (None, 443)
                    or destination.hostname not in {domain, root, 'www.' + root}
                    or target in visited or hop == 2):
                return _unknown(domain, 'Organization footprint', current_url, 'redirect_changed',
                                f'HTTP {response.status_code}; redirect is outside the permitted HTTPS host pair, loops, or exceeds two hops.')
            current_url = target
        if response.status_code != 200:
            return _unknown(domain, 'Organization footprint', url, 'redirect_changed' if response.is_redirect else 'rate_limited' if response.status_code == 429 else 'blocked' if response.status_code in (401, 403) else 'http_error', f'HTTP {response.status_code}; no links inferred.')
        if len(response.content) > MAX_BODY or ('text/html' not in response.headers.get('content-type', 'text/html').lower()):
            return _unknown(domain, 'Organization footprint', url, 'parser_mismatch', 'Response is too large or not HTML.')
        parser = _Anchors()
        parser.feed(response.text)
        title = ' '.join(' '.join(parser.title).lower().split())
        if re.match(r'^(?:just a moment|access denied|attention required|client challenge)(?:\W|$)', title):
            return _unknown(domain, 'Organization footprint', current_url, 'bot_blocked', 'Browser challenge or access-denied page; no organization references inferred.')
        patterns = _catalog_patterns()
        rows, seen = [], set()
        for raw in parser.links:
            link = public_url(urljoin(current_url, raw))
            if not link or link in seen:
                continue
            host = (urlsplit(link).hostname or '').removeprefix('www.')
            if host == root or host.endswith('.' + root):
                continue
            seen.add(link)
            platform = next((name for name, pattern in patterns if pattern.fullmatch(link)), '')
            rows.append(_row(domain, 'Organization footprint', link, 'found', source_url=current_url,
                             detail='Public homepage contains an outgoing reference; ownership is unverified.',
                             public_links=[link], relationship='published_reference', ownership_verified=False,
                             category='catalog_profile' if platform else 'external_domain', linked_platform=platform,
                             linked_domain=host))
            if len(rows) >= 30:
                break
        return rows or [_row(domain, 'Organization footprint', current_url, 'not_found', source_url=current_url, detail='No eligible outgoing links observed on this homepage; other pages were not checked.')]

    try:
        return await asyncio.wait_for(run(), TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        return _unknown(domain, 'Organization footprint', url, 'timeout', 'Research time budget exhausted.')
    except _ResponseTooLarge:
        return _unknown(domain, 'Organization footprint', url, 'parser_mismatch', 'Response size limit exceeded.')
    except httpx.TimeoutException:
        return _unknown(domain, 'Organization footprint', url, 'timeout', 'Homepage request timed out.')
    except httpx.TimeoutException:
        return _unknown(domain, 'Organization footprint', url, 'timeout', 'Homepage request timed out.')
    except (httpx.HTTPError, OSError):
        return _unknown(domain, 'Organization footprint', url, 'network_error', 'Homepage unavailable.')
    except ValueError:
        return _unknown(domain, 'Organization footprint', url, 'parser_mismatch', 'Homepage response is invalid or exceeds HTML complexity limits.')


async def research_brand(domain, client=None):
    domain = normalize_domain(domain)
    # Only a conservative second-level stem; ambiguous public-suffix names are rejected.
    labels = domain.split('.')
    stem = labels[-2]
    if len(labels) >= 3 and labels[-2] in {'co', 'com', 'org', 'net', 'gov', 'edu', 'ac'}:
        stem = labels[-3]
    source = 'https://crt.sh/'
    query = '%' + stem + '%'
    source_url = source + '?q=' + quote(query) + '&output=json'
    if len(stem) < 4 or stem in {'www', 'mail', 'login', 'admin', 'test', 'example'}:
        return _unknown(domain, 'Brand research', source_url, 'insufficient_input', 'Brand stem is too short or generic for a bounded candidate search.')
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as raw:
            return await research_brand(domain, raw)

    async def run():
        response = await _bounded_get(client, source, params={'q': query, 'output': 'json'}, follow_redirects=False)
        if response.status_code != 200 or len(response.content) > MAX_BODY:
            return _unknown(domain, 'Brand research', source_url, 'rate_limited' if response.status_code == 429 else 'blocked' if response.status_code in (401, 403) else 'source_unavailable', f'crt.sh returned HTTP {response.status_code}; no certificate candidates inferred.')
        payload = response.json()
        if not isinstance(payload, list):
            return _unknown(domain, 'Brand research', source_url, 'parser_mismatch', 'Certificate response was not a list.')
        if payload and not any(isinstance(item, dict) and isinstance(item.get('name_value'), str) for item in payload[:5000]):
            return _unknown(domain, 'Brand research', source_url, 'parser_mismatch', 'Certificate entries are malformed.')
        candidates = {}
        for item in payload[:5000]:
            if not isinstance(item, dict) or not isinstance(item.get('name_value'), str):
                continue
            for raw in item['name_value'][:5000].splitlines()[:100]:
                try:
                    name = normalize_domain(raw.strip().removeprefix('*.'))
                except ValueError:
                    continue
                if name == domain or name.endswith('.' + domain):
                    continue
                # Match only a complete DNS label or a hyphenated brand token, never arbitrary substrings.
                if not any(label == stem or label.startswith(stem + '-') or label.endswith('-' + stem) for label in name.split('.')[:-1]):
                    continue
                candidates.setdefault(name, _certificate_time(item.get('entry_timestamp')))
        rows = [_row(domain, 'Brand research', 'https://' + name + '/', 'found',
                     detail='Unverified name-similarity candidate from public certificate records; candidate not visited.',
                     source_url=source_url, candidate_domain=name, similarity_reason='Exact brand label or hyphen-delimited brand token in certificate name',
                     assessment='unverified_candidate', impersonation_verified=False, ownership_verified=False,
                     certificate_timestamp=timestamp, candidate_visited=False,
                     truncated=len(candidates) > 30 or len(payload) > 5000)
                for name, timestamp in sorted(candidates.items())[:30]]
        return rows or [_row(domain, 'Brand research', source_url, 'not_found', source_url=source_url,
                            detail='No eligible candidates in this bounded certificate response; absence does not exclude impersonation.')]

    try:
        return await asyncio.wait_for(run(), TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        return _unknown(domain, 'Brand research', source_url, 'timeout', 'Research time budget exhausted.')
    except httpx.TimeoutException:
        return _unknown(domain, 'Brand research', source_url, 'timeout', 'crt.sh request timed out; no certificate candidates inferred.')
    except httpx.HTTPError as exc:
        return _unknown(domain, 'Brand research', source_url, 'network_error', f'crt.sh request failed ({type(exc).__name__}); no certificate candidates inferred.')
    except (ValueError, TypeError):
        return _unknown(domain, 'Brand research', source_url, 'parser_mismatch', 'Certificate source unavailable or invalid.')
