"""One-hop discovery through known catalog profile patterns only."""
import re
import asyncio
from urllib.parse import unquote

from utils.public_data import public_url, profile_key

DISCOVERY_REQUEST_TIMEOUT_SECONDS = 12
DISCOVERY_TOTAL_TIMEOUT_SECONDS = 35


def linked_candidates(results, platforms, limit=10):
    if limit <= 0:
        return []
    seen = {(r.get('platform'), str(r.get('queried_username', '')).casefold()) for r in results}
    candidates = []
    for source in results:
        if not source.get('found') or source.get('reliability') != 'verified':
            continue
        links = (source.get('public_metadata') or {}).get('public_links', [])
        if not isinstance(links, list):
            continue
        for link in links[:10]:
            url = public_url(link)
            if not url:
                continue
            for platform in platforms:
                if platform.get('disabled_reason') or not (platform.get('strict_api') or platform.get('check') == 'structured_profile'):
                    continue
                template = platform['url'].replace('https://', '').replace('http://', '').removeprefix('www.').rstrip('/')
                regex = re.escape(template).replace(re.escape('{}'), r'([A-Za-z0-9_.~-]{1,100})')
                match = re.fullmatch(regex, profile_key(url), flags=re.I)
                if not match:
                    continue
                username = unquote(match.group(1))
                key = (platform['name'], username.casefold())
                if key in seen:
                    break
                seen.add(key)
                candidates.append({'platform': platform, 'username': username, 'source_url': source.get('url', ''), 'declared_url': url})
                if len(candidates) >= max(0, min(limit, 10)):
                    return candidates
                break
    return candidates


async def discover_linked_profiles(results, platforms, client, limit=10):
    from osint.username_checker import check_single_username
    from osint.evidence import finalize_username
    candidates = linked_candidates(results, platforms, limit)
    completed = {}
    semaphore = asyncio.Semaphore(2)
    def timed_out(candidate):
        return finalize_username({'platform': candidate['platform']['name'], 'status': 'unknown', 'found': False,
            'url': candidate['platform']['url'].format(candidate['username']), 'unknown_cause': 'timeout',
            'detail': 'Linked discovery time budget exhausted', 'reliability': candidate['platform'].get('reliability', 'unreliable')}, candidate['username'], candidate['platform'])
    async def check(index, candidate):
        async with semaphore:
            # Use the catalog probe; never fetch the arbitrary declared URL.
            try:
                result = await asyncio.wait_for(check_single_username(candidate['username'], candidate['platform'], client), DISCOVERY_REQUEST_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                result = timed_out(candidate)
            completed[index] = result
    try:
        await asyncio.wait_for(asyncio.gather(*(check(i, c) for i, c in enumerate(candidates))), DISCOVERY_TOTAL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        pass
    results = []
    for index, candidate in enumerate(candidates):
        result = completed.get(index) or timed_out(candidate)
        result['discovered_from'] = {'source_url': candidate['source_url'], 'declared_url': candidate['declared_url'], 'depth': 1, 'ownership_verified': False}
        results.append(result)
    return results
