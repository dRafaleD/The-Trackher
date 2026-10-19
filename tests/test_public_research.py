"""New research modules must retain candidate semantics and every visible record."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from osint.intelligence import expand_records, normalize_target, research_public
from osint.evidence import evidence_card
from osint.scan_control import ScanControl
from utils.research import new_case, record_scan, graph_for_scan, case_timeline
from utils.research import result_key
from utils.finding_reviews import finding_id, set_review, review_for


class PublicResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_title_change_keeps_source_identity_and_legacy_notes(self):
        def rows(title):
            return expand_records([{'platform': 'Public mentions', 'status': 'found', 'research_kind': 'mentions',
                'evidence_type': 'news_index', 'url': 'https://news.google.com/rss/search?q=brand',
                'public_metadata': {'records': [{'title': title, 'url': 'https://news.example/article'}]}}], 'brand')
        case = new_case()
        old = record_scan(case, 'mentions', 'brand', 'standard', rows('First title'))
        review = set_review(case, old, old['rows'][1], state='reviewed', notes='Keep this source note')
        case['reviews'] = {finding_id(old, old['rows'][1], legacy=True): review}
        latest = record_scan(case, 'mentions', 'brand', 'standard', rows('Corrected title'))
        self.assertEqual(result_key(old['rows'][1]), result_key(latest['rows'][1]))
        self.assertNotIn('new_record', {c['type'] for c in latest['diff']['changes']})
        annotation = review_for(case, latest, latest['rows'][1])
        self.assertEqual(annotation['notes'], 'Keep this source note')
        self.assertTrue(annotation['stale'])

    async def test_cancel_during_comparison_retains_already_streamed_index(self):
        control = ScanControl()
        async def history(target, **kwargs):
            kwargs['on_result']({'platform': 'Web history', 'url': 'https://web.archive.org/cdx/search/cdx',
                'status': 'found', 'evidence_type': 'archive_index', 'public_metadata': {'records': [
                    {'url': 'https://example.com/', 'archive_url': 'https://web.archive.org/web/20200101000000/https://example.com/',
                     'timestamp': '2020-01-01T00:00:00Z'}]}})
            control.stopped.set()
            await asyncio.sleep(5)
        streamed = []
        with patch('osint.web_history.research_history', side_effect=history):
            results = await research_public('history', 'example.com', control=control, on_result=streamed.append)
        self.assertTrue(any(r['status'] == 'found' for r in results))
        self.assertTrue(any(r.get('unknown_cause') == 'cancelled' for r in results))
        self.assertTrue(any(r['status'] == 'found' for r in streamed))
        self.assertEqual(len({result_key(r) for r in results}), len(results))

    async def test_control_characters_rejected_before_query_normalization(self):
        for value in ('sample\nbrand', 'brand\tname', 'brand\x7fname'):
            with self.assertRaises(ValueError):
                normalize_target('mentions', value)

    async def test_all_thirty_organization_links_survive_result_identity(self):
        rows = [{'platform': 'Organization footprint', 'url': f'https://external{i}.example/about',
                 'status': 'found', 'public_metadata': {'linked_domain': f'external{i}.example',
                    'public_links': [f'https://external{i}.example/about'], 'source_url': 'https://company.example/'}}
                for i in range(30)]
        with patch('osint.organization.research_organization', new=AsyncMock(return_value=rows)):
            results = await research_public('organization', 'company.example')
        self.assertEqual(len(results), 30)
        from utils.research import result_key
        self.assertEqual(len({result_key(r) for r in results}), 30)
        self.assertTrue(all(evidence_card(r)['identity_claim'] == 'public_record_only' for r in results))

    async def test_candidates_remain_candidates_in_case_graph_and_diffs(self):
        summary = {'platform': 'Public mentions', 'url': 'https://news.google.com/rss/search?q=brand',
                   'status': 'found', 'public_metadata': {'records': [
                      {'title': 'Brand mention', 'url': 'https://news.example/article',
                       'published': '2026-01-01T00:00:00Z', 'relevance': 'unverified'}]}}
        with patch('osint.web_history.research_mentions', new=AsyncMock(return_value=[summary])):
            rows = await research_public('mentions', 'brand')
        self.assertEqual([r['status'] for r in rows], ['possible', 'possible'])
        self.assertTrue(all(evidence_card(r)['identity_claim'] == 'candidate_only' for r in rows))
        case = new_case()
        scan = record_scan(case, 'mentions', 'brand', 'standard', rows)
        graph = graph_for_scan(scan)
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['edges'][0]['kind'], 'mention_candidate')
        self.assertEqual(len(case_timeline(case)), 1)
        record_scan(case, 'mentions', 'brand', 'standard', [])
        latest = record_scan(case, 'mentions', 'brand', 'standard', rows)
        self.assertEqual({c['type'] for c in latest['diff']['changes']}, {'new_record'})

    async def test_stopped_job_makes_no_network_request_and_keeps_unknown(self):
        control = ScanControl()
        control.stopped.set()
        job = AsyncMock()
        with patch('osint.web_history.research_history', new=job):
            results = await research_public('history', 'example.com', control=control)
        job.assert_not_called()
        self.assertEqual(results[0]['unknown_cause'], 'cancelled')
        self.assertEqual(results[0]['status'], 'unknown')

    async def test_worker_streams_and_finishes_through_main_thread_queue(self):
        from test_gui_memory import GuiMemoryTests
        app = GuiMemoryTests().make_app()
        app.post_ui = Mock()
        app.print_to_terminal = Mock()
        rows = [{'platform': 'Web history', 'status': 'unknown'}]
        async def scan(kind, target, **kwargs):
            kwargs['on_result'](rows[0])
            return rows
        # Worker owns its own event loop, so call outside this test's running loop.
        with patch('gui.tabs.intelligence.research_public', side_effect=scan):
            await asyncio.to_thread(app.do_intelligence_research, 'history', 'example.com')
        app.post_ui.assert_any_call(app._receive_scan_result, rows[0])
        app.post_ui.assert_any_call(app._complete_scan_results, rows)
        app.post_ui.assert_any_call(app._release_scan_results)


class ResearchCliTests(unittest.TestCase):
    def test_new_action_runs_without_profile_lookup_and_exports_html(self):
        import main
        rows = [{'platform': '<candidate>', 'status': 'possible', 'url': 'https://news.example/article',
                 'public_metadata': {}}]
        with tempfile.TemporaryDirectory() as folder:
            old_cwd = Path.cwd()
            import os
            try:
                os.chdir(folder)
                with patch('main.sys.argv', ['main.py', '--mentions', 'sample brand', '--report', 'html', '--no-banner']), \
                     patch('osint.intelligence.research_public', new=AsyncMock(return_value=rows)) as job:
                    main.main()
                job.assert_awaited_once_with('mentions', 'sample brand')
                html = Path('trackher_report_html.html').read_text(encoding='utf-8')
                self.assertIn('&lt;candidate&gt;', html)
                self.assertNotIn('<candidate>', html)
            finally:
                os.chdir(old_cwd)

    def test_all_inputs_validate_before_provider_calls(self):
        import main
        with patch('main.sys.argv', ['main.py', '--mentions', 'valid brand', '--organization', 'https://bad/', '--no-banner']), \
             patch('osint.intelligence.research_public', new=AsyncMock()) as job, \
             self.assertRaises(SystemExit) as error:
            main.main()
        self.assertEqual(error.exception.code, 2)
        job.assert_not_called()


if __name__ == '__main__':
    unittest.main()
