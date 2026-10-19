"""Bounded archive indexes, optional two-capture comparisons, and news mentions."""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import hashlib
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, urljoin
import xml.etree.ElementTree as ET

import httpx

from osint.domain_research import normalize_domain
from utils.public_data import public_url

MAX_RESPONSE_BYTES = 1_000_000
MAX_RECORDS = 30
DEADLINE_SECONDS = 25
CDX_URL = 'https://web.archive.org/cdx/search/cdx'
NEWS_URL = 'https://news.google.com/rss/search'


class _Unavailable(Exception):
    pass


def _row(platform, query, url, kind):
    return {'platform': platform, 'queried_username': query, 'url': url,
            'status': 'unknown', 'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            'evidence_type': kind, 'public_metadata': {'records': [], 'source_url': url,
                'coverage': 'Limited provider index, not an exhaustive search', 'record_limit': MAX_RECORDS}}


def _check_status(status):
    if status == 429:
        raise _Unavailable('rate_limited')
    if status in (401, 403):
        raise _Unavailable('blocked')
    if 300 <= status < 400:
        raise _Unavailable('redirect_changed')
    if status != 200:
        raise _Unavailable('provider_error')


async def _fetch(client, url):
    # Raw HTTPX clients allow an actual download cap, including decoded chunks.
    if hasattr(client, 'stream'):
        async with client.stream('GET', url, follow_redirects=False) as response:
            _check_status(response.status_code)
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise _Unavailable('response_too_large')
                chunks.append(chunk)
            return b''.join(chunks)
    response = await client.get(url, follow_redirects=False)
    _check_status(response.status_code)
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise _Unavailable('response_too_large')
    return response.content


async def _collect(row, client, parser):
    try:
        body = await asyncio.wait_for(_fetch(client, row['url']), timeout=DEADLINE_SECONDS)
        records, rejected, limited = parser(body)
        row['public_metadata'].update(records=records, rejected_records=rejected, limit_reached=limited)
        if records:
            row['status'] = 'found'
        elif rejected:
            row['unknown_cause'] = 'parser_mismatch'
        else:
            row['status'] = 'not_found'
    except _Unavailable as exc:
        row['unknown_cause'] = str(exc)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        row['unknown_cause'] = 'timeout'
    except httpx.HTTPError:
        row['unknown_cause'] = 'network_error'
    except (ValueError, TypeError, ET.ParseError, UnicodeError, OverflowError):
        row['unknown_cause'] = 'parser_mismatch'
    return [row]


def _history_records(body, domain):
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError('Invalid CDX response')
    if not data:
        return [], 0, False
    header = data[0]
    fields = ['timestamp', 'original', 'mimetype', 'statuscode', 'digest']
    if header != fields:
        raise ValueError('Unexpected CDX fields')
    records, seen, rejected = [], set(), 0
    for values in data[1:MAX_RECORDS + 1]:
        if not isinstance(values, list) or len(values) != len(fields) or not all(isinstance(v, str) for v in values):
            rejected += 1
            continue
        timestamp, original, mimetype, status, digest = values
        url = public_url(original)
        host = (urlsplit(url).hostname or '').lower().rstrip('.')
        try:
            if not re.fullmatch(r'\d{14}', timestamp):
                raise ValueError('Invalid timestamp')
            moment = datetime.strptime(timestamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
            if moment > datetime.now(timezone.utc) or not url or not (host == domain or host.endswith('.' + domain)):
                raise ValueError('Unexpected archive target')
            if status != '200' or mimetype.lower() not in ('text/html', 'application/xhtml+xml'):
                raise ValueError('Unexpected record type')
        except ValueError:
            rejected += 1
            continue
        key = timestamp, url
        if key in seen:
            continue
        seen.add(key)
        records.append({'timestamp': moment.isoformat(), 'capture_timestamp': timestamp, 'url': url,
                        'archive_url': 'https://web.archive.org/web/' + timestamp + '/' + url,
                        'mimetype': mimetype, 'statuscode': status, 'digest': digest[:128]})
    records.sort(key=lambda r: r['timestamp'])
    return records, rejected, len(data) - 1 >= MAX_RECORDS


async def research_history(domain, client=None, *, inspect_pages=False, on_result=None):
    """Return one archive-index result row; invalid user input raises ValueError."""
    domain = normalize_domain(domain)
    params = {'url': domain, 'matchType': 'domain', 'output': 'json',
              'fl': 'timestamp,original,mimetype,statuscode,digest', 'filter': 'statuscode:200',
              'collapse': 'timestamp:6', 'limit': MAX_RECORDS}
    row = _row('Web history', domain, CDX_URL + '?' + urlencode(params), 'archive_index')
    row['public_metadata']['limitations'] = 'Index references only; snapshot contents were not fetched or compared.'
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as raw:
            return await research_history(domain, raw, inspect_pages=inspect_pages, on_result=on_result)
    started = asyncio.get_running_loop().time()
    rows = await _collect(row, client, lambda b: _history_records(b, domain))
    if on_result:
        on_result(row)
    if inspect_pages and row['status'] == 'found':
        captures = row['public_metadata']['records']
        groups = {}
        for capture in captures:
            groups.setdefault(capture['url'], []).append(capture)
        sampled = max(groups.values(), key=len)
        selected = [sampled[0]['archive_url']]
        if len(sampled) > 1:
            selected.append(sampled[-1]['archive_url'])
        remaining = DEADLINE_SECONDS - (asyncio.get_running_loop().time() - started)
        if remaining > .05:
            try:
                comparisons = await asyncio.wait_for(compare_archived_pages(domain, selected, client), remaining)
                rows.extend(comparisons)
                if on_result:
                    for comparison in comparisons:
                        on_result(comparison)
            except asyncio.TimeoutError:
                failed = _row('Archive comparison', domain, selected[0], 'archive_content')
                failed['unknown_cause'] = 'timeout'
                rows.append(failed)
                if on_result:
                    on_result(failed)
    return rows


def _archive_target(domain, archive_url):
    safe = public_url(archive_url)
    p = urlsplit(safe)
    if p.scheme != 'https' or p.netloc != 'web.archive.org':
        raise ValueError('Select a canonical HTTPS Wayback capture')
    match = re.fullmatch(r'/web/(\d{14})/(https?://.+)', p.path)
    # Query strings belong to the captured original URL, so validate them below.
    if not match:
        raise ValueError('Select a canonical Wayback capture')
    stamp, original = match.groups()
    if p.query:
        original += '?' + p.query
    moment = datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    if moment > datetime.now(timezone.utc):
        raise ValueError('Capture timestamp is in the future')
    original = public_url(original)
    host = (urlsplit(original).hostname or '').lower().rstrip('.')
    if not original or not (host == domain or host.endswith('.' + domain)):
        raise ValueError('Capture must match the researched domain')
    return stamp, original, safe


class _ArchivedPage(HTMLParser):
    def __init__(self, original):
        super().__init__(convert_charrefs=True)
        self.original, self.links, self.text, self.title = original, set(), [], []
        self.stack, self.in_title = [], False
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 10000 or len(self.stack) > 256:
            raise ValueError('Archive HTML complexity limit exceeded')
        attrs = dict(attrs)
        hidden = (tag in ('script', 'style', 'noscript', 'template') or 'hidden' in attrs
                  or attrs.get('aria-hidden', '').lower() == 'true'
                  or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', attrs.get('style', ''), re.I)))
        excluded = hidden or any(value for _, value in self.stack)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, excluded))
        if excluded:
            return
        if tag == 'title':
            self.in_title = True
        if tag == 'a' and len(self.links) < 200:
            href = attrs.get('href', '') or ''
            if not href.strip() or href.startswith('#'):
                return
            # Wayback rewrites archived links; recover their public target.
            rewritten = re.match(r'^(?:https?://web\.archive\.org)?/web/\d{1,14}[a-z_]*/(https?://.+)$', href)
            url = public_url(rewritten.group(1) if rewritten else urljoin(self.original, href))
            if url:
                self.links.add(url)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if not any(excluded for _, excluded in self.stack):
            self.text.append(data)
            if self.in_title:
                self.title.append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


async def compare_archived_pages(domain, archive_urls, client=None):
    """Inspect at most two selected captures; unavailable pages never imply removal."""
    domain = normalize_domain(domain)
    if not isinstance(archive_urls, (list, tuple)) or not 1 <= len(archive_urls) <= 2:
        raise ValueError('Select one or two archive captures')
    targets = [_archive_target(domain, value) for value in archive_urls]
    if len({target[2] for target in targets}) != len(targets):
        raise ValueError('Select different archive captures')
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as raw:
            return await compare_archived_pages(domain, archive_urls, raw)
    row = _row('Archive comparison', domain, targets[0][2], 'archive_content')
    row['public_metadata']['limitations'] = ('Two sampled archived pages only; normalized visible text and links may include archive artifacts. '
        'Differences do not establish publication dates, ownership, or live-site deletion.')
    async def inspect(target):
        stamp, original, source = target
        try:
            # id_ avoids Wayback toolbar injection while keeping a fixed fetch host.
            fetch_url = 'https://web.archive.org/web/' + stamp + 'id_/' + original
            body = await _fetch(client, fetch_url)
            text = body.decode('utf-8', errors='replace')
            if not re.search(r'<(?:html|head|title|body)\b', text, re.I):
                raise _Unavailable('parser_mismatch')
            if re.search(r'<title[^>]*>\s*(?:Wayback Machine|Just a moment|Access denied|Error)', text, re.I):
                raise _Unavailable('blocked')
            page = _ArchivedPage(original)
            page.feed(text)
            visible = ' '.join(' '.join(page.text).split())
            if not visible:
                raise _Unavailable('parser_mismatch')
            return {'timestamp': datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).isoformat(),
                    'url': original, 'archive_url': source, 'source_url': source,
                    'title': ' '.join(' '.join(page.title).split())[:1000],
                    'public_links': sorted(page.links), 'content_sha256': hashlib.sha256(visible.encode()).hexdigest()}
        except _Unavailable as exc:
            return {'archive_url': source, 'status': 'unknown', 'unknown_cause': str(exc)}
        except httpx.TimeoutException:
            return {'archive_url': source, 'status': 'unknown', 'unknown_cause': 'timeout'}
        except httpx.HTTPError:
            return {'archive_url': source, 'status': 'unknown', 'unknown_cause': 'network_error'}
        except (ValueError, UnicodeError):
            return {'archive_url': source, 'status': 'unknown', 'unknown_cause': 'parser_mismatch'}
    try:
        results = await asyncio.wait_for(asyncio.gather(*(inspect(t) for t in targets)), DEADLINE_SECONDS)
    except asyncio.TimeoutError:
        row['unknown_cause'] = 'timeout'
        return [row]
    records = [r for r in results if r.get('status') != 'unknown']
    row['public_metadata'].update(records=records, unavailable_captures=[r for r in results if r.get('status') == 'unknown'])
    if records:
        row['status'] = 'found'
    else:
        row['unknown_cause'] = results[0].get('unknown_cause', 'parser_mismatch')
    if len(records) == 2 and records[0]['url'] == records[1]['url']:
        before, after = sorted(records, key=lambda r: r['timestamp'])
        row['public_metadata']['comparison'] = {'status': 'compared',
            'title_changed': before['title'] != after['title'],
            'content_changed': before['content_sha256'] != after['content_sha256'],
            'added_links': sorted(set(after['public_links']) - set(before['public_links'])),
            'removed_links': sorted(set(before['public_links']) - set(after['public_links']))}
    else:
        row['public_metadata']['comparison'] = {'status': 'unknown', 'reason': 'Two available captures of the same URL required'}
    return [row]


def _normalized_title(title):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', title).casefold()))


def _normalized_link(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))


def _mention_records(body):
    # The provider emits UTF-8. Reject alternate XML encodings and declarations
    # before parsing, so a UTF-16 DTD cannot evade the declaration check.
    text = body.decode('utf-8-sig')
    if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML declarations not accepted')
    root = ET.fromstring(text)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None or not (channel.findtext('title') or '').strip():
        raise ValueError('Unexpected RSS response')
    items = channel.findall('item')
    records, rejected = [], 0
    for item in items[:MAX_RECORDS]:
        title = ' '.join((item.findtext('title') or '').split())[:1000]
        url = public_url(item.findtext('link'))
        if not title or not url:
            rejected += 1
            continue
        published = ''
        date = (item.findtext('pubDate') or '').strip()
        if date:
            try:
                moment = parsedate_to_datetime(date)
                if moment.tzinfo is not None:
                    published = moment.astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                pass
        source = item.find('source')
        source_name = ' '.join((source.text or '').split())[:300] if source is not None else ''
        source_url = public_url(source.get('url', '')) if source is not None else ''
        title_key, link_key = _normalized_title(title), _normalized_link(url)
        if not title_key:
            rejected += 1
            continue
        duplicate = next((r for r in records if title_key in r['_titles'] or link_key in r['_links']), None)
        if duplicate is not None:
            duplicate['duplicate_count'] += 1
            duplicate['_titles'].add(title_key)
            duplicate['_links'].add(link_key)
            if url not in duplicate['related_urls']:
                duplicate['related_urls'].append(url)
            continue
        records.append({'title': title, 'url': url, 'published': published, 'source': source_name,
                        'source_url': source_url, 'relevance': 'unverified', 'duplicate_count': 0,
                        'related_urls': [], '_titles': {title_key}, '_links': {link_key}})
    for record in records:
        record.pop('_titles')
        record.pop('_links')
    return records, rejected, len(items) >= MAX_RECORDS


async def research_mentions(query, client=None):
    """Return public news-index candidates, never verified identity matches."""
    if not isinstance(query, str) or any(ord(c) < 32 or ord(c) == 127 for c in query):
        raise ValueError('Enter a public research query of 2 to 160 characters')
    query = query.strip()
    if not 2 <= len(query) <= 160:
        raise ValueError('Enter a public research query of 2 to 160 characters')
    url = NEWS_URL + '?' + urlencode({'q': query, 'hl': 'tr', 'gl': 'TR', 'ceid': 'TR:tr'})
    row = _row('Public mentions', query, url, 'news_index')
    row['public_metadata'].update(relevance='unverified', provider_contract='experimental_public_rss',
        limitations='Google News candidates only. Relevance and independent corroboration require review; articles were not fetched.')
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as raw:
            return await _collect(row, raw, _mention_records)
    return await _collect(row, client, _mention_records)
