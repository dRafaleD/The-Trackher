"""Analyst annotations, independent of machine detection and identity claims."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata


REVIEW_STATES = {'new': 'Bekliyor', 'reviewed': 'İncelendi', 'rejected': 'İlgisiz', 'uncertain': 'Kararsız'}
VIEW_STATES = {**REVIEW_STATES, 'stale': 'Kanıt değişti'}
PRIORITIES = {'high': 'Yüksek', 'normal': 'Normal', 'low': 'Düşük'}
MAX_NOTES = 20_000
MAX_TAGS = 30


def search_text(value):
    """Accent-insensitive UI search, including Turkish dotted/dotless I."""
    text = unicodedata.normalize('NFKD', str(value)).casefold()
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('ı', 'i')


def finding_id(scan, result, *, legacy=False):
    """Keep annotations across rescans, without mixing targets or linked handles."""
    target = scan['target'].strip()
    if scan['kind'] in ('email', 'domain'):
        target = target.casefold()
    section = str(result.get('section') or ('account' if scan['kind'] == 'email' else ''))
    handle = str(result.get('queried_username') or (scan['target'] if scan['kind'] == 'username' else ''))
    identity = [scan['kind'], target, section,
                str(result.get('platform') or result.get('service') or 'Domain'),
                handle]
    if not legacy and scan['kind'] in ('history', 'brand', 'organization', 'mentions'):
        from utils.public_data import research_key
        identity[3] = research_key(dict(result, research_kind=scan['kind']))
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()


def evidence_fingerprint(result):
    """Ignore check timestamps while detecting changes to actual source evidence."""
    fields = ('status', 'found', 'url', 'queried_username', 'unknown_cause', 'diagnostic_cause', 'public_metadata', 'field_sources', 'detector_used')
    value = {key: result[key] for key in fields if key in result}
    card = result.get('evidence_card', {})
    value['evidence_source'] = {k: card.get(k) for k in ('rule_fingerprint', 'source_url', 'http_status', 'detector')}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def validate_reviews(reviews):
    if not isinstance(reviews, dict) or len(reviews) > 200_000:
        raise ValueError('Geçersiz bulgu inceleme listesi')
    for key, value in reviews.items():
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key) or not isinstance(value, dict):
            raise ValueError('Geçersiz bulgu inceleme kaydı')
        if not isinstance(value.get('state'), str) or not isinstance(value.get('priority'), str) or value['state'] not in REVIEW_STATES or value['priority'] not in PRIORITIES:
            raise ValueError('Geçersiz inceleme durumu veya önceliği')
        if not isinstance(value.get('notes'), str) or len(value['notes']) > MAX_NOTES:
            raise ValueError('Bulgu notu en fazla 20000 karakter olabilir')
        tags = value.get('tags')
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and 0 < len(t) <= 80 for t in tags):
            raise ValueError('Geçersiz bulgu etiketleri')
        if not isinstance(value.get('evidence_fingerprint'), str) or not re.fullmatch(r'[0-9a-f]{64}', value['evidence_fingerprint']):
            raise ValueError('Geçersiz kanıt özeti')
        try:
            timestamp = datetime.fromisoformat(value['updated_at'])
            if timestamp.tzinfo is None:
                raise ValueError('Saat dilimi eksik')
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Geçersiz inceleme zamanı') from exc
    return reviews


def review_for(case, scan, result):
    review = deepcopy(case.get('reviews', {}).get(finding_id(scan, result)))
    # Earlier local versions used the mutable displayed title as the key. Keep
    # those annotations available when the same source returns with a new title.
    if review is None and case.get('reviews') and scan['kind'] in ('history', 'brand', 'organization', 'mentions'):
        reviews = case['reviews']
        review = deepcopy(reviews.get(finding_id(scan, result, legacy=True)))
        if review is None:
            key = finding_id(scan, result)
            for previous in reversed(case.get('scans', [])):
                if previous.get('kind') != scan['kind'] or previous.get('target') != scan['target']:
                    continue
                for old in previous.get('rows', []):
                    old_review = reviews.get(finding_id(previous, old, legacy=True))
                    if old_review and finding_id(previous, old) == key:
                        review = deepcopy(old_review)
                        break
                if review is not None:
                    break
    if review is None:
        review = {'state': 'new', 'priority': 'normal', 'notes': '', 'tags': [], 'updated_at': ''}
    stale = bool(review.get('evidence_fingerprint') and review['evidence_fingerprint'] != evidence_fingerprint(result))
    return {**review, 'stale': stale, 'view_state': 'stale' if stale else review['state']}


def set_review(case, scan, result, *, state='new', priority='normal', notes='', tags=None):
    if not isinstance(tags, (list, tuple, type(None))):
        raise ValueError('Etiketleri liste olarak girin')
    if tags is not None and not all(isinstance(t, str) for t in tags):
        raise ValueError('Etiketler metin olmalıdır')
    normalized = list(dict.fromkeys(t.strip() for t in (tags or []) if t.strip()))
    review = {'state': state, 'priority': priority, 'notes': notes, 'tags': normalized,
              'updated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              'evidence_fingerprint': evidence_fingerprint(result)}
    key = finding_id(scan, result)
    validate_reviews({key: review})
    case.setdefault('reviews', {})[key] = review
    return review


def review_rows(case, scan, *, query='', state='all', priority='all'):
    if scan is None:
        return []
    needle = search_text(query.strip())
    rows = []
    for index, result in enumerate(scan['rows']):
        review = review_for(case, scan, result)
        if state != 'all' and review['view_state'] != state:
            continue
        if priority != 'all' and review['priority'] != priority:
            continue
        site = str(result.get('platform') or result.get('service') or 'Domain')
        handle = str(result.get('queried_username') or scan['target'])
        status = str(result.get('status', 'unknown'))
        text = ' '.join([site, handle, status, str(result.get('detail', '')), str(result.get('url', '')),
                         review['notes'], *review['tags'], VIEW_STATES[review['view_state']], PRIORITIES[review['priority']]])
        if needle and needle not in search_text(text):
            continue
        rows.append({'id': finding_id(scan, result), 'index': index, 'site': site, 'handle': handle,
                     'detection': status, 'url': str(result.get('url', '')), 'review': review, 'result': result})
    return rows


def _csv_cell(value):
    text = str(value)
    # Spreadsheet programs may evaluate formulas even in quoted CSV cells.
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def export_reviews_csv(path, rows):
    fields = ('site', 'handle', 'detection', 'review_state', 'analyst_state', 'priority', 'tags', 'notes', 'evidence_changed', 'reviewed_at', 'source_url')
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for row in rows:
            review = row['review']
            values = [row['site'], row['handle'], row['detection'], VIEW_STATES[review['view_state']], REVIEW_STATES[review['state']],
                      PRIORITIES[review['priority']], ', '.join(review['tags']), review['notes'],
                      str(review['stale']), review['updated_at'], row['url']]
            writer.writerow([_csv_cell(value) for value in values])
