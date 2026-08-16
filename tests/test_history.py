import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.history import clear_scan_history, save_and_diff_scan
from utils.reporter import export_to_html, export_to_json


def email_payload(
    *,
    target: str = "owner@example.test",
    accounts: list[dict] | None = None,
    breaches: list[dict] | None = None,
    risk_score: int = 0,
    risk_level: str = "LOW",
    scan_profile: str = "standard",
) -> dict:
    return {
        "scan_profile": scan_profile,
        "osint_email": {
            "target": target,
            "results": {
                "accounts": accounts or [],
                "breaches": breaches or [],
            },
        },
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "reasons": [],
            "disclaimer": "test",
        },
    }


def username_payload(
    *,
    target: str = "test-user",
    results: list[dict] | None = None,
    risk_score: int = 0,
    risk_level: str = "LOW",
    scan_profile: str = "standard",
) -> dict:
    return {
        "scan_profile": scan_profile,
        "osint_username": {
            "target": target,
            "results": results or [],
        },
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "reasons": [],
            "disclaimer": "test",
        },
    }


class HistoryTests(unittest.TestCase):
    def test_first_scan_has_no_previous_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                ),
                history_dir=Path(temp_dir),
            )

        self.assertTrue(result["enabled"])
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "first_scan")

    def test_new_finding_is_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                email_payload(
                    accounts=[
                        {"service": "Gravatar", "status": "FOUND", "found": True},
                        {"service": "GitHub", "status": "POSSIBLE", "found": False},
                    ],
                    risk_score=14,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )

        self.assertTrue(result["available"])
        self.assertEqual(len(result["new_findings"]), 1)
        self.assertEqual(result["new_findings"][0]["label"], "GitHub")

    def test_resolved_finding_is_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    accounts=[
                        {"service": "Gravatar", "status": "FOUND", "found": True},
                        {"service": "GitHub", "status": "POSSIBLE", "found": False},
                    ],
                    risk_score=14,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )

        self.assertEqual(len(result["resolved_findings"]), 1)
        self.assertEqual(result["resolved_findings"][0]["label"], "GitHub")

    def test_unchanged_finding_is_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            baseline = username_payload(
                results=[{"platform": "Reddit", "status": "found", "found": True}],
                risk_score=4,
                risk_level="LOW",
            )
            save_and_diff_scan(baseline, history_dir=history_dir)
            result = save_and_diff_scan(baseline, history_dir=history_dir)

        self.assertEqual(len(result["unchanged_findings"]), 1)
        self.assertEqual(result["unchanged_findings"][0]["label"], "Reddit")

    def test_breach_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    breaches=[
                        {
                            "service": "Have I Been Pwned",
                            "status": "FOUND",
                            "found": True,
                            "breaches": ["OldBreach"],
                        }
                    ],
                    risk_score=18,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                email_payload(
                    breaches=[
                        {
                            "service": "Have I Been Pwned",
                            "status": "FOUND",
                            "found": True,
                            "breaches": ["NewBreach"],
                        }
                    ],
                    risk_score=18,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )

        self.assertEqual([item["label"] for item in result["new_breaches"]], ["NewBreach"])
        self.assertEqual([item["label"] for item in result["removed_breaches"]], ["OldBreach"])

    def test_risk_score_change_is_detected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                username_payload(
                    results=[{"platform": "Reddit", "status": "found", "found": True}],
                    risk_score=67,
                    risk_level="HIGH",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                username_payload(
                    results=[],
                    risk_score=48,
                    risk_level="MEDIUM",
                ),
                history_dir=history_dir,
            )

        self.assertEqual(result["previous"]["risk"]["score"], 67)
        self.assertEqual(result["current"]["risk"]["score"], 48)
        self.assertEqual(result["risk_change"]["value"], -19)
        self.assertEqual(result["risk_change"]["direction"], "down")

    def test_disabled_history_skips_storage_and_diff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            result = save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                ),
                enabled=False,
                history_dir=history_dir,
            )

            snapshot_dir = history_dir / "snapshots"

        self.assertFalse(result["enabled"])
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(snapshot_dir.exists())

    def test_clear_history_removes_local_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )
            result = clear_scan_history(history_dir)

        self.assertTrue(result["cleared"])
        self.assertEqual(result["removed_files"], 1)

    def test_corrupted_history_data_is_reset_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            first = email_payload(
                accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                risk_score=10,
                risk_level="LOW",
            )
            initial = save_and_diff_scan(first, history_dir=history_dir)
            snapshot_path = Path(initial["snapshot_path"])
            snapshot_path.write_text("{not-json", encoding="utf-8")

            result = save_and_diff_scan(first, history_dir=history_dir)
            archived = list(snapshot_path.parent.glob("*.corrupt-*.jsonl"))

        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "corrupted")
        self.assertTrue(archived)

    def test_manual_unknown_and_errors_are_not_marked_resolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    accounts=[
                        {"service": "ManualOnly", "status": "MANUAL", "found": False},
                        {"service": "UnknownOnly", "status": "UNKNOWN", "found": False},
                    ],
                    risk_score=0,
                    risk_level="LOW",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                email_payload(accounts=[], risk_score=0, risk_level="LOW"),
                history_dir=history_dir,
            )

        self.assertEqual(result["resolved_findings"], [])

    def test_profile_mismatch_is_reported_in_diff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                    scan_profile="standard",
                ),
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                email_payload(
                    accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                    risk_score=10,
                    risk_level="LOW",
                    scan_profile="quick",
                ),
                history_dir=history_dir,
            )

        self.assertTrue(result["profile_mismatch"])
        self.assertIn("different profiles", result["coverage_warning"])


class HistoryReportTests(unittest.TestCase):
    def test_report_includes_scan_diff(self):
        payload = {
            **email_payload(
                accounts=[{"service": "Gravatar", "status": "FOUND", "found": True}],
                risk_score=48,
                risk_level="MEDIUM",
                scan_profile="quick",
            ),
            "scan_history": {
                "enabled": True,
                "available": True,
                "status": "ok",
                "previous": {"risk": {"score": 67, "level": "HIGH"}, "profile": "standard"},
                "current": {"risk": {"score": 48, "level": "MEDIUM"}, "profile": "quick"},
                "profile_mismatch": True,
                "coverage_warning": "Diff coverage differs because the previous and current scans used different profiles.",
                "risk_change": {"value": -19, "direction": "down"},
                "new_findings": [{"label": "GitLab", "status": "FOUND"}],
                "resolved_findings": [{"label": "GitHub", "status": "POSSIBLE"}],
                "unchanged_findings": [{"label": "Gravatar", "status": "FOUND"}],
                "new_breaches": [],
                "removed_breaches": [],
                "unchanged_breaches": [],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "report.json"
            html_path = Path(temp_dir) / "report.html"
            export_to_json(payload, str(json_path))
            export_to_html(payload, str(html_path))
            json_report = json.loads(json_path.read_text(encoding="utf-8"))
            html_report = html_path.read_text(encoding="utf-8")

        self.assertIn("scan_history", json_report)
        self.assertEqual(json_report["scan_profile"], "quick")
        self.assertIn("Scan Diff", html_report)
        self.assertIn("Scan Profile", html_report)
        self.assertIn("Previous Risk:", html_report)


if __name__ == "__main__":
    unittest.main()
