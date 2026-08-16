import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.correlation import build_identity_correlation
from utils.reporter import export_to_html, export_to_json


def username_result(
    platform: str,
    *,
    reliability: str = "verified",
    metadata: dict | None = None,
) -> dict:
    return {
        "platform": platform,
        "url": f"https://example.test/{platform.casefold()}",
        "found": True,
        "status": "found",
        "reliability": "unreliable" if reliability == "heuristic" else "verified",
        "public_metadata": metadata or {},
    }


def email_result(
    service: str,
    *,
    status: str = "FOUND",
    metadata: dict | None = None,
) -> dict:
    return {
        "service": service,
        "status": status,
        "found": status == "FOUND",
        "detail": "",
        "public_metadata": metadata or {},
    }


class IdentityCorrelationTests(unittest.TestCase):
    def test_strong_multi_signal_match_is_high_confidence(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result(
                            "GitHub",
                            metadata={
                                "username": "octocat",
                                "display_name": "Octo Cat",
                                "website": "octo.example",
                            },
                        ),
                        email_result(
                            "GitLab",
                            metadata={
                                "username": "octocat",
                                "display_name": "Octo Cat",
                                "website": "https://octo.example/about",
                            },
                        ),
                    ],
                    "breaches": [],
                },
            }
        }

        correlation = build_identity_correlation(payload)

        self.assertTrue(correlation["available"])
        self.assertEqual(correlation["items"][0]["confidence"], "HIGH")
        labels = {item["signal"] for item in correlation["items"][0]["evidence"]}
        self.assertIn("same_username", labels)
        self.assertIn("same_website_domain", labels)

    def test_weak_single_signal_does_not_become_high_confidence(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result("GitHub", metadata={"display_name": "Alex Doe"}),
                        email_result("GitLab", metadata={"display_name": "Alex Doe"}),
                    ],
                    "breaches": [],
                },
            }
        }

        correlation = build_identity_correlation(payload)

        self.assertFalse(correlation["available"])

    def test_conflicting_signals_reduce_confidence(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result(
                            "GitHub",
                            metadata={
                                "username": "octocat",
                                "display_name": "Alpha Zeta",
                                "website": "https://example.dev",
                            },
                        ),
                        email_result(
                            "GitLab",
                            metadata={
                                "username": "octocat",
                                "display_name": "Beta Gamma",
                                "website": "example.dev",
                            },
                        ),
                    ],
                    "breaches": [],
                },
            }
        }

        correlation = build_identity_correlation(payload)

        self.assertTrue(correlation["available"])
        self.assertNotEqual(correlation["items"][0]["confidence"], "HIGH")
        self.assertTrue(correlation["items"][0]["penalties"])

    def test_missing_metadata_is_neutral(self):
        payload = {
            "osint_username": {
                "target": "octocat",
                "results": [
                    username_result("GitHub", metadata={"username": "octocat"}),
                    username_result("Reddit", metadata={}),
                ],
            }
        }

        correlation = build_identity_correlation(payload)

        self.assertFalse(correlation["available"])

    def test_false_positive_same_name_only_is_filtered(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result("GitHub", metadata={"display_name": "John Smith"}),
                        email_result("GitLab", metadata={"display_name": "John Smith"}),
                    ],
                    "breaches": [],
                },
            }
        }

        correlation = build_identity_correlation(payload)

        self.assertFalse(correlation["available"])

    def test_scoring_is_deterministic(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result(
                            "GitHub",
                            metadata={
                                "username": "octocat",
                                "display_name": "Octo Cat",
                                "website": "octo.example",
                            },
                        ),
                        email_result(
                            "GitLab",
                            status="POSSIBLE",
                            metadata={
                                "username": "octocat",
                                "display_name": "Octo Cat",
                                "website": "octo.example",
                            },
                        ),
                    ],
                    "breaches": [],
                },
            }
        }

        first = build_identity_correlation(payload)
        second = build_identity_correlation(payload)

        self.assertEqual(first, second)

    def test_html_and_json_reports_serialize_correlation(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        email_result(
                            "GitHub",
                            metadata={
                                "username": "octocat",
                                "display_name": "<Admin>",
                                "website": "octo.example",
                            },
                        ),
                        email_result(
                            "GitLab",
                            metadata={
                                "username": "octocat",
                                "display_name": "<Admin>",
                                "website": "octo.example",
                            },
                        ),
                    ],
                    "breaches": [],
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            html_path = temp_dir / "report.html"
            json_path = temp_dir / "report.json"
            export_to_html(payload, str(html_path))
            export_to_json(payload, str(json_path))
            html_report = html_path.read_text(encoding="utf-8")
            json_report = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertIn("Identity Correlation", html_report)
        self.assertNotIn("<Admin>", html_report)
        self.assertIn("correlation", json_report)
        self.assertTrue(json_report["correlation"]["available"])


if __name__ == "__main__":
    unittest.main()
