import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from osint import checker
from osint import username_checker
from osint.detector_runtime import normalize_username_result
from utils.history import save_and_diff_scan
from utils.profiles import (
    DEFAULT_SCAN_PROFILE,
    normalize_scan_profile,
    profile_allows_email,
    profile_allows_username,
)
from utils.reporter import export_to_html, export_to_json


class ProfileSelectionTests(unittest.TestCase):
    def test_invalid_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_scan_profile("invalid")

    def test_profile_scope_flags(self):
        self.assertTrue(profile_allows_email("quick"))
        self.assertTrue(profile_allows_username("quick"))
        self.assertFalse(profile_allows_email("username-only"))
        self.assertFalse(profile_allows_username("email-only"))
        self.assertEqual(normalize_scan_profile(None), DEFAULT_SCAN_PROFILE)


class EmailProfileRuntimeTests(unittest.TestCase):
    def test_default_profile_keeps_existing_email_coverage(self):
        called_accounts: list[str] = []
        called_breaches: list[str] = []

        async def fake_account(email, client, platform):
            called_accounts.append(platform["name"])
            return {"service": platform["name"], "status": "FOUND", "found": True}

        async def fake_breach(email, client, platform):
            called_breaches.append(platform["name"])
            return {"service": platform["name"], "status": "FOUND", "found": True, "breaches": []}

        account_platforms = [
            {"name": "Verified", "category": "verified"},
            {"name": "Heuristic", "category": "heuristic"},
        ]
        breach_platforms = [
            {"name": "HIBP", "category": "verified"},
        ]

        with (
            patch.object(checker, "ACCOUNT_PLATFORMS", account_platforms),
            patch.object(checker, "BREACH_PLATFORMS", breach_platforms),
            patch.object(checker, "check_account_platform", fake_account),
            patch.object(checker, "check_breach_platform", fake_breach),
        ):
            result = asyncio.run(checker.check_email("owner@example.test"))

        self.assertCountEqual(called_accounts, ["Verified", "Heuristic"])
        self.assertEqual(called_breaches, ["HIBP"])
        self.assertEqual(len(result["accounts"]), 2)
        self.assertEqual(len(result["breaches"]), 1)

    def test_quick_profile_filters_to_verified_email_checks(self):
        called_accounts: list[str] = []
        called_breaches: list[str] = []

        async def fake_account(email, client, platform):
            called_accounts.append(platform["name"])
            return {"service": platform["name"], "status": "FOUND", "found": True}

        async def fake_breach(email, client, platform):
            called_breaches.append(platform["name"])
            return {"service": platform["name"], "status": "FOUND", "found": True, "breaches": []}

        account_platforms = [
            {"name": "Verified", "category": "verified"},
            {"name": "Heuristic", "category": "heuristic"},
        ]
        breach_platforms = [
            {"name": "HIBP", "category": "verified"},
            {"name": "ManualBreach", "category": "manual"},
        ]

        with (
            patch.object(checker, "ACCOUNT_PLATFORMS", account_platforms),
            patch.object(checker, "BREACH_PLATFORMS", breach_platforms),
            patch.object(checker, "check_account_platform", fake_account),
            patch.object(checker, "check_breach_platform", fake_breach),
        ):
            result = asyncio.run(checker.check_email("owner@example.test", profile="quick"))

        self.assertCountEqual(called_accounts, ["Verified"])
        self.assertEqual(called_breaches, ["HIBP"])
        self.assertEqual(len(result["accounts"]), 1)
        self.assertEqual(len(result["breaches"]), 1)

    def test_deep_profile_currently_matches_standard_email_scope(self):
        called_standard: list[str] = []
        called_deep: list[str] = []

        async def fake_account(email, client, platform):
            return {"service": platform["name"], "status": "FOUND", "found": True}

        async def fake_breach(email, client, platform):
            return {"service": platform["name"], "status": "FOUND", "found": True, "breaches": []}

        account_platforms = [
            {"name": "Verified", "category": "verified"},
            {"name": "Heuristic", "category": "heuristic"},
        ]
        breach_platforms = [{"name": "HIBP", "category": "verified"}]

        async def capture_standard(email, client, platform):
            called_standard.append(platform["name"])
            return await fake_account(email, client, platform)

        async def capture_deep(email, client, platform):
            called_deep.append(platform["name"])
            return await fake_account(email, client, platform)

        with (
            patch.object(checker, "ACCOUNT_PLATFORMS", account_platforms),
            patch.object(checker, "BREACH_PLATFORMS", breach_platforms),
            patch.object(checker, "check_account_platform", capture_standard),
            patch.object(checker, "check_breach_platform", fake_breach),
        ):
            asyncio.run(checker.check_email("owner@example.test", profile="standard"))

        with (
            patch.object(checker, "ACCOUNT_PLATFORMS", account_platforms),
            patch.object(checker, "BREACH_PLATFORMS", breach_platforms),
            patch.object(checker, "check_account_platform", capture_deep),
            patch.object(checker, "check_breach_platform", fake_breach),
        ):
            asyncio.run(checker.check_email("owner@example.test", profile="deep"))

        self.assertCountEqual(called_standard, called_deep)


class UsernameProfileRuntimeTests(unittest.TestCase):
    def test_default_profile_keeps_existing_username_coverage(self):
        called: list[str] = []

        async def fake_detector(username, platform, client):
            called.append(platform["name"])
            return normalize_username_result(platform, status="found")

        platforms = [
            {"name": "Verified", "url": "https://example.test/{}", "reliability": "verified", "check": "html"},
            {"name": "Unreliable", "url": "https://example.test/{}", "reliability": "unreliable", "check": "html"},
        ]

        with (
            patch.object(username_checker, "USERNAME_PLATFORMS", platforms),
            patch.object(username_checker, "check_single_username", fake_detector),
        ):
            result = asyncio.run(username_checker.check_username_async("octocat"))

        self.assertCountEqual(called, ["Verified", "Unreliable"])
        self.assertEqual(len(result), 2)

    def test_quick_profile_filters_to_verified_username_checks(self):
        called: list[str] = []

        async def fake_detector(username, platform, client):
            called.append(platform["name"])
            return normalize_username_result(platform, status="found")

        platforms = [
            {"name": "Verified", "url": "https://example.test/{}", "reliability": "verified", "check": "html"},
            {"name": "Unreliable", "url": "https://example.test/{}", "reliability": "unreliable", "check": "html"},
        ]

        with (
            patch.object(username_checker, "USERNAME_PLATFORMS", platforms),
            patch.object(username_checker, "check_single_username", fake_detector),
        ):
            result = asyncio.run(username_checker.check_username_async("octocat", profile="quick"))

        self.assertCountEqual(called, ["Verified"])
        self.assertEqual(len(result), 1)

    def test_email_only_profile_disables_username_scans_via_helper(self):
        self.assertFalse(profile_allows_username("email-only"))

    def test_username_only_profile_disables_email_scans_via_helper(self):
        self.assertFalse(profile_allows_email("username-only"))


class ReportProfileTests(unittest.TestCase):
    def test_json_and_html_reports_include_scan_profile(self):
        payload = {
            "scan_profile": "quick",
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [{"service": "Gravatar", "status": "FOUND", "found": True}],
                    "breaches": [],
                },
            },
            "risk": {"score": 10, "level": "LOW", "reasons": [], "disclaimer": "test"},
            "scan_history": {
                "enabled": True,
                "available": False,
                "status": "first_scan",
                "message": "No previous matching scan in local history.",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "report.json"
            html_path = Path(temp_dir) / "report.html"
            export_to_json(payload, str(json_path))
            export_to_html(payload, str(html_path))
            json_report = json.loads(json_path.read_text(encoding="utf-8"))
            html_report = html_path.read_text(encoding="utf-8")

        self.assertEqual(json_report["scan_profile"], "quick")
        self.assertIn("Scan Profile", html_report)
        self.assertIn("quick", html_report)


class HistoryProfileTests(unittest.TestCase):
    def test_history_snapshot_records_profile_and_warns_on_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_dir = Path(temp_dir)
            save_and_diff_scan(
                {
                    "scan_profile": "standard",
                    "osint_email": {
                        "target": "owner@example.test",
                        "results": {
                            "accounts": [{"service": "Gravatar", "status": "FOUND", "found": True}],
                            "breaches": [],
                        },
                    },
                    "risk": {"score": 10, "level": "LOW"},
                },
                history_dir=history_dir,
            )
            result = save_and_diff_scan(
                {
                    "scan_profile": "quick",
                    "osint_email": {
                        "target": "owner@example.test",
                        "results": {
                            "accounts": [{"service": "Gravatar", "status": "FOUND", "found": True}],
                            "breaches": [],
                        },
                    },
                    "risk": {"score": 10, "level": "LOW"},
                },
                history_dir=history_dir,
            )

        self.assertTrue(result["profile_mismatch"])
        self.assertIn("different profiles", result["coverage_warning"])


if __name__ == "__main__":
    unittest.main()
