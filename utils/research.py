"""Portable local investigation files, field-level differences and evidence graphs."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from utils.public_data import public_url, profile_key, research_key
from utils.correlation import _build_nodes, _pairwise_evidence

MAX_CASE_BYTES = 20_000_000
INTELLIGENCE_KINDS = ('history', 'brand', 'organization', 'mentions')
FIELDS = ('display_name', 'bio', 'avatar_url', 'website', 'public_links', 'breach_details', 'records', 'names', 'policy', 'assessment',
          'candidate_domain', 'linked_domain', 'linked_platform', 'category', 'certificate_timestamp', 'similarity_reason', 'source_url', 'comparison')


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def result_key(row):
    return research_key(row) or str(row.get('platform') or row.get('service') or 'Domain') + '|' + str(row.get('queried_username', ''))


def new_case(title='Yeni araştırma'):
    return {'version': 1, 'title': title[:200], 'notes': '', 'tags': [], 'scans': [], 'decisions': {}, 'reviews': {}}


def validate_case(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Desteklenmeyen araştırma dosyası')
    if not isinstance(data.get('title'), str) or not isinstance(data.get('notes', ''), str):
        raise ValueError('Geçersiz araştırma başlığı veya notu')
    if not isinstance(data.get('tags', []), list) or not all(isinstance(t, str) for t in data.get('tags', [])):
        raise ValueError('Geçersiz etiketler')
    scans = data.get('scans')
    if not isinstance(scans, list) or len(scans) > 100:
        raise ValueError('En fazla 100 tarama desteklenir')
    for scan in scans:
        if not isinstance(scan, dict) or scan.get('kind') not in ('username', 'email', 'domain') + INTELLIGENCE_KINDS or not isinstance(scan.get('target'), str):
            raise ValueError('Geçersiz tarama')
        rows = scan.get('rows')
        if not isinstance(rows, list) or len(rows) > 2000 or not all(isinstance(r, dict) for r in rows):
            raise ValueError('Geçersiz sonuç listesi')
        from utils.profiles import PROFILE_ORDER
        if scan.get('profile') not in PROFILE_ORDER or not isinstance(scan.get('checked_at'), str) or type(scan.get('stopped')) is not bool:
            raise ValueError('Geçersiz tarama kapsamı veya zamanı')
        for row in rows:
            if not isinstance(row.get('public_metadata', {}), dict):
                raise ValueError('Geçersiz profil alanları')
            links = row.get('public_metadata', {}).get('public_links', [])
            if not isinstance(links, list) or not all(isinstance(v, str) for v in links):
                raise ValueError('Geçersiz profil bağlantıları')
            records = row.get('public_metadata', {}).get('records', [])
            if scan.get('kind') in INTELLIGENCE_KINDS and (not isinstance(records, list) or len(records) > 2000 or not all(isinstance(v, dict) for v in records)):
                raise ValueError('Geçersiz açık kaynak kayıtları')
            card = row.get('evidence_card', {})
            if not isinstance(card, dict) or not isinstance(card.get('fields', []), list) or not all(isinstance(f, dict) for f in card.get('fields', [])):
                raise ValueError('Geçersiz kanıt kartı')
            if not isinstance(row.get('field_sources', {}), dict):
                raise ValueError('Geçersiz alan kaynakları')
        diff = scan.get('diff', {})
        if not isinstance(diff, dict) or not isinstance(diff.get('changes', []), list) or not all(isinstance(c, dict) and isinstance(c.get('site'), str) and isinstance(c.get('type'), str) for c in diff.get('changes', [])):
            raise ValueError('Geçersiz karşılaştırma')
    if not isinstance(data.get('decisions', {}), dict) or any(v not in ('related', 'unrelated', 'uncertain') for v in data.get('decisions', {}).values()):
        raise ValueError('Geçersiz ilişki kararları')
    from utils.finding_reviews import validate_reviews
    validate_reviews(data.get('reviews', {}))
    return data


def load_case(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_CASE_BYTES + 1)
    if len(raw) > MAX_CASE_BYTES:
        raise ValueError('Araştırma dosyası 20 MB sınırını aşıyor')
    return validate_case(json.loads(raw.decode('utf-8')))


def save_case(path, data):
    validate_case(data)
    encoded = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    if len(encoded) > MAX_CASE_BYTES:
        raise ValueError('Araştırma dosyası 20 MB sınırını aşıyor')
    path = Path(path)
    # Atomic replacement keeps the previous file intact if writing fails.
    fd, temp = tempfile.mkstemp(prefix='.trackher-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def compare_scans(previous, current):
    if not previous:
        return {'available': False, 'changes': [], 'message': 'İlk tarama; karşılaştırılacak kayıt yok.'}
    before = {result_key(r): r for r in previous['rows']}
    after = {result_key(r): r for r in current['rows']}
    changes = []
    observed_statuses = ('found', 'possible') if current.get('kind') in INTELLIGENCE_KINDS else ('found',)
    for key, row in after.items():
        old = before.get(key)
        status = str(row.get('status', '')).lower()
        old_status = str((old or {}).get('status', '')).lower()
        if not old:
            if status in observed_statuses:
                changes.append({'site': key, 'type': 'new_record' if current.get('kind') in INTELLIGENCE_KINDS else 'new_profile', 'after': row.get('url', '')})
            continue
        if status in ('unknown', 'error', 'not_configured'):
            if old_status in observed_statuses:
                changes.append({'site': key, 'type': 'unavailable', 'after': row.get('unknown_cause', status)})
            continue
        if status != old_status:
            changes.append({'site': key, 'type': 'status', 'before': old_status, 'after': status})
        if status == old_status and status in observed_statuses:
            left, right = old.get('public_metadata', {}), row.get('public_metadata', {})
            for field in FIELDS:
                # A parser no longer extracting a field is not evidence of deletion.
                if field in left and field not in right:
                    changes.append({'site': key, 'type': 'field_unavailable', 'field': field})
                elif field == 'public_links' and field in left and field in right and isinstance(left[field], list) and isinstance(right[field], list):
                    removed = sorted(set(left[field]) - set(right[field]))
                    added = sorted(set(right[field]) - set(left[field]))
                    for link in removed:
                        changes.append({'site': key, 'type': 'removed_link', 'field': field, 'before': link})
                    for link in added:
                        changes.append({'site': key, 'type': 'added_link', 'field': field, 'after': link})
                elif field in right and left.get(field) != right[field]:
                    changes.append({'site': key, 'type': 'field', 'field': field,
                                    'before': left.get(field), 'after': right[field]})
    return {'available': True, 'changes': changes,
            'uncovered': sorted(before.keys() - after.keys()),
            'coverage_changed': previous.get('profile') != current.get('profile') or before.keys() != after.keys() or any(r.get('retained_from_previous_scan') for r in current['rows']),
            'message': 'Kapsam dışı sonuçlar silinmiş hesap sayılmaz; çıkarılamayan alanlar değişiklik kanıtı değildir.'}


def record_scan(case, kind, target, profile, rows, *, stopped=False):
    scan = {'kind': kind, 'target': target, 'profile': profile, 'checked_at': now(),
            'stopped': bool(stopped), 'rows': deepcopy(rows)}
    previous = next((s for s in reversed(case['scans']) if s['kind'] == kind and s['target'] == target), None)
    scan['diff'] = compare_scans(previous, scan)
    if len(case['scans']) >= 100:
        raise ValueError('Araştırma dosyasında 100 tarama var; yeni dosya oluşturun.')
    case['scans'].append(scan)
    return scan


def graph_for_scan(scan, decisions=None):
    if not scan:
        return {'nodes': [], 'edges': [], 'truncated': False}
    if scan.get('kind') in INTELLIGENCE_KINDS:
        return _intelligence_graph(scan, decisions)
    rows = scan['rows']
    payload = ({'osint_username': {'target': scan['target'], 'results': rows}} if scan['kind'] == 'username'
               else {'osint_email': {'results': {'accounts': [r for r in rows if r.get('section') != 'breach' and r.get('service') != 'Email domain']}}} if scan['kind'] == 'email' else {})
    raw = _build_nodes(payload)
    nodes, edges, by_url = [], [], {}
    for item in raw[:200]:
        key = profile_key(item.get('url', '')) or item['platform']
        node_id = hashlib.sha256((key + item['platform']).encode()).hexdigest()[:20]
        source = next((r for r in rows if (r.get('platform') or r.get('service')) == item['platform'] and str(r.get('url', '')) == item.get('url', '')), {})
        nodes.append({'id': node_id, 'label': item['platform'], 'url': item.get('url', ''),
                      'kind': 'profile', 'evidence': deepcopy(source)})
        if key:
            by_url[key] = node_id
    for index, left in enumerate(raw[:200]):
        for j in range(index + 1, min(len(raw), 200)):
            evidence, penalties = _pairwise_evidence(left, raw[j])
            if not evidence and not penalties:
                continue
            edge_id = ':'.join(sorted((nodes[index]['id'], nodes[j]['id'])))
            edges.append({'id': edge_id, 'left': nodes[index]['id'], 'right': nodes[j]['id'],
                          'kind': 'candidate', 'evidence': evidence, 'conflicts': penalties,
                          'sources': [nodes[index]['url'], nodes[j]['url']],
                          'decision': (decisions or {}).get(edge_id, 'uncertain')})
    # Explicit links also expose domain nodes without fetching those destinations.
    from urllib.parse import urlsplit
    domains = {}
    for index, item in enumerate(raw[:200]):
        links = item.get('metadata', {}).get('public_links', [])
        for value in (links if isinstance(links, list) else [])[:10]:
            url = public_url(value)
            if not url:
                continue
            host = urlsplit(url).hostname
            if host not in domains:
                domain_id = 'domain:' + host
                domains[host] = domain_id
                nodes.append({'id': domain_id, 'label': host, 'url': '', 'kind': 'domain'})
            edge_id = nodes[index]['id'] + ':' + domains[host]
            edges.append({'id': edge_id, 'left': nodes[index]['id'], 'right': domains[host],
                          'kind': 'declared_link', 'evidence': [{'label': 'public profile link', 'value': url}],
                          'conflicts': [], 'decision': (decisions or {}).get(edge_id, 'uncertain')})
    if scan['kind'] in ('username', 'email'):
        identifier = 'query:' + hashlib.sha256((scan['kind'] + scan['target']).encode()).hexdigest()[:20]
        profile_nodes = [n for n in nodes if n['kind'] == 'profile']
        nodes.insert(0, {'id': identifier, 'label': scan['target'], 'kind': 'query', 'url': ''})
        for node in profile_nodes:
            edges.append({'id': identifier + ':' + node['id'], 'left': identifier, 'right': node['id'],
                          'kind': 'search_result', 'evidence': [{'label': 'Arama sonucu; sahiplik kanıtı değildir', 'source': node['url']}],
                          'conflicts': [], 'decision': 'uncertain'})
    if scan['kind'] == 'domain':
        nodes = [{'id': 'domain:' + scan['target'], 'label': scan['target'], 'kind': 'domain', 'url': ''}]
        for index, row in enumerate(rows[:200]):
            nid = f'record:{index}'
            nodes.append({'id': nid, 'label': row.get('service', 'Record'), 'kind': 'record', 'evidence': row, 'url': row.get('url', '')})
            edges.append({'id': nid, 'left': nodes[0]['id'], 'right': nid, 'kind': 'public_record',
                          'evidence': [row], 'conflicts': [], 'decision': 'uncertain'})
    return {'nodes': nodes, 'edges': edges, 'truncated': len(raw) > 200,
            'limitation': 'Bağlantılar ve benzerlikler hesapların aynı kişiye ait olduğunu kanıtlamaz.'}


def _intelligence_records(row, kind):
    """Accommodate collection summaries and individual observation rows."""
    metadata = row.get('public_metadata', {})
    records = metadata.get('records', [])
    for record in (records if isinstance(records, list) else [])[:200]:
        if isinstance(record, dict):
            yield record
    if kind in ('brand', 'organization') and not records:
        observation = dict(metadata)
        observation.setdefault('url', row.get('url', ''))
        observation.setdefault('domain', metadata.get('candidate_domain') or metadata.get('linked_domain'))
        links = metadata.get('public_links', [])
        if kind == 'organization' and links:
            for link in links[:200]:
                yield {**observation, 'url': link}
        else:
            yield observation
    elif not records:
        for link in metadata.get('public_links', [])[:200]:
            yield {'url': link, 'source_url': metadata.get('source_url', row.get('url', ''))}


def _intelligence_graph(scan, decisions=None):
    """Source links describe observations, never ownership or identity."""
    from urllib.parse import urlsplit
    root = 'query:' + hashlib.sha256((scan['kind'] + scan['target']).encode()).hexdigest()[:20]
    nodes = [{'id': root, 'label': scan['target'], 'kind': 'query', 'url': ''}]
    edges, seen, truncated = [], {}, False
    relations = {'history': ('archive_capture', 'archive'), 'mentions': ('mention_candidate', 'publication'),
                 'brand': ('certificate_candidate', 'domain'), 'organization': ('published_link', 'domain')}
    relation, node_kind = relations[scan['kind']]
    for row in scan.get('rows', [])[:2000]:
        if str(row.get('status', '')).lower() not in ('found', 'possible'):
            continue
        for record in _intelligence_records(row, scan['kind']):
            if not isinstance(record, dict):
                continue
            url = next((value for key in ('archive_url', 'url', 'source_url') if (value := public_url(record.get(key)))), '')
            if not url:
                continue
            if (relation, url) in seen:
                node, edge = seen[(relation, url)]
                node['evidence'].update(deepcopy(record))
                if record.get('title'):
                    node['label'] = str(record['title'])
                if record != edge['evidence'][-1].get('record') and len(edge['evidence']) < 10:
                    extra_source = public_url(record.get('source_url')) or public_url(row.get('url')) or url
                    edge['evidence'].append({'label': 'Ek kaynak ayrıntısı; sahiplik kanıtı değildir',
                                             'source': extra_source,
                                             'record': deepcopy(record)})
                    if extra_source not in edge['sources']:
                        edge['sources'].append(extra_source)
                continue
            if len(nodes) >= 201:
                truncated = True
                continue
            nid = 'source:' + hashlib.sha256((relation + url).encode()).hexdigest()[:20]
            nodes.append({'id': nid, 'label': str(record.get('title') or record.get('domain') or urlsplit(url).hostname),
                          'kind': node_kind, 'url': url, 'evidence': deepcopy(record)})
            eid = root + ':' + nid
            source = public_url(record.get('source_url')) or public_url(row.get('url')) or url
            edges.append({'id': eid, 'left': root, 'right': nid, 'kind': relation,
                          'evidence': [{'label': 'Açık kaynak kaydı; sahiplik kanıtı değildir', 'source': source, 'record': deepcopy(record)}],
                          'sources': [source], 'conflicts': [], 'decision': (decisions or {}).get(eid, 'uncertain')})
            seen[(relation, url)] = (nodes[-1], edges[-1])
    return {'nodes': nodes, 'edges': edges, 'truncated': truncated,
            'limitation': 'Yayın, arşiv ve benzerlik kayıtları sahiplik veya kimlik kanıtı değildir.'}


def _event_time(value):
    """Normalize explicit source dates; collection time is handled separately."""
    if not isinstance(value, str) or len(value) > 50:
        return ''
    try:
        if len(value) == 14 and value.isdigit():
            parsed = datetime.strptime(value, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        elif len(value) == 10 and value[4:5] == '-' and value[7:8] == '-':
            parsed = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        elif 'T' in value:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return ''
        else:
            return ''
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return ''


def case_timeline(case):
    """At most 2000 sourced observations, sorted oldest first; dates retain meaning."""
    events, seen = [], {}
    for scan in case.get('scans', [])[:100]:
        collected = _event_time(scan.get('checked_at'))
        for row in scan.get('rows', [])[:2000]:
            if scan.get('kind') in INTELLIGENCE_KINDS and str(row.get('status', '')).lower() not in ('found', 'possible'):
                continue
            source = public_url(row.get('url'))
            for record in _intelligence_records(row, scan['kind']):
                if not isinstance(record, dict):
                    continue
                link = next((value for key in ('archive_url', 'url', 'source_url') if (value := public_url(record.get(key)))), '')
                if not link:
                    continue
                time, time_kind = '', ''
                date_keys = (('certificate_timestamp', 'certificate'), ('timestamp', 'archive'), ('archived_at', 'archive'), ('published_at', 'published'),
                             ('published', 'published'), ('date', 'source'))
                for key, meaning in date_keys:
                    time = _event_time(record.get(key))
                    if time:
                        time_kind = meaning
                        break
                if not time:
                    time, time_kind = collected, 'collected'
                if not time:
                    continue
                event = {'time': time, 'time_kind': time_kind, 'kind': scan['kind'], 'target': scan['target'],
                         'title': str(record.get('title') or record.get('domain') or row.get('platform') or row.get('service') or ''),
                         'url': link, 'source_url': public_url(record.get('source_url')) or source or link,
                         'checked_at': collected}
                key = (event['kind'], event['target'], time, time_kind, link)
                if key in seen:
                    if record.get('title'):
                        seen[key]['title'] = str(record['title'])
                elif len(events) < 2000:
                    seen[key] = event
                    events.append(event)
    return sorted(events, key=lambda item: (item['time'], item['kind'], item['target'], item['url']))


def export_case_html(path, case):
    """Self-contained escaped report, including analyst decisions and raw evidence."""
    from html import escape
    from utils.finding_reviews import review_for, REVIEW_STATES, VIEW_STATES, PRIORITIES
    validate_case(case)
    parts = ['<!doctype html><html lang="tr"><meta charset="utf-8"><title>Trackher araştırması</title>',
             '<style>body{background:#0c1420;color:#cad8e8;font:15px system-ui;max-width:1100px;margin:30px auto;padding:20px}section{background:#152130;padding:20px;margin:20px 0;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;color:#50d7e8}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #304459;text-align:left}a{color:#50d7e8}</style>',
             '<h1>' + escape(case['title']) + '</h1>', '<p>' + escape(', '.join(case.get('tags', []))) + '</p>',
             '<pre>' + escape(case.get('notes', '')) + '</pre>',
             '<p>İlişkiler sahiplik kanıtı değildir. Analist kararları yerel değerlendirmelerdir.</p>']
    timeline = case_timeline(case)
    parts.append('<section><h2>Kaynaklı zaman çizelgesi</h2><p>En fazla 2000 olay gösterilir. Toplama zamanı yayın veya arşiv tarihi değildir. Tarihsiz veya geçersiz tarihli kayıtlar yalnızca toplama zamanı ile gösterilir. Sınırlı kaynak kapsamı, olayın yokluğunu kanıtlamaz.</p><table><tr><th>Zaman ve türü</th><th>Bulgu</th><th>Kaynak</th></tr>')
    for event in timeline:
        # URLs have already passed public_url; escaping protects attribute context.
        parts.append('<tr><td>' + escape(event['time']) + ' · ' + escape(event['time_kind']) + '</td><td>' + escape(event['target'] + ' · ' + event['title']) + '</td><td><a rel="noreferrer noopener" href="' + escape(event['url'], quote=True) + '">Kayıt</a> · <a rel="noreferrer noopener" href="' + escape(event['source_url'], quote=True) + '">Kaynak</a></td></tr>')
    parts.append('</table></section>')
    for scan in case['scans']:
        graph = graph_for_scan(scan, case.get('decisions'))
        labels = {n['id']: n['label'] for n in graph['nodes']}
        parts.append('<section><h2>' + escape(scan['target']) + ' · ' + escape(scan['checked_at']) + '</h2>')
        parts.append('<p>Tür: ' + escape(scan['kind']) + ' · Durduruldu: ' + str(scan['stopped']) + '</p>')
        parts.append('<details><summary>Değişiklikler</summary><pre>' + escape(json.dumps(scan.get('diff', {}), ensure_ascii=False, indent=2)) + '</pre></details>')
        parts.append(f'<h3>İlişkiler ({len(graph["edges"])})</h3><p>İlk 1000 ilişki listelenir; ham bulgular aşağıda eksiksizdir.</p><table><tr><th>Bağlantı</th><th>Analist kararı</th><th>Kanıtlar ve çelişkiler</th></tr>')
        for edge in graph['edges'][:1000]:
            parts.append('<tr><td>' + escape(labels[edge['left']] + ' ↔ ' + labels[edge['right']]) + '</td><td>' + escape(edge['decision']) + '</td><td><pre>' + escape(json.dumps({'evidence': edge['evidence'], 'conflicts': edge['conflicts']}, ensure_ascii=False, indent=2)) + '</pre></td></tr>')
        parts.append('</table><h3>Kaynak bulgular</h3>')
        for row in scan['rows']:
            review = review_for(case, scan, row)
            review_html = '<p>Analist incelemesi: ' + escape(VIEW_STATES[review['view_state']]) + ' · Öncelik: ' + escape(PRIORITIES[review['priority']]) + '</p>'
            if review['stale']:
                review_html += '<p>Bu taramanın kanıtı inceleme yapılan sürümden farklıdır. Önceki karar: ' + escape(REVIEW_STATES[review['state']]) + '.</p>'
            review_html += '<p>Etiketler: ' + escape(', '.join(review['tags'])) + ' · İnceleme zamanı: ' + escape(review['updated_at']) + '</p><pre>' + escape(review['notes']) + '</pre>'
            parts.append('<details><summary>' + escape(str(row.get('platform') or row.get('service') or 'Record')) + ' · ' + escape(str(row.get('status', 'UNKNOWN'))) + '</summary>' + review_html + '<pre>' + escape(json.dumps(row, ensure_ascii=False, indent=2)) + '</pre></details>')
        parts.append('</section>')
    parts.append('</html>')
    Path(path).write_text(''.join(parts), encoding='utf-8')
