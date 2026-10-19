"""Small, explicit public-source research jobs sharing the case result contract."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib

from osint.domain_research import normalize_domain
from osint.scan_control import ScanStopped
from utils.public_data import public_url


RESEARCH_MODES = {
    'history': 'Web sitesi geçmişi',
    'brand': 'Marka ve taklit adayları',
    'organization': 'Kurumsal dijital ayak izi',
    'mentions': 'Açık kaynaklarda bahsedilme',
}


def normalize_target(kind, target):
    if kind not in RESEARCH_MODES:
        raise ValueError('Bilinmeyen araştırma türü')
    if kind != 'mentions':
        return normalize_domain(target)
    if not isinstance(target, str):
        raise ValueError('Bir marka, kurum veya alan adı girin')
    if any(ord(c) < 32 or ord(c) == 127 for c in target):
        raise ValueError('Araştırma ifadesi kontrol karakterleri içeremez')
    target = ' '.join(target.split())
    if not 2 <= len(target) <= 160:
        raise ValueError('Araştırma ifadesi 2–160 karakter olmalı')
    return target


def expand_records(rows, target):
    """Keep provider coverage and make each collected record inspectable in the UI."""
    expanded = []
    for original in rows[:100]:
        row = deepcopy(original)
        row.setdefault('queried_username', target)
        row.setdefault('checked_at', datetime.now(timezone.utc).isoformat())
        metadata = row.get('public_metadata', {})
        records = metadata.get('records', [])
        if not row.get('detail') and isinstance(records, list):
            row['detail'] = f'{len(records)} kaynak kaydı' + (' · İlgisi doğrulanmamış adaylar' if kind_is_candidate(row) else '')
        direct_label = metadata.get('candidate_domain') or metadata.get('linked_domain')
        if direct_label:
            identity = hashlib.sha256(str(row.get('url', '')).encode()).hexdigest()[:12]
            row['platform'] = f"{row.get('platform') or 'Kaynak'} · {direct_label} [{identity}]"
        if kind_is_candidate(row) and str(row.get('status', '')).lower() == 'found':
            row['status'] = 'possible'
            row['found'] = False
        expanded.append(row)
        records = row.get('public_metadata', {}).get('records', [])
        if not isinstance(records, list):
            continue
        seen = set()
        for record in records[:30]:
            if not isinstance(record, dict):
                continue
            url = next((public_url(record.get(k)) for k in ('archive_url', 'url', 'source_url') if public_url(record.get(k))), '')
            label = str(record.get('title') or record.get('domain') or record.get('timestamp') or record.get('name') or url)[:100]
            fingerprint = hashlib.sha256((url + str(record.get('timestamp', ''))).encode()).hexdigest()[:12]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            expanded.append({
                'platform': f"{row.get('platform') or row.get('service') or 'Kaynak'} · {label} [{fingerprint}]",
                'queried_username': target, 'url': url,
                'status': 'possible' if kind_is_candidate(row) else 'found',
                'found': not kind_is_candidate(row),
                'detail': str(record.get('reason') or record.get('title') or row.get('detail') or label),
                'checked_at': row['checked_at'], 'evidence_type': row.get('evidence_type', 'public_record'),
                'research_kind': row.get('research_kind', ''),
                'public_metadata': {'records': [deepcopy(record)], 'source_url': row.get('url', ''),
                                    'limitations': row.get('public_metadata', {}).get('limitations', '')},
            })
    return expanded


def kind_is_candidate(row):
    return row.get('research_kind') in ('brand', 'mentions')


async def research_public(kind, target, *, client=None, control=None, on_result=None):
    target = normalize_target(kind, target)
    from osint.web_history import research_history, research_mentions
    from osint.organization import research_brand, research_organization
    jobs = {'history': research_history, 'mentions': research_mentions,
            'brand': research_brand, 'organization': research_organization}
    collected = []

    def stream(row):
        copied = deepcopy(row)
        copied['research_kind'] = kind
        collected.append(copied)
        if on_result:
            for result in expand_records([copied], target):
                on_result(result)

    async def bounded():
        kwargs = {'inspect_pages': True, 'on_result': stream} if kind == 'history' else {}
        return await asyncio.wait_for(jobs[kind](target, client=client, **kwargs), timeout=35)

    try:
        rows = await control.run(RESEARCH_MODES[kind], bounded) if control else await bounded()
    except (ScanStopped, asyncio.TimeoutError) as exc:
        cause = 'cancelled' if isinstance(exc, ScanStopped) else 'timeout'
        rows = collected + [{'platform': RESEARCH_MODES[kind], 'status': 'unknown', 'url': '',
                 'unknown_cause': cause, 'detail': 'Tarama durduruldu' if cause == 'cancelled' else 'Kaynak yanıt süresi aşıldı'}]
    for row in rows:
        row['research_kind'] = kind
    results = expand_records(rows, target)
    if on_result:
        for row in results:
            on_result(row)
    return results
