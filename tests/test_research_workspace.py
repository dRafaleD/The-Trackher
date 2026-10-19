import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from osint.scan_control import ScanControl, ScanStopped
from osint.domain_security import research_domain_security
from osint.username_checker import check_username_async
from osint.checker import check_email
from osint.services import check_haveibeenpwned
from utils.research import new_case, record_scan, save_case, load_case, graph_for_scan, compare_scans, export_case_html


def profile(site='A', **metadata):
    return {'platform': site, 'queried_username': 'sample', 'status': 'found', 'found': True,
            'reliability': 'verified', 'url': f'https://{site.lower()}.example/sample',
            'public_metadata': {'username': 'sample', **metadata}}


class CaseTests(unittest.TestCase):
    def test_retry_merge_retains_original_provenance_and_coverage_age(self):
        from gui.tabs.research import ResearchTabMixin
        app = ResearchTabMixin()
        first, second = profile('A'), profile('B')
        second['discovered_from'] = {'source_url': 'https://a.example/sample', 'depth': 1}
        app._retry_base = [first, second]
        updated = profile('B')
        updated['status'] = 'not_found'
        updated['found'] = False
        rows = app._merge_results([updated])
        self.assertTrue(rows[0]['retained_from_previous_scan'])
        self.assertNotIn('retained_from_previous_scan', rows[1])
        self.assertEqual(rows[1]['discovered_from'], second['discovered_from'])
        case = new_case()
        record_scan(case, 'username', 'sample', 'standard', [first, second])
        scan = record_scan(case, 'username', 'sample', 'standard', rows)
        self.assertTrue(scan['diff']['coverage_changed'])

    def test_roundtrip_preserves_notes_tags_decisions_and_all_results(self):
        case = new_case('Case')
        case.update(notes='Private local notes', tags=['test'])
        record_scan(case, 'username', 'sample', 'standard', [profile()])
        case['decisions']['a:b'] = 'unrelated'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.trackher.json'
            save_case(path, case)
            self.assertEqual(load_case(path), case)

    def test_failed_atomic_replace_keeps_old_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.json'
            path.write_text('previous', encoding='utf-8')
            with patch('utils.research.os.replace', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    save_case(path, new_case())
            self.assertEqual(path.read_text(), 'previous')
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_import_rejects_invalid_nested_shapes_and_size(self):
        case = new_case()
        record_scan(case, 'username', 'sample', 'standard', [profile()])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            for mutate in (lambda c: c['scans'][0].pop('checked_at'),
                           lambda c: c['scans'][0]['rows'][0].update(public_metadata=[]),
                           lambda c: c.update(decisions={'edge': 'confirmed_identity'})):
                invalid = deepcopy(case)
                mutate(invalid)
                path.write_text(json.dumps(invalid), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_case(path)
            path.write_bytes(b'x' * 101)
            with patch('utils.research.MAX_CASE_BYTES', 100), self.assertRaises(ValueError):
                load_case(path)

    def test_missing_coverage_or_field_never_means_deleted_profile(self):
        case = new_case()
        old = record_scan(case, 'username', 'sample', 'standard', [profile('A', bio='old'), profile('B')])
        new = record_scan(case, 'username', 'sample', 'standard', [profile('A')])
        self.assertTrue(new['diff']['coverage_changed'])
        self.assertEqual(new['diff']['uncovered'], ['B|sample'])
        self.assertEqual(new['diff']['changes'], [{'site': 'A|sample', 'type': 'field_unavailable', 'field': 'bio'}])
        row = profile('A')
        row.update(status='unknown', found=False, unknown_cause='bot_blocked')
        new = record_scan(case, 'username', 'sample', 'standard', [row])
        self.assertEqual(new['diff']['changes'][0]['type'], 'unavailable')

    def test_field_changes_and_separate_handles_on_one_platform(self):
        case = new_case()
        old = record_scan(case, 'username', 'sample', 'standard', [profile(bio='before', public_links=['https://personal.example/'])])
        new = record_scan(case, 'username', 'sample', 'standard', [profile(bio='after', public_links=[])])
        self.assertEqual({c['field'] for c in new['diff']['changes']}, {'bio', 'public_links'})
        second = profile()
        second['queried_username'] = 'different'
        diff = compare_scans(old, {'profile': 'standard', 'rows': [profile(), second]})
        self.assertEqual(sum(c['type'] == 'new_profile' for c in diff['changes']), 1)

    def test_graph_keeps_conflicts_and_analyst_decision_with_source_evidence(self):
        case = new_case()
        scan = record_scan(case, 'username', 'sample', 'standard', [profile('A', display_name='Alice Smith'), profile('B', display_name='Zzz Qqq')])
        graph = graph_for_scan(scan)
        edge = next(e for e in graph['edges'] if e['kind'] == 'candidate')
        self.assertTrue(edge['conflicts'])
        self.assertEqual(len(edge['sources']), 2)
        decided = graph_for_scan(scan, {edge['id']: 'unrelated'})
        self.assertEqual(next(e for e in decided['edges'] if e['id'] == edge['id'])['decision'], 'unrelated')
        self.assertTrue(any(n['kind'] == 'query' for n in graph['nodes']))
        self.assertEqual(scan['rows'][0]['status'], 'found')

    def test_graph_declared_domain_links_do_not_fetch_or_claim_identity(self):
        case = new_case()
        scan = record_scan(case, 'username', 'sample', 'standard', [profile(public_links=['https://personal.example/bio', 'http://127.0.0.1/'])])
        graph = graph_for_scan(scan)
        self.assertEqual([n['label'] for n in graph['nodes'] if n['kind'] == 'domain'], ['personal.example'])
        self.assertTrue(any(e['kind'] == 'declared_link' for e in graph['edges']))

    def test_html_case_report_escapes_untrusted_notes_and_metadata(self):
        case = new_case('<script>title</script>')
        case['notes'] = '<img src=x onerror=alert(1)>'
        record_scan(case, 'username', 'sample', 'standard', [profile(bio='<script>bio</script>')])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.html'
            export_case_html(path, case)
            text = path.read_text(encoding='utf-8')
        self.assertNotIn('<script>', text)
        self.assertNotIn('<img', text)
        self.assertIn('&lt;script&gt;bio', text)


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_paused_jobs_do_not_start_and_resume_releases_them(self):
        control = ScanControl()
        control.paused.set()
        started = asyncio.Event()
        async def work():
            started.set()
            return 'done'
        task = asyncio.create_task(control.run('Site', work))
        await asyncio.sleep(.08)
        self.assertFalse(started.is_set())
        control.paused.clear()
        self.assertEqual(await asyncio.wait_for(task, 1), 'done')
        self.assertEqual(control.snapshot()['jobs'][0]['state'], 'done')

    async def test_stop_cancels_inflight_and_waiting_jobs_without_orphans(self):
        control = ScanControl()
        semaphore = asyncio.Semaphore(1)
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def work():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        tasks = [asyncio.create_task(control.run(str(i), work, semaphore)) for i in range(3)]
        await started.wait()
        control.stopped.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 1)
        self.assertTrue(all(isinstance(r, ScanStopped) for r in results))
        self.assertTrue(cancelled.is_set())
        self.assertTrue(all(j['state'] == 'stopped' for j in control.snapshot()['jobs']))
        self.assertEqual(semaphore._value, 1)

    async def test_username_retry_uses_exact_catalog_handle_pairs(self):
        catalog = [{'name': 'GitHub', 'url': 'https://github.com/{}', 'reference_username': 'octocat'}]
        calls = []
        async def check(handle, plat, client):
            calls.append((handle, plat['name']))
            return {'platform': plat['name'], 'queried_username': handle, 'status': 'not_found', 'found': False}
        with patch('osint.username_checker.USERNAME_PLATFORMS', catalog), patch('osint.username_checker.select_username_platforms', return_value=catalog), patch('osint.username_checker.check_single_username', side_effect=check):
            results = await check_username_async('original', control=ScanControl(), only_queries=[('GitHub', 'one'), ('GitHub', 'two'), ('Other', 'ignored'), ('GitHub', 'one')])
        self.assertCountEqual(calls, [('one', 'GitHub'), ('two', 'GitHub')])
        self.assertEqual(len(results), 2)

    async def test_username_stop_returns_every_pending_site_as_unknown(self):
        catalog = [{'name': n, 'url': 'https://example.com/{}'} for n in ('A', 'B')]
        control = ScanControl()
        control.stopped.set()
        with patch('osint.username_checker.select_username_platforms', return_value=catalog):
            rows = await check_username_async('sample', control=control)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['status'] == 'unknown' and r['unknown_cause'] == 'cancelled' for r in rows))

    async def test_email_stopped_still_streams_all_sections_and_preserves_status(self):
        control = ScanControl()
        control.stopped.set()
        seen = []
        with patch('osint.checker.select_email_platforms', return_value=([{'name': 'A'}], [{'name': 'B'}])):
            data = await check_email('me@example.com', control=control, on_result=seen.append)
        self.assertEqual(len(seen), 3)
        self.assertEqual({r['section'] for r in seen}, {'account', 'breach', 'domain'})
        self.assertTrue(all(r['status'] == 'UNKNOWN' for r in seen))
        self.assertEqual(data['accounts'][0]['unknown_cause'], 'cancelled')


class DomainAndBreachTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresolved_cname_is_not_reported_as_missing_policy(self):
        def handler(request):
            return httpx.Response(200, json={'Status': 0, 'Answer': [{'name': 'example.com', 'type': 5, 'data': 'other.example.net.'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain_security('example.com', client, certificates=False)
        self.assertEqual(result['SPF']['status'], 'UNKNOWN')
        self.assertNotIn('assessment', result['SPF'])

    async def test_security_txt_chunks_dmarc_and_authenticated_dnssec(self):
        def handler(request):
            name, kind = request.url.params['name'], request.url.params['type']
            text = '"v=DMARC1; p=reject"' if name.startswith('_dmarc') else '"v=spf1 " "-all"'
            return httpx.Response(200, json={'Status': 0, 'AD': True, 'Answer': [{'name': name + '.', 'type': 48 if kind == 'DNSKEY' else 16, 'data': text}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain_security('example.com', client, certificates=False)
        self.assertEqual(result['SPF']['records'], ['v=spf1 -all'])
        self.assertEqual(result['DMARC']['assessment'], 'enforcement_policy')
        self.assertEqual(result['DNSSEC']['assessment'], 'validated_by_resolver')
        self.assertEqual(result['Certificate transparency']['status'], 'NOT_REQUESTED')

    async def test_duplicate_missing_and_unvalidated_records_remain_distinct(self):
        def handler(request):
            name, kind = request.url.params['name'], request.url.params['type']
            answers = [{'name': name, 'type': 16, 'data': '"v=spf1 +all"'}] * 2 if name == 'example.com' and kind == 'TXT' else []
            return httpx.Response(200, json={'Status': 0, 'AD': False, 'Answer': answers})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain_security('example.com', client, certificates=False)
        self.assertEqual(result['SPF']['assessment'], 'multiple_records')
        self.assertEqual(result['DMARC']['assessment'], 'missing')
        self.assertEqual(result['DNSSEC']['assessment'], 'not_authenticated')

    async def test_ct_deduplicates_exact_domain_scope_and_never_visits_hosts(self):
        requests = []
        def handler(request):
            requests.append(str(request.url))
            if request.url.host == 'crt.sh':
                return httpx.Response(200, json=[{'name_value': '*.dev.example.com\ndev.example.com\nexample.com.evil.org\nlocalhost\nhttps://evil.org/x\napi.example.com'}])
            return httpx.Response(200, json={'Status': 0})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain_security('example.com', client)
        ct = result['Certificate transparency']
        self.assertEqual(ct['names'], ['api.example.com', 'dev.example.com'])
        self.assertEqual(len(requests), 4)
        self.assertTrue(all('crt.sh' in u or 'dns.google' in u for u in requests))

    async def test_ct_failure_does_not_turn_into_no_records(self):
        def handler(request):
            return httpx.Response(503) if request.url.host == 'crt.sh' else httpx.Response(200, json={'Status': 2})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain_security('example.com', client)
        self.assertTrue(all(r['status'] == 'UNKNOWN' for r in result.values()))

    async def test_hibp_full_metadata_is_sanitized_and_keeps_legacy_names(self):
        def handler(request):
            self.assertEqual(request.url.params['truncateResponse'], 'false')
            return httpx.Response(200, json=[{'Name': 'Example', 'Title': 'Example incident', 'BreachDate': '2020-01-01', 'AddedDate': '2020-02-01', 'DataClasses': ['Email addresses'], 'IsVerified': True, 'Description': '<script>ignored</script>'}])
        with patch.dict(os.environ, {'HIBP_API_KEY': 'a' * 32}):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                result = await check_haveibeenpwned('me@example.com', client)
        self.assertEqual(result['breaches'], ['Example'])
        self.assertEqual(result['breach_details'][0]['breach_date'], '2020-01-01')
        self.assertNotIn('Description', result['breach_details'][0])
        self.assertEqual(result['status'], 'FOUND')


if __name__ == '__main__':
    unittest.main()
