import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from utils.display import print_remediation_summary
from utils.history import save_and_diff_scan
from utils.reporter import export_to_html, export_to_json
from utils.remediation import build_remediation_report


def username_payload(results: list[dict]) -> dict:
    return {
        "osint_username": {
            "target": "test-user",
            "results": results,
        }
    }


class RemediationReportTests(unittest.TestCase):
    def test_real_catalog_actions_are_exposed_for_found_username(self):
        payload = username_payload(
            [
                {
                    "platform": "GitHub",
                    "status": "found",
                    "found": True,
                    "url": "https://github.com/octocat",
                }
            ]
        )

        remediation = build_remediation_report(payload)

        self.assertTrue(remediation["available"])
        self.assertEqual(remediation["item_count"], 1)
        self.assertGreaterEqual(remediation["action_count"], 3)
        labels = {action["label"] for action in remediation["items"][0]["actions"]}
        self.assertIn("Account Security / 2FA", labels)
        self.assertIn("Data Export", labels)
        self.assertIn("Delete Account / Help", labels)

    def test_platform_with_no_actions_is_ignored(self):
        payload = username_payload(
            [
                {
                    "platform": "Facebook",
                    "status": "found",
                    "found": True,
                    "url": "https://www.facebook.com/example",
                }
            ]
        )

        remediation = build_remediation_report(payload)

        self.assertFalse(remediation["available"])
        self.assertEqual(remediation["items"], [])

    def test_invalid_url_rejection_omits_unsafe_links(self):
        fake_platforms = [
            {
                "name": "BadSite",
                "actions": [
                    {
                        "type": "Help",
                        "label": "Help",
                        "url": "javascript:alert(1)",
                    },
                    {
                        "type": "Docs",
                        "label": "Docs",
                        "url": "file:///tmp/notes",
                    },
                ],
            }
        ]

        with patch("osint.username_checker.USERNAME_PLATFORMS", fake_platforms):
            remediation = build_remediation_report(
                username_payload(
                    [
                        {
                            "platform": "BadSite",
                            "status": "found",
                            "found": True,
                            "url": "https://example.test/badsite",
                        }
                    ]
                )
            )

        self.assertFalse(remediation["available"])
        self.assertEqual(remediation["items"], [])

    def test_html_escaping_and_report_serialization(self):
        fake_platforms = [
            {
                "name": "EscapedSite",
                "actions": [
                    {
                        "type": "Help",
                        "label": "<script>alert(1)</script>",
                        "url": "https://example.test/help",
                    }
                ],
            }
        ]
        payload = username_payload(
            [
                {
                    "platform": "EscapedSite",
                    "status": "found",
                    "found": True,
                    "url": "https://example.test/profile",
                }
            ]
        )

        with patch("osint.username_checker.USERNAME_PLATFORMS", fake_platforms):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir = Path(temp_dir)
                html_path = temp_dir / "report.html"
                json_path = temp_dir / "report.json"
                export_to_html(payload, str(html_path))
                export_to_json(payload, str(json_path))
                html_report = html_path.read_text(encoding="utf-8")
                json_report = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_report)
        self.assertNotIn("javascript:", html_report)
        self.assertIn("remediation", json_report)
        self.assertTrue(json_report["remediation"]["available"])

    def test_history_ignores_remediation_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            payload = {
                **username_payload(
                    [
                        {
                            "platform": "Reddit",
                            "status": "found",
                            "found": True,
                            "url": "https://www.reddit.com/user/example/",
                        }
                    ]
                ),
                "remediation": {"available": True, "items": []},
            }
            save_and_diff_scan(payload, history_dir=history_dir)
            result = save_and_diff_scan(payload, history_dir=history_dir)

        self.assertEqual(len(result["unchanged_findings"]), 1)
        self.assertEqual(result["unchanged_findings"][0]["label"], "Reddit")


class RemediationDisplayTests(unittest.TestCase):
    def test_summary_can_be_concise_or_detailed(self):
        remediation = {
            "available": True,
            "item_count": 1,
            "action_count": 2,
            "items": [
                {
                    "platform": "GitHub",
                    "status": "FOUND",
                    "actions": [
                        {"label": "Account Security / 2FA", "url": "https://example.test/2fa"},
                        {"label": "Delete Account / Help", "url": "https://example.test/delete"},
                    ],
                }
            ],
        }

        with patch("utils.display.console") as console:
            print_remediation_summary(remediation, show_details=False)
            concise_output = [call.args[0] for call in console.print.call_args_list]

        self.assertTrue(any("Use --show-actions" in line for line in concise_output))

        with patch("utils.display.console") as console:
            print_remediation_summary(remediation, show_details=True)
            detailed_output = [
                " ".join(str(arg) for arg in call.args)
                for call in console.print.call_args_list
                if call.args
            ]

        self.assertTrue(any("GitHub" in line and "FOUND" in line for line in detailed_output))
        self.assertTrue(any("Account Security / 2FA" in line for line in detailed_output))


if __name__ == "__main__":
    unittest.main()
