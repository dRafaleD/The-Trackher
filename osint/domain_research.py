"""Explicit domain research using DNS JSON and IANA-bootstrapped RDAP."""
import asyncio
from datetime import datetime, timezone
import ipaddress
import re
from urllib.parse import quote

import httpx

from osint.request_policy import PoliteAsyncClient
from utils.public_data import public_url


def normalize_domain(value):
    if not isinstance(value, str):
        raise ValueError('Enter a domain name, not a URL or IP address')
    domain = value.strip().rstrip('.').lower()
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Invalid domain') from exc
    if len(domain) > 253 or '.' not in domain or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')):
        raise ValueError('Enter a domain name, not a URL or IP address')
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        if domain.endswith(('.local', '.localhost', '.internal', '.lan', '.invalid')):
            raise ValueError('A public domain is required')
        return domain
    raise ValueError('Enter a domain name, not an IP address')


async def research_domain(domain, client=None, *, enhanced=False, certificates=False):
    domain = normalize_domain(domain)
    if client is None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as raw:
            return await research_domain(domain, PoliteAsyncClient(raw, max_concurrent=2), enhanced=enhanced, certificates=certificates)
    result = {'domain': domain, 'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              'status': 'PARTIAL', 'dns': {}, 'rdap': {},
              'limitations': 'Registration and DNS records do not prove mailbox or real-world ownership.'}

    async def dns(record_type):
        source = 'https://dns.google/resolve'
        row = {'status': 'UNKNOWN', 'records': [], 'source_url': source + '?name=' + quote(domain, safe='.-') + '&type=' + record_type}
        try:
            r = await client.get(source, params={'name': domain, 'type': record_type}, follow_redirects=False)
            if r.status_code != 200:
                row['reason'] = f'HTTP {r.status_code}'
                return record_type, row
            data = r.json()
            if not isinstance(data, dict) or type(data.get('Status')) is not int:
                return record_type, row
            if data['Status'] == 3:
                row['status'] = 'DOMAIN_NOT_FOUND'
            elif data['Status'] == 0:
                codes = {'A': 1, 'AAAA': 28, 'MX': 15, 'NS': 2}
                answers = data.get('Answer', [])
                if not isinstance(answers, list):
                    return record_type, row
                row['records'] = [str(a.get('data', ''))[:500] for a in answers[:50]
                                  if isinstance(a, dict) and a.get('type') == codes[record_type]]
                row['status'] = 'FOUND' if row['records'] else 'NO_RECORDS'
        except (httpx.HTTPError, ValueError, TypeError):
            row['reason'] = 'DNS response unavailable or invalid'
        return record_type, row

    async def rdap():
        row = {'status': 'UNKNOWN', 'bootstrap_url': 'https://data.iana.org/rdap/dns.json'}
        try:
            bootstrap = await client.get(row['bootstrap_url'], follow_redirects=False)
            if bootstrap.status_code != 200 or len(bootstrap.content) > 1_000_000:
                return row
            data = bootstrap.json()
            if not isinstance(data, dict) or not isinstance(data.get('services'), list):
                return row
            base = ''
            suffix_length = 0
            for service in data['services']:
                if not isinstance(service, list) or len(service) != 2 or not all(isinstance(v, list) for v in service):
                    continue
                for suffix in service[0]:
                    if isinstance(suffix, str) and (domain == suffix or domain.endswith('.' + suffix)) and len(suffix) > suffix_length:
                        urls = [public_url(u) for u in service[1] if isinstance(u, str) and u.startswith('https://')]
                        if urls and urls[0]:
                            base, suffix_length = urls[0], len(suffix)
            if not base:
                row['reason'] = 'No supported authoritative HTTPS RDAP service'
                return row
            row['source_url'] = base.rstrip('/') + '/domain/' + quote(domain, safe='.-')
            response = await client.get(row['source_url'], follow_redirects=False, headers={'Accept': 'application/rdap+json'})
            if response.status_code == 404:
                row['status'] = 'NOT_FOUND'
                return row
            if response.status_code != 200 or len(response.content) > 2_000_000:
                row['reason'] = f'HTTP {response.status_code}'
                return row
            payload = response.json()
            if not isinstance(payload, dict) or payload.get('objectClassName') != 'domain' or str(payload.get('ldhName', '')).casefold() != domain:
                row['reason'] = 'RDAP domain identity did not match'
                return row
            row.update(status='FOUND', handle=str(payload.get('handle', ''))[:200],
                       registrar_handles=[str(e.get('handle', ''))[:200] for e in payload.get('entities', [])[:20] if isinstance(e, dict) and 'registrar' in e.get('roles', [])],
                       events=[{'action': str(e.get('eventAction', ''))[:80], 'date': str(e.get('eventDate', ''))[:80]}
                               for e in payload.get('events', [])[:20] if isinstance(e, dict)],
                       nameservers=[str(n.get('ldhName', ''))[:253] for n in payload.get('nameservers', [])[:20] if isinstance(n, dict)])
        except (httpx.HTTPError, ValueError, TypeError):
            row['reason'] = 'RDAP response unavailable or invalid'
        return row

    values = await asyncio.gather(*(dns(t) for t in ('A', 'AAAA', 'MX', 'NS')), rdap())
    result['dns'] = dict(values[:4])
    result['rdap'] = values[4]
    if all(v['status'] != 'UNKNOWN' for v in result['dns'].values()) and result['rdap']['status'] != 'UNKNOWN':
        result['status'] = 'COMPLETE'
    if enhanced:
        from osint.domain_security import research_domain_security
        result['security'] = await research_domain_security(domain, client, certificates=certificates)
        if any(row['status'] == 'UNKNOWN' for row in result['security'].values()):
            result['status'] = 'PARTIAL'
    return result
