"""Complete result lists and status distinctions must survive GUI filtering."""
import unittest
from unittest.mock import Mock, patch

from gui import TrackherApp
from gui.widgets.results import filter_rows, public_link, result_row


class ResultListTests(unittest.TestCase):
    def test_all_303_results_are_available_without_sampling(self):
        rows = [result_row({'platform': f'Site {index}', 'status': 'unknown', 'unknown_cause': 'bot_blocked'}) for index in range(303)]
        self.assertEqual(len(filter_rows(rows)), 303)
        self.assertEqual(len(filter_rows(rows, 'Doğrulanamadı')), 303)
        self.assertEqual(filter_rows(rows, query='Site 302'), [rows[302]])

    def test_email_statuses_remain_distinct(self):
        statuses = ['FOUND', 'NOT_FOUND', 'UNKNOWN', 'ERROR', 'NOT_CONFIGURED', 'POSSIBLE', 'MANUAL', 'NO_PUBLIC_EVIDENCE']
        rows = [result_row({'service': status, 'status': status}) for status in statuses]
        self.assertEqual(len(filter_rows(rows, 'Doğrulanamadı')), 3)
        self.assertEqual(len(filter_rows(rows, 'Manuel')), 1)
        self.assertEqual(len(filter_rows(rows, 'Kanıt yok')), 1)
        self.assertEqual(len(filter_rows(rows, 'Bulundu')), 1)

    def test_filter_combines_group_and_case_insensitive_search(self):
        rows = [result_row({'platform': 'GitHub', 'status': 'found'}), result_row({'platform': 'GitLab', 'status': 'unknown', 'unknown_cause': 'timeout'})]
        self.assertEqual(filter_rows(rows, 'Bulundu', 'GIT'), [rows[0]])
        self.assertEqual(filter_rows(rows, 'Bulundu', 'gitlab'), [])
        self.assertEqual(filter_rows(rows, query='Yanıt süresi'), [rows[1]])

    def test_profile_links_reject_unsafe_schemes_and_credentials(self):
        for url in ('javascript:alert(1)', 'file:///C:/private', 'https://name:pass@example.com', 'http://', 'https://[bad'):
            self.assertFalse(public_link(url))
        self.assertTrue(public_link('https://github.com/octocat'))

    def test_username_worker_delivers_all_results_to_main_thread(self):
        from test_gui_memory import GuiMemoryTests
        app = GuiMemoryTests().make_app()
        app.results_tree = Mock()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_user = Mock()
        results = [{'platform': f'Site {n}', 'status': status, 'found': status == 'found', 'url': 'https://example.test'}
                   for n, status in enumerate(('found', 'not_found', 'unknown'))]
        async def scan(*args, on_result=None, **kwargs):
            for result in results:
                on_result(result)
            return results
        with patch('gui.tabs.osint.check_username_async', side_effect=scan):
            app.do_username_osint('sample')
        app.post_ui.assert_any_call(app._complete_scan_results, results)
        for result in results:
            app.post_ui.assert_any_call(app._receive_scan_result, result)
        app.post_ui.assert_any_call(app._release_scan_results)

    def test_email_worker_delivers_manual_unknown_breach_and_domain_rows(self):
        from test_gui_memory import GuiMemoryTests
        app = GuiMemoryTests().make_app()
        app.results_tree = Mock()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_email = Mock()
        payload = {'accounts': [{'service': 'Manual', 'status': 'MANUAL'}, {'service': 'Unknown', 'status': 'UNKNOWN'}],
                   'breaches': [{'service': 'Breach provider', 'status': 'NOT_CONFIGURED'}],
                   'domain': {'domain': 'example.invalid', 'status': 'UNKNOWN'}}
        with patch('gui.tabs.osint.asyncio.run', side_effect=GuiMemoryTests.fake_asyncio_run(payload)):
            app.do_email_osint('sample@example.invalid')
        calls = [call for call in app.post_ui.call_args_list if call.args[0] == app._complete_scan_results]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0].args[1]), 4)
        self.assertEqual(calls[0].args[1][-1]['service'], 'Alan adı · example.invalid')
