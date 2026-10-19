from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from utils.finding_reviews import finding_id, review_for, review_rows, set_review, export_reviews_csv
from utils.research import new_case, record_scan, save_case, load_case, export_case_html, validate_case


def row(site='GitHub', handle='sample', status='found'):
    return {'platform': site, 'queried_username': handle, 'status': status, 'found': status == 'found',
            'url': f'https://{site.lower()}.example/{handle}', 'public_metadata': {'bio': 'Original bio'},
            'evidence_card': {'checked_at': '2026-10-17T00:00:00+00:00', 'rule_fingerprint': 'rule1'}}


class FindingReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = new_case()
        self.scan = record_scan(self.case, 'username', 'sample', 'standard', [row(), row('GitLab', status='unknown')])
        self.result = self.scan['rows'][0]

    def test_annotation_roundtrip_and_legacy_case_compatibility(self):
        old = deepcopy(self.case)
        old.pop('reviews')
        self.assertEqual(review_for(old, self.scan, self.result)['view_state'], 'new')
        validate_case(old)
        set_review(self.case, self.scan, self.result, state='reviewed', priority='high', notes='Manual note', tags=['work', 'work', ' checked '])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.json'
            save_case(path, self.case)
            loaded = load_case(path)
        annotation = review_for(loaded, loaded['scans'][0], loaded['scans'][0]['rows'][0])
        self.assertEqual(annotation['state'], 'reviewed')
        self.assertEqual(annotation['notes'], 'Manual note')
        self.assertEqual(annotation['tags'], ['work', 'checked'])

    def test_review_never_promotes_or_erases_machine_detection(self):
        original = deepcopy(self.scan)
        for state in ('new', 'reviewed', 'rejected', 'uncertain'):
            set_review(self.case, self.scan, self.scan['rows'][1], state=state)
            self.assertEqual(self.scan, original)
        set_review(self.case, self.scan, self.result, state='rejected')
        self.assertEqual(self.result['status'], 'found')
        self.assertTrue(self.result['found'])

    def test_annotations_are_isolated_by_target_handle_and_source_section(self):
        base = finding_id(self.scan, self.result)
        other_target = dict(self.scan, target='other')
        self.assertNotEqual(base, finding_id(other_target, self.result))
        self.assertNotEqual(base, finding_id(self.scan, dict(self.result, queried_username='other')))
        self.assertNotEqual(base, finding_id(self.scan, dict(self.result, platform='GitLab')))
        email_scan = dict(self.scan, kind='email', target='ME@EXAMPLE.COM')
        account = {'service': 'Provider', 'section': 'account', 'status': 'UNKNOWN'}
        breach = dict(account, section='breach')
        self.assertNotEqual(finding_id(email_scan, account), finding_id(email_scan, breach))
        self.assertEqual(finding_id(email_scan, account), finding_id(dict(email_scan, target='me@example.com'), account))

    def test_rescan_timestamp_alone_does_not_invalidate_review(self):
        set_review(self.case, self.scan, self.result, state='reviewed')
        again = deepcopy(self.result)
        again['evidence_card']['checked_at'] = '2027-01-01T00:00:00+00:00'
        again['retained_from_previous_scan'] = True
        new_scan = record_scan(self.case, 'username', 'sample', 'quick', [again])
        self.assertEqual(review_for(self.case, new_scan, again)['view_state'], 'reviewed')

    def test_evidence_change_reopens_review_but_keeps_notes_and_previous_decision(self):
        set_review(self.case, self.scan, self.result, state='rejected', priority='high', notes='Keep this note', tags=['watch'])
        for changed in [dict(self.result, status='unknown', found=False),
                        dict(self.result, public_metadata={'bio': 'Changed bio'}),
                        dict(self.result, evidence_card={'rule_fingerprint': 'rule2'})]:
            annotation = review_for(self.case, self.scan, changed)
            self.assertEqual(annotation['view_state'], 'stale')
            self.assertEqual(annotation['state'], 'rejected')
            self.assertEqual(annotation['notes'], 'Keep this note')
            self.assertEqual(annotation['tags'], ['watch'])
        set_review(self.case, self.scan, changed, state='reviewed', notes='Rechecked')
        self.assertFalse(review_for(self.case, self.scan, changed)['stale'])

    def test_search_combines_notes_tags_state_priority_and_preserves_unknowns(self):
        set_review(self.case, self.scan, self.scan['rows'][1], state='uncertain', priority='high', notes='Review after access returns', tags=['follow-up'])
        found = review_rows(self.case, self.scan, query='FOLLOW-UP', state='uncertain', priority='high')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['detection'], 'unknown')
        self.assertEqual(review_rows(self.case, self.scan, query='follow-up', state='reviewed'), [])
        self.assertEqual(len(review_rows(self.case, self.scan)), 2)
        self.assertEqual(len(review_rows(self.case, self.scan, state='new')), 1)

    def test_stale_filter_and_read_views_do_not_mutate_the_case(self):
        set_review(self.case, self.scan, self.result, state='reviewed')
        changed = deepcopy(self.result)
        changed['public_metadata']['bio'] = 'New'
        scan = record_scan(self.case, 'username', 'sample', 'standard', [changed])
        before = deepcopy(self.case)
        self.assertEqual(len(review_rows(self.case, scan, state='stale')), 1)
        self.assertEqual(len(review_rows(self.case, scan, state='reviewed')), 0)
        self.assertEqual(self.case, before)

    def test_turkish_search_handles_dotted_i_and_unaccented_input(self):
        set_review(self.case, self.scan, self.result, notes='Özel bulgu', tags=['izleme', 'ışık'])
        for query in ('İZLEME', 'IZLEME', 'ISIK', 'IŞIK', 'ozel'):
            with self.subTest(query=query):
                self.assertEqual(len(review_rows(self.case, self.scan, query=query)), 1)

    def test_malformed_imported_reviews_fail_before_ui_use(self):
        set_review(self.case, self.scan, self.result)
        key = finding_id(self.scan, self.result)
        for field, invalid in [('state', []), ('priority', 'critical'), ('notes', 'x' * 20001),
                               ('tags', ['x' * 81]), ('tags', 'tag'), ('evidence_fingerprint', 'bad'),
                               ('updated_at', '2026-01-01')]:
            data = deepcopy(self.case)
            data['reviews'][key][field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_case(data)

    def test_invalid_edit_preserves_the_existing_annotation(self):
        set_review(self.case, self.scan, self.result, notes='Saved')
        before = deepcopy(self.case)
        with self.assertRaises(ValueError):
            set_review(self.case, self.scan, self.result, notes='x' * 20001)
        self.assertEqual(self.case, before)

    def test_csv_exports_visible_subset_and_neutralizes_spreadsheet_formulas(self):
        set_review(self.case, self.scan, self.result, state='reviewed', notes=' =HYPERLINK("https://example.org")\nsecond line', tags=['=formula'])
        visible = review_rows(self.case, self.scan, state='reviewed')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'review.csv'
            export_reviews_csv(path, visible)
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['notes'].startswith("' =HYPERLINK"))
        self.assertTrue(rows[0]['tags'].startswith("'=formula"))
        self.assertEqual(rows[0]['detection'], 'found')

    def test_html_report_keeps_raw_evidence_and_escapes_review_content(self):
        set_review(self.case, self.scan, self.result, state='uncertain', notes='<script>note</script>', tags=['<img src=x>'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.html'
            export_case_html(path, self.case)
            text = path.read_text(encoding='utf-8')
        self.assertIn('Kararsız', text)
        self.assertIn('&lt;script&gt;note&lt;/script&gt;', text)
        self.assertIn('&lt;img src=x&gt;', text)
        self.assertNotIn('<script>', text)
        self.assertIn('Original bio', text)


class CaseSaveProtectionTests(unittest.TestCase):
    def make_app(self):
        from gui.tabs.research import ResearchTabMixin
        app = ResearchTabMixin()
        app._has_unsaved_case = Mock(return_value=True)
        app._save_case = Mock(return_value=False)
        app.after = Mock()
        app._on_close = Mock()
        app._stop_scan = Mock()
        return app

    def test_cancelled_save_does_not_discard_the_current_case(self):
        app = self.make_app()
        with patch('gui.tabs.research.messagebox.askyesnocancel', return_value=True):
            self.assertFalse(app._confirm_case_replacement())
            app._save_case.return_value = True
            self.assertTrue(app._confirm_case_replacement())

    def test_cancel_and_explicit_discard_have_different_outcomes(self):
        app = self.make_app()
        with patch('gui.tabs.research.messagebox.askyesnocancel', return_value=None):
            self.assertFalse(app._confirm_case_replacement())
        with patch('gui.tabs.research.messagebox.askyesnocancel', return_value=False):
            self.assertTrue(app._confirm_case_replacement())
        app._save_case.assert_not_called()

    def test_close_during_scan_waits_for_stopped_results_before_saving(self):
        app = self.make_app()
        app._scan_active = True
        with patch('gui.tabs.research.messagebox.askyesnocancel', return_value=True):
            self.assertFalse(app._close_case_can_exit())
        app._stop_scan.assert_called_once()
        app._save_case.assert_not_called()
        app.after.assert_called_with(150, app._on_close)
        app._scan_active = False
        app._save_case.return_value = True
        self.assertTrue(app._close_case_can_exit())
        app._save_case.assert_called_once()
        self.assertFalse(app._close_save_pending)

    def test_close_cancel_keeps_scan_running_and_saved_case_closes_without_prompt(self):
        app = self.make_app()
        app._scan_active = True
        with patch('gui.tabs.research.messagebox.askyesnocancel', return_value=None):
            self.assertFalse(app._close_case_can_exit())
        app._stop_scan.assert_not_called()
        app.after.assert_not_called()
        app._scan_active = False
        app._has_unsaved_case.return_value = False
        with patch('gui.tabs.research.messagebox.askyesnocancel') as ask:
            self.assertTrue(app._close_case_can_exit())
        ask.assert_not_called()


if __name__ == '__main__':
    unittest.main()
