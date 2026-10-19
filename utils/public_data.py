"""Conservative URL handling for public evidence; never a fetch permission."""
import ipaddress
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit


EVIDENCE_POLICY_REVISION = '2026-10-19-no-reflections'


def configuration_fingerprint(definition):
    # Engine semantics can change without editing a site's configuration.
    # Retire cached health and evidence reviews produced by weaker rules.
    payload = {'policy_revision': EVIDENCE_POLICY_REVISION, 'definition': definition}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')).hexdigest()[:16]


def public_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return ''
    try:
        p = urlsplit(value.strip())
        host = (p.hostname or '').rstrip('.').lower()
        if p.scheme not in ('https', 'http') or not host or p.username or p.password or p.port not in (None, 80, 443):
            return ''
        if host == 'localhost' or '.' not in host or host.endswith(('.localhost', '.local', '.internal', '.lan')):
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            pass
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))
    except ValueError:
        return ''


def profile_key(value):
    url = public_url(value)
    if not url:
        return ''
    p = urlsplit(url)
    return (p.hostname or '').removeprefix('www.') + p.path.rstrip('/').casefold() + ('?' + p.query if p.query else '')


def research_key(result):
    """Stable source identity; article titles and certificate dates can change."""
    kind = result.get('research_kind')
    if kind not in ('history', 'brand', 'organization', 'mentions'):
        return ''
    platform = str(result.get('platform') or result.get('service') or 'Source')
    provider = platform.split(' · ', 1)[0]
    role = 'record' if ' · ' in platform or kind in ('brand', 'organization') else 'summary'
    metadata = result.get('public_metadata', {})
    records = metadata.get('records', []) if isinstance(metadata, dict) else []
    stamp = ''
    if kind == 'history' and role == 'record' and len(records) == 1 and isinstance(records[0], dict):
        stamp = str(records[0].get('capture_timestamp') or records[0].get('timestamp') or '')
    identity = [kind, provider, role, str(result.get('evidence_type', '')),
                str(result.get('url', '')), stamp, str(result.get('queried_username', ''))]
    return 'research:' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
