from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from utils.research import (case_timeline, compare_scans, export_case_html, graph_for_scan,
                            load_case, new_case, record_scan, save_case)


def finding(records=None, **values):
    return {'platform': 'Public source', 'queried_username': 'example.org', 'status': 'found',
            'url': 'https://source.example/search',
            'public_metadata': {'records': records or [], 'public_links': []}, **values}


class IntelligenceCaseTests(unittest.TestCase):
    def test_archived_page_enrichment_survives_index_deduplication(self):
        case = new_case()
        capture = {'archive_url': 'https://web.archive.org/web/20200101000000/https://example.org/',
                   'url': 'https://example.org/', 'timestamp': '2020-01-01T00:00:00Z'}
        index = finding([capture], platform='Web history')
        page = finding([{**capture, 'title': 'Actual archived title', 'public_links': ['https://other.example/']}],
                       platform='Archive comparison')
        scan = record_scan(case, 'history', 'example.org', 'standard', [index, page])
        graph = graph_for_scan(scan)
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['nodes'][1]['label'], 'Actual archived title')
        self.assertEqual(graph['nodes'][1]['evidence']['public_links'], ['https://other.example/'])
        self.assertEqual(len(case_timeline(case)), 1)
        self.assertEqual(case_timeline(case)[0]['title'], 'Actual archived title')

    def test_roundtrip_new_kinds_and_collection_diff(self):
        case = new_case('Intelligence')
        for kind in ('history', 'brand', 'organization', 'mentions'):
            record_scan(case, kind, 'example.org', 'standard', [finding()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.json'
            save_case(path, case)
            self.assertEqual(load_case(path), case)
        previous = deepcopy(case['scans'][0])
        current = deepcopy(previous)
        current['rows'].append(finding(platform='Additional archive'))
        self.assertEqual(compare_scans(previous, current)['changes'][0]['type'], 'new_record')
        current['rows'] = []
        difference = compare_scans(previous, current)
        self.assertEqual(difference['changes'], [])
        self.assertTrue(difference['uncovered'])

    def test_graph_observations_are_explicit_not_ownership(self):
        for kind, relationship in (('history', 'archive_capture'), ('brand', 'certificate_candidate'),
                                   ('organization', 'published_link'), ('mentions', 'mention_candidate')):
            case = new_case()
            row = finding([{'url': 'https://linked.example/page', 'title': 'Public record'}])
            scan = record_scan(case, kind, 'example.org', 'standard', [row, row])
            graph = graph_for_scan(scan)
            self.assertEqual(len(graph['edges']), 1)
            self.assertEqual(graph['edges'][0]['kind'], relationship)
            self.assertEqual(graph['edges'][0]['decision'], 'uncertain')
            self.assertNotIn('profile', {n['kind'] for n in graph['nodes']})

    def test_individual_brand_and_organization_metadata(self):
        case = new_case()
        brand = finding(public_metadata={'source_url': 'https://crt.sh/?q=example.org',
                        'candidate_domain': 'examp1e.org', 'certificate_timestamp': '2024-01-01T00:00:00Z'},
                        url='https://examp1e.org/', status='possible')
        scan = record_scan(case, 'brand', 'example.org', 'standard', [brand])
        self.assertEqual(graph_for_scan(scan)['nodes'][1]['label'], 'examp1e.org')
        self.assertEqual(case_timeline(case)[0]['time_kind'], 'certificate')
        organization = finding(public_metadata={'source_url': 'https://example.org/',
                               'public_links': ['https://social.example/official'],
                               'linked_domain': 'social.example'})
        scan = record_scan(case, 'organization', 'example.org', 'standard', [organization])
        self.assertEqual(graph_for_scan(scan)['nodes'][1]['url'], 'https://social.example/official')
        self.assertEqual(case_timeline(case)[-1]['source_url'], 'https://example.org/')

    def test_possible_intelligence_diff_and_unavailable_rows(self):
        case = new_case()
        candidate = finding(status='possible', public_metadata={
            'candidate_domain': 'examp1e.org', 'source_url': 'https://crt.sh/?q=example.org'})
        old = record_scan(case, 'brand', 'example.org', 'standard', [])
        current = record_scan(case, 'brand', 'example.org', 'standard', [candidate])
        self.assertEqual(current['diff']['changes'][0]['type'], 'new_record')
        updated = deepcopy(candidate)
        updated['public_metadata']['candidate_domain'] = 'examp1e.net'
        next_scan = record_scan(case, 'brand', 'example.org', 'standard', [updated])
        self.assertIn('candidate_domain', {c.get('field') for c in next_scan['diff']['changes']})
        for kind in ('brand', 'organization', 'history', 'mentions'):
            for status in ('unknown', 'not_found', 'error', 'not_configured'):
                empty = new_case()
                scan = record_scan(empty, kind, 'example.org', 'standard', [finding(status=status)])
                self.assertEqual(case_timeline(empty), [])
                self.assertEqual(graph_for_scan(scan)['edges'], [])
        # Existing account searches must not promote a possible candidate to found.
        previous = {'kind': 'username', 'profile': 'standard', 'rows': []}
        self.assertEqual(compare_scans(previous, {**previous, 'rows': [candidate]})['changes'], [])

    def test_timeline_dates_sources_dedup_and_order(self):
        case = new_case()
        records = [
            {'url': 'https://news.example/new', 'published_at': '2024-04-01T12:00:00Z'},
            {'archive_url': 'https://archive.example/old', 'timestamp': '20010102030405'},
            {'url': 'https://news.example/invalid', 'date': '2024-02-30'},
            {'url': 'https://news.example/local', 'published_at': '2020-01-01T12:00:00'},
            {'url': 'javascript:alert(1)', 'date': '2024-01-01'},
        ]
        scan = record_scan(case, 'history', 'example.org', 'standard', [finding(records), finding(records)])
        scan['checked_at'] = '2026-10-17T10:00:00+00:00'
        events = case_timeline(case)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0]['time'], '2001-01-02T03:04:05+00:00')
        self.assertEqual(events[0]['time_kind'], 'archive')
        self.assertEqual(events[1]['time_kind'], 'published')
        self.assertEqual({e['time_kind'] for e in events[2:]}, {'collected'})
        self.assertTrue(all(e['source_url'] == 'https://source.example/search' for e in events))

    def test_html_escapes_titles_notes_and_rejects_unsafe_links(self):
        case = new_case('<script>title</script>')
        case['notes'] = '<img src=x onerror=alert(1)>'
        scan = record_scan(case, 'mentions', 'example.org', 'standard', [finding([
            {'url': 'https://news.example/article?q="x"', 'title': '<script>record</script>', 'date': '2025-01-01'},
            {'url': 'javascript:alert(1)', 'date': '2025-01-01'},
        ])])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.html'
            export_case_html(path, case)
            content = path.read_text(encoding='utf-8')
        self.assertIn('Kaynaklı zaman çizelgesi', content)
        self.assertIn('&lt;script&gt;record&lt;/script&gt;', content)
        self.assertNotIn('<script>', content)
        self.assertNotIn('href="javascript:', content)
        self.assertIn('Toplama zamanı yayın veya arşiv tarihi değildir', content)

    def test_timeline_is_bounded_and_graph_records_coverage(self):
        case = new_case()
        scan = record_scan(case, 'mentions', 'example.org', 'standard', [finding([
            {'url': f'https://news.example/{i}', 'date': '2024-01-01'} for i in range(220)
        ]) for _ in range(12)])
        self.assertLessEqual(len(case_timeline(case)), 2000)
        self.assertLessEqual(len(graph_for_scan(scan)['nodes']), 201)


if __name__ == '__main__':
    unittest.main()
