"""Evidence cards and public metadata from responses already fetched by scans."""
from datetime import datetime, timezone
import re
from urllib.parse import urljoin

from osint.profile_evidence import ProfileDocument
from utils.public_data import public_url, configuration_fingerprint


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def enrich_profile(result, username, platform, response):
    result['response_evidence'] = {'source_url': public_url(str(response.url)), 'http_status': response.status_code, 'checked_at': utc_now()}
    if not result.get('found'):
        return result
    metadata = dict(result.get('public_metadata') or {})
    sources = {key: 'API:' + str(platform.get('metadata_fields', {}).get(key, key)) for key in metadata}
    if 'username' not in metadata:
        metadata['username'] = username.strip()
        sources['username'] = 'requested username, matched by detector rules'
    if 'profile_url' not in metadata:
        metadata['profile_url'] = result.get('url', '')
        sources['profile_url'] = 'configured public profile URL'
    html = response.text
    if html.lstrip().startswith('<') and len(html) <= 3_000_000:
        doc = response.extensions.pop('trackher_profile_document', None)
        if doc is None:
            doc = ProfileDocument()
            doc.feed(html)
        properties = {'og:description': 'bio', 'og:image': 'avatar_url', 'og:title': 'page_title',
                      'profile:first_name': 'first_name', 'profile:last_name': 'last_name'}
        for node in doc.nodes:
            if node.get('auxiliary'):
                continue
            attrs = node['attrs']
            if node['tag'] == 'meta':
                prop = attrs.get('property', attrs.get('name', ''))
                key = properties.get(prop)
                content = attrs.get('content', '').strip()
                if key and content and key not in metadata:
                    if key == 'avatar_url':
                        content = public_url(urljoin(str(response.url), content))
                    if content:
                        metadata[key] = content[:1500]
                        sources[key] = 'meta:' + prop
        # Only explicitly named profile headings; arbitrary page headings are not names.
        for node in doc.nodes:
            if not node.get('auxiliary') and node['tag'] == 'h1' and set(node['attrs'].get('class', '').split()) & {'name', 'profile-title', 'header-title', 'ArtistInfo-name'} and node['text'].strip():
                metadata.setdefault('display_name', ' '.join(node['text'].split())[:200])
                sources.setdefault('display_name', 'h1:profile-heading')
                break
        links = []
        for node in doc.nodes:
            if node.get('auxiliary'):
                continue
            attrs = node['attrs']
            if node['tag'] == 'a' and ('me' in attrs.get('rel', '').split() or attrs.get('itemprop') == 'sameAs'):
                url = public_url(urljoin(str(response.url), attrs.get('href', '')))
                if url and url != result.get('url') and url not in links:
                    links.append(url)
            if len(links) >= 10:
                break
        metadata['public_links'] = links
        if links:
            sources['public_links'] = 'a[rel=me|itemprop=sameAs]'
    existing_links = metadata.get('public_links', [])
    links = [public_url(url) for url in existing_links if isinstance(url, str)] if isinstance(existing_links, list) else []
    for field in ('website', 'blog'):
        url = public_url(metadata.get(field, ''))
        if url:
            links.append(url)
    # Bio links remain declarations by the profile, never verified account ownership.
    for url in re.findall(r'https?://[^\s<>"\)]+', str(metadata.get('bio', '')))[:10]:
        if public_url(url):
            links.append(public_url(url))
    metadata['public_links'] = list(dict.fromkeys(link for link in links if link))[:10]
    if not metadata['public_links']:
        metadata.pop('public_links', None)
    if metadata.get('first_name') and metadata.get('last_name'):
        metadata.setdefault('display_name', metadata['first_name'] + ' ' + metadata['last_name'])
        sources.setdefault('display_name', 'profile:first_name + profile:last_name')
    result['public_metadata'] = metadata
    result['field_sources'] = {key: value for key, value in sources.items() if key in metadata}
    return result


def evidence_card(result, *, detector='', rules=None):
    response = result.get('response_evidence') or {}
    status = str(result.get('status', 'unknown'))
    metadata = result.get('public_metadata') or {}
    fields = [{'field': key, 'value': value, 'source': result.get('field_sources', {}).get(key, 'public_metadata')}
              for key, value in metadata.items() if key not in ('avatar_hash',)][:20]
    identity_claim = 'candidate_only' if status.upper() == 'POSSIBLE' else ('profile_presence_only' if status.upper() == 'FOUND' else 'none')
    if result.get('research_kind') and status.upper() == 'FOUND':
        identity_claim = 'public_record_only'
    if status.upper() == 'FOUND' and (result.get('section') == 'breach' or 'breach_details' in metadata):
        identity_claim = 'breach_listing_only'
    elif status.upper() == 'FOUND' and (result.get('domain') or detector in ('A', 'AAAA', 'MX', 'NS', 'RDAP', 'SPF', 'DMARC', 'DNSSEC', 'Certificate transparency', 'dns_mx')):
        identity_claim = 'public_record_only'
    return {'checked_at': response.get('checked_at') or result.get('checked_at') or utc_now(), 'source_url': response.get('source_url') or public_url(metadata.get('commit_url', '')) or public_url(metadata.get('record_url', '')) or public_url(result.get('source_url', '')) or public_url(result.get('url', '')),
            'source_type': 'response' if response.get('source_url') else 'public_record_link',
            'http_status': response.get('http_status'), 'status': status,
            'detector': detector or result.get('detector_used', ''),
            'rules': rules or [], 'fields': fields,
            'reason': str(result.get('detail', '')),
            'unknown_cause': result.get('unknown_cause'),
            'identity_claim': identity_claim,
            'limitations': 'Public declarations and profile presence do not prove real-world ownership.'}


def finalize_username(result, username, platform):
    result['queried_username'] = username.strip()
    rules = platform.get('profile_evidence', []) if result.get('found') else []
    if not rules and result.get('found'):
        rules = [{'identity_path': platform.get('json_path', ''), 'check': platform.get('check', 'html')}]
    result['evidence_card'] = evidence_card(result, detector=result.get('detector_used', platform.get('check', 'html')), rules=rules)
    result['evidence_card']['rule_fingerprint'] = configuration_fingerprint(platform)
    return result


def email_evidence_view(accounts, breaches, domain):
    records = []
    for section, results in (('account', accounts), ('breach', breaches)):
        for result in results:
            result.setdefault('evidence_card', evidence_card(result))
            records.append({'section': section, 'service': result.get('service', ''),
                            'status': result.get('status'), 'card': result['evidence_card']})
    if domain:
        domain['evidence_card'] = evidence_card(domain, detector='dns_mx')
        records.append({'section': 'domain', 'service': domain.get('domain', ''), 'status': domain.get('status'),
                        'card': domain['evidence_card']})
    return records
