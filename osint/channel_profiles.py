"""Verify public Odysee channel claims through anonymous, read-only resolution."""
import re
from datetime import datetime, timezone


ODYSEE_RESOLVE_URL = 'https://api.na-backend.odysee.com/api/v1/proxy?m=resolve'


async def detect_odysee_channel(username, platform, client, result):
    from osint.username_checker import _set_result, _request_timeout, _http_unknown_cause

    query = 'lbry://@' + username.strip()
    response = await client.post(
        ODYSEE_RESOLVE_URL,
        json={'jsonrpc': '2.0', 'method': 'resolve', 'params': {'urls': [query]}, 'id': 1},
        headers={'Accept': 'application/json'}, follow_redirects=False,
        timeout=_request_timeout(platform),
    )
    result['response_evidence'] = {
        'source_url': ODYSEE_RESOLVE_URL, 'http_status': response.status_code,
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
    if response.status_code != 200:
        return _set_result(result, 'unknown', f'Channel API HTTP {response.status_code}',
                           _http_unknown_cause(response.status_code, response.text))
    unknown = lambda: _set_result(result, 'unknown', 'Channel claim identity not verified', 'parser_mismatch')
    if len(response.content) > 1_000_000:
        return unknown()
    try:
        data = response.json()
    except ValueError:
        return unknown()
    if not isinstance(data, dict) or data.get('jsonrpc') != '2.0' or type(data.get('id')) is not int or data['id'] != 1 or 'error' in data:
        return unknown()
    records = data.get('result')
    entry = records.get(query) if isinstance(records, dict) else None
    if not isinstance(entry, dict):
        return unknown()
    error = entry.get('error')
    if isinstance(error, dict):
        if set(entry) == {'error'} and error.get('name') == 'NOT_FOUND' and error.get('text') == f'Could not find channel in "{query}".':
            return _set_result(result, 'not_found', 'Requested public channel claim does not exist', 'soft_404')
        return unknown()
    name, claim = entry.get('name'), entry.get('claim_id')
    if (entry.get('value_type') != 'channel' or not isinstance(name, str)
            or name.casefold() != ('@' + username.strip()).casefold()
            or entry.get('normalized_name') != name.casefold()
            or not isinstance(claim, str) or not re.fullmatch('[0-9a-f]{40}', claim)
            or not isinstance(entry.get('value'), dict)
            or entry.get('permanent_url') != f'lbry://{name}#{claim}'):
        return unknown()
    result['public_metadata'] = {'username': name[1:], 'channel_claim_id': claim}
    title = entry['value'].get('title')
    if isinstance(title, str) and title.strip():
        result['public_metadata']['channel_title'] = title.strip()[:250]
    result['field_sources'] = {key: 'odysee_public_resolve' for key in result['public_metadata']}
    return _set_result(result, 'found', 'Public channel claim and requested identity verified')
