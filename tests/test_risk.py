import json
import tempfile
import unittest
from pathlib import Path

from utils.reporter import export_to_html, export_to_json
from utils.risk import DISCLAIMER, compute_risk


class RiskScoreTests(unittest.TestCase):
    def test_manual_and_unknown_do_not_increase_risk(self):
        risk = compute_risk(
            {
                "osint_email": {
                    "target": "owner@example.test",
                    "results": {
                        "accounts": [
                            {"service": "ManualOnly", "status": "MANUAL", "found": False},
                            {"service": "UnknownOnly", "status": "UNKNOWN", "found": False},
                        ],
                        "breaches": [
                            {"service": "Have I Been Pwned", "status": "NOT_CONFIGURED", "found": False},
                        ],
                    },
                }
            }
        )

        self.assertEqual(risk["score"], 0)
        self.assertEqual(risk["level"], "LOW")
        self.assertEqual(risk["reasons"], [])

    def test_possible_counts_less_than_verified(self):
        verified = compute_risk(
            {
                "osint_email": {
                    "target": "owner@example.test",
                    "results": {
                        "accounts": [{"service": "Gravatar", "status": "FOUND", "found": True}],
                        "breaches": [],
                    },
                }
            }
        )
        possible = compute_risk(
            {
                "osint_email": {
                    "target": "owner@example.test",
                    "results": {
                        "accounts": [{"service": "GitHub", "status": "POSSIBLE", "found": False}],
                        "breaches": [],
                    },
                }
            }
        )

        self.assertGreater(verified["score"], possible["score"])

    def test_boundary_levels_and_caps(self):
        medium = compute_risk(
            {
                "osint_username": {
                    "target": "test-user",
                    "results": [
                        {"platform": "A", "status": "found", "found": True},
                        {"platform": "B", "status": "found", "found": True},
                        {"platform": "C", "status": "found", "found": True},
                        {"platform": "D", "status": "found", "found": True},
                        {"platform": "E", "status": "found", "found": True},
                    ],
                }
            }
        )
        critical = compute_risk(
            {
                "osint_email": {
                    "target": "owner@example.test",
                    "results": {
                        "accounts": [
                            {"service": "Gravatar", "status": "FOUND", "found": True},
                            {"service": "GitLab", "status": "FOUND", "found": True},
                            {"service": "Other", "status": "FOUND", "found": True},
                        ],
                        "breaches": [
                            {
                                "service": "Have I Been Pwned",
                                "status": "FOUND",
                                "found": True,
                                "breaches": ["A", "B", "C", "D"],
                            }
                        ],
                    },
                },
                "osint_username": {
                    "target": "test-user",
                    "results": [
                        {"platform": "P1", "status": "found", "found": True},
                        {"platform": "P2", "status": "found", "found": True},
                        {"platform": "P3", "status": "found", "found": True},
                        {"platform": "P4", "status": "found", "found": True},
                        {"platform": "P5", "status": "found", "found": True},
                        {"platform": "P6", "status": "found", "found": True},
                    ],
                },
            }
        )

        self.assertEqual(medium["score"], 20)
        self.assertEqual(medium["level"], "MEDIUM")
        self.assertEqual(critical["score"], 100)
        self.assertEqual(critical["level"], "CRITICAL")

    def test_username_unreliable_counts_less_than_verified(self):
        verified = compute_risk(
            {
                "osint_username": {
                    "target": "test-user",
                    "results": [{"platform": "Reddit", "status": "found", "found": True}],
                }
            }
        )
        unreliable = compute_risk(
            {
                "osint_username": {
                    "target": "test-user",
                    "results": [
                        {
                            "platform": "Heuristic Site",
                            "status": "found",
                            "found": True,
                            "reliability": "unreliable",
                        }
                    ],
                }
            }
        )

        self.assertGreater(verified["score"], unreliable["score"])


class RiskReportTests(unittest.TestCase):
    def test_risk_is_added_to_json_and_html_reports(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [{"service": "Gravatar", "status": "FOUND", "found": True}],
                    "breaches": [],
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "report.json"
            html_path = Path(temp_dir) / "report.html"
            export_to_json(payload, str(json_path))
            export_to_html(payload, str(html_path))
            json_report = json.loads(json_path.read_text(encoding="utf-8"))
            html_report = html_path.read_text(encoding="utf-8")

        self.assertIn("risk", json_report)
        self.assertEqual(json_report["risk"]["score"], 10)
        self.assertIn("Digital Footprint Risk Score", html_report)
        self.assertIn(DISCLAIMER, html_report)


if __name__ == "__main__":
    unittest.main()
