"""Passive domain evidence via fixed DNS and certificate-log providers."""
import asyncio
import re
from urllib.parse import quote
import httpx

from osint.domain_research import normalize_domain


async def research_domain_security(domain, client, *, certificates=True):
    domain = normalize_domain(domain)

    async def query(name, kind):
        source = 'https://dns.google/resolve'
        row = {'status': 'UNKNOWN', 'records': [],
               'source_url': f'{source}?name={quote(name)}&type={kind}&do=true&cd=false'}
        try:
            response = await client.get(source, params={'name': name, 'type': kind, 'do': 'true', 'cd': 'false'}, follow_redirects=False)
            if response.status_code != 200:
                row['reason'] = f'HTTP {response.status_code}'
                return row
            data = response.json()
            if not isinstance(data, dict) or type(data.get('Status')) is not int:
                return row
            row['dnssec_authenticated'] = data.get('AD') is True
            if data['Status'] in (0, 3):
                answers = data.get('Answer', [])
                if not isinstance(answers, list):
                    return row
                code = 16 if kind == 'TXT' else 48
                for item in answers[:100]:
                    if not isinstance(item, dict) or item.get('type') != code or str(item.get('name', '')).rstrip('.').casefold() != name:
                        continue
                    value = str(item.get('data', ''))[:4000]
                    # Join DNS TXT character strings, preserving a single logical record.
                    chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', value)
                    row['records'].append(''.join(chunks) if chunks else value)
                if not row['records'] and any(isinstance(a, dict) and a.get('type') == 5 for a in answers):
                    row['reason'] = 'CNAME hedefindeki kayıt bu kontrolde doğrulanmadı.'
                    return row
                row['status'] = 'FOUND' if row['records'] else 'NO_RECORDS'
            else:
                row['reason'] = f'DNS response code {data["Status"]}'
        except (httpx.HTTPError, ValueError, TypeError):
            row['reason'] = 'DNS yanıtı alınamadı veya geçersiz.'
        return row

    spf, dmarc, dnssec = await asyncio.gather(query(domain, 'TXT'), query('_dmarc.' + domain, 'TXT'), query(domain, 'DNSKEY'))
    for row, marker in ((spf, 'v=spf1'), (dmarc, 'v=dmarc1')):
        if row['status'] == 'UNKNOWN':
            continue
        row['records'] = [v for v in row['records'] if re.match(re.escape(marker) + r'(?:\s|;|$)', v, re.I)]
        row['status'] = 'FOUND' if row['records'] else 'NO_RECORDS'
        row['assessment'] = 'missing' if not row['records'] else 'multiple_records' if len(row['records']) > 1 else 'present'
    if spf.get('assessment') == 'present':
        record = spf['records'][0]
        spf['assessment'] = 'permits_all' if re.search(r'(?:^|\s)\+?all(?:\s|$)', record, re.I) else 'policy_present'
    if dmarc.get('assessment') == 'present':
        tags = [part.strip().split('=', 1) for part in dmarc['records'][0].split(';') if '=' in part]
        policies = [v.strip().lower() for k, v in tags if k.strip().lower() == 'p']
        dmarc['policy'] = policies[0] if len(policies) == 1 else ''
        dmarc['assessment'] = ('monitoring_only' if policies == ['none'] else 'enforcement_policy'
                               if policies in (['reject'], ['quarantine']) else 'invalid_policy')
    dnssec['assessment'] = ('validated_by_resolver' if dnssec.get('dnssec_authenticated')
                           else 'not_authenticated' if dnssec['status'] != 'UNKNOWN' else 'unknown')
    dnssec['limitations'] = 'AD işareti çözücünün doğrulamasını bildirir; AD yokluğu tek başına DNSSEC yokluğunu kanıtlamaz.'

    ct = {'status': 'NOT_REQUESTED', 'names': [], 'limitations': 'Sertifika kaydı güncel DNS veya çalışan hizmet kanıtı değildir.'}
    if certificates:
        ct.update(status='UNKNOWN', source_url='https://crt.sh/?q=' + quote('%.' + domain) + '&output=json')
        try:
            response = await asyncio.wait_for(client.get('https://crt.sh/', params={'q': '%.' + domain, 'output': 'json'}, follow_redirects=False), timeout=20)
            if response.status_code == 200 and len(response.content) <= 2_000_000:
                data = response.json()
                if isinstance(data, list):
                    names = set()
                    for item in data[:10000]:
                        if not isinstance(item, dict):
                            continue
                        for raw in str(item.get('name_value', ''))[:5000].splitlines():
                            name = raw.strip().removeprefix('*.').lower()
                            try:
                                name = normalize_domain(name)
                            except ValueError:
                                continue
                            if name.endswith('.' + domain):
                                names.add(name)
                    ct.update(status='FOUND' if names else 'NO_RECORDS', names=sorted(names)[:200], truncated=len(names) > 200 or len(data) > 10000)
            else:
                ct['reason'] = f'HTTP {response.status_code} veya yanıt boyutu sınırı'
        except (httpx.HTTPError, ValueError, TypeError, asyncio.TimeoutError):
            ct['reason'] = 'Sertifika kaynağı yanıt vermedi; sonuç belirsiz.'
    return {'SPF': spf, 'DMARC': dmarc, 'DNSSEC': dnssec, 'Certificate transparency': ct}
