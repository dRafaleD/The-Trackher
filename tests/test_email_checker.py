import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from osint import checker
from osint.services import (
    AUTOMATIC_ACCOUNT_PLATFORMS,
    ALL_SERVICES,
    EMAIL_PLATFORMS,
    UNKNOWN,
    FOUND,
    MANUAL,
    NOT_CONFIGURED,
    NOT_FOUND,
    POSSIBLE,
    ERROR,
    check_account_platform,
    check_gravatar,
    check_haveibeenpwned,
)
from utils.display import print_email_results
from utils.reporter import export_to_html, export_to_json


class EmailDetectionTests(unittest.TestCase):
    def run_account_check(self, platform: dict, response: httpx.Response, email: str = "owner@example.test") -> dict:
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: response)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform(email, client, platform)

        return asyncio.run(execute())

    def test_gravatar_verified_found_and_not_found(self):
        found = self.run_account_check(
            {"name": "Gravatar", "category": "verified", "check": "gravatar"},
            httpx.Response(200),
        )
        missing = self.run_account_check(
            {"name": "Gravatar", "category": "verified", "check": "gravatar"},
            httpx.Response(404),
        )

        self.assertEqual(found["status"], FOUND)
        self.assertEqual(missing["status"], NOT_FOUND)

    def test_heuristic_result_is_possible_never_verified_found(self):
        platform = {
            "name": "Example",
            "category": "heuristic",
            "check": "heuristic",
            "probe_url": "https://example.test/check?email={email}",
            "possible_markers": ["account exists"],
        }

        result = self.run_account_check(platform, httpx.Response(200, text="account exists"))

        self.assertEqual(result["status"], POSSIBLE)
        self.assertFalse(result["found"])

    def test_manual_platform_is_kept_for_investigation(self):
        platform = {"name": "GitHub", "category": "manual", "check": "manual"}

        result = self.run_account_check(platform, httpx.Response(200))

        self.assertEqual(result["status"], MANUAL)
        self.assertFalse(result["found"])

    def test_unsupported_email_detector_type_falls_back_to_manual(self):
        platform = {
            "name": "Unknown",
            "category": "manual",
            "check": "unsupported_type",
        }

        result = self.run_account_check(platform, httpx.Response(200))

        self.assertEqual(result["status"], MANUAL)
        self.assertFalse(result["found"])

    def test_malformed_email_platform_metadata_is_isolated(self):
        platform = {
            "name": "Broken",
            "category": "verified",
            "check": "public_profile_email",
            "probe_url": "https://example.test/search?email={email}",
            "items_path": "items",
            "profile_url_template": "https://example.test/users/{missing}",
            "profile_email_field": "email",
        }

        result = self.run_account_check(platform, httpx.Response(200, json={"items": [{"id": 1}]}))

        self.assertEqual(result["status"], UNKNOWN)
        self.assertFalse(result["found"])

    def test_public_profile_email_returns_possible_on_exact_public_match(self):
        platform = {
            "name": "GitHub",
            "category": "heuristic",
            "check": "public_profile_email",
            "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
            "items_path": "items",
            "profile_url_field": "url",
            "profile_email_field": "email",
            "label_field": "login",
        }

        async def execute() -> dict:
            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/search/users":
                    return httpx.Response(200, json={"items": [{"login": "octocat", "url": "https://api.github.com/users/octocat"}]})
                if request.url.path == "/users/octocat":
                    return httpx.Response(200, json={"email": "owner@example.test"})
                raise AssertionError(f"Unexpected URL {request.url}")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], POSSIBLE)
        self.assertFalse(result["found"])
        self.assertIn("octocat", result["detail"])
        self.assertEqual(result["public_metadata"]["username"], "octocat")

    def test_gitlab_public_email_match_is_verified_found(self):
        platform = {
            "name": "GitLab",
            "category": "verified",
            "check": "public_profile_email",
            "probe_url": "https://gitlab.com/api/v4/users?search={email}",
            "items_path": "",
            "profile_url_template": "https://gitlab.com/api/v4/users/{id}",
            "profile_email_field": "public_email",
            "label_field": "username",
        }

        async def execute() -> dict:
            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/api/v4/users":
                    return httpx.Response(200, json=[{"id": 42, "username": "gitlab-user"}])
                if request.url.path == "/api/v4/users/42":
                    return httpx.Response(200, json={"public_email": "owner@example.test"})
                raise AssertionError(f"Unexpected URL {request.url}")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], FOUND)
        self.assertTrue(result["found"])
        self.assertIn("gitlab-user", result["detail"])
        self.assertEqual(result["public_metadata"]["username"], "gitlab-user")

    def test_gravatar_found_includes_avatar_hash_metadata(self):
        found = self.run_account_check(
            {"name": "Gravatar", "category": "verified", "check": "gravatar"},
            httpx.Response(200),
        )

        self.assertRegex(found["public_metadata"]["avatar_hash"], r"^[a-f0-9]{32}$")

    def test_gitlab_public_email_miss_stays_unknown(self):
        platform = {
            "name": "GitLab",
            "category": "verified",
            "check": "public_profile_email",
            "probe_url": "https://gitlab.com/api/v4/users?search={email}",
            "items_path": "",
            "profile_url_template": "https://gitlab.com/api/v4/users/{id}",
            "profile_email_field": "public_email",
            "label_field": "username",
        }

        async def execute() -> dict:
            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/api/v4/users":
                    return httpx.Response(200, json=[])
                raise AssertionError(f"Unexpected URL {request.url}")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("missing@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], UNKNOWN)
        self.assertFalse(result["found"])

    def test_gitlab_public_email_timeout_is_error(self):
        platform = {
            "name": "GitLab",
            "category": "verified",
            "check": "public_profile_email",
            "probe_url": "https://gitlab.com/api/v4/users?search={email}",
            "items_path": "",
            "profile_url_template": "https://gitlab.com/api/v4/users/{id}",
            "profile_email_field": "public_email",
            "label_field": "username",
        }

        async def execute() -> dict:
            def handler(_request: httpx.Request) -> httpx.Response:
                raise httpx.ReadTimeout("slow")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], ERROR)

    def test_public_profile_email_without_exact_match_stays_unknown(self):
        platform = {
            "name": "GitHub",
            "category": "heuristic",
            "check": "public_profile_email",
            "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
            "items_path": "items",
            "profile_url_field": "url",
            "profile_email_field": "email",
        }

        async def execute() -> dict:
            def handler(request: httpx.Request) -> httpx.Response:
                if request.url.path == "/search/users":
                    return httpx.Response(200, json={"items": [{"url": "https://api.github.com/users/octocat"}]})
                if request.url.path == "/users/octocat":
                    return httpx.Response(200, json={"email": "someoneelse@example.test"})
                raise AssertionError(f"Unexpected URL {request.url}")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("missing@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["found"])

    def test_public_profile_email_unexpected_response_is_unknown(self):
        platform = {
            "name": "GitHub",
            "category": "heuristic",
            "check": "public_profile_email",
            "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
            "items_path": "items",
            "profile_url_field": "url",
            "profile_email_field": "email",
        }

        result = self.run_account_check(platform, httpx.Response(200, text="not-json"))

        self.assertEqual(result["status"], "UNKNOWN")

    def test_public_profile_email_timeout_is_error(self):
        platform = {
            "name": "GitHub",
            "category": "heuristic",
            "check": "public_profile_email",
            "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
            "items_path": "items",
            "profile_url_field": "url",
            "profile_email_field": "email",
        }

        async def execute() -> dict:
            def handler(_request: httpx.Request) -> httpx.Response:
                raise httpx.ReadTimeout("slow")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], ERROR)

    def test_timeout_or_http_error_is_error(self):
        platform = {
            "name": "Example",
            "category": "heuristic",
            "check": "heuristic",
            "probe_url": "https://example.test/check?email={email}",
        }

        async def execute() -> dict:
            def handler(_request: httpx.Request) -> httpx.Response:
                raise httpx.ReadTimeout("slow")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], ERROR)

    def test_hibp_not_configured_without_api_key(self):
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: self.fail("HIBP should not be called"))
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_haveibeenpwned("owner@example.test", client)

        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(execute())

        self.assertEqual(result["status"], NOT_CONFIGURED)
        self.assertIn("not configured", result["detail"])

    def test_hibp_breaches_are_separate_from_accounts(self):
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"Name": "ExampleBreach"}]))
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_haveibeenpwned("owner@example.test", client)

        with patch.dict("os.environ", {"HIBP_API_KEY": "a" * 32}, clear=False):
            result = asyncio.run(execute())

        self.assertEqual(result["status"], FOUND)
        self.assertEqual(result["section"], "breach")
        self.assertEqual(result["breaches"], ["ExampleBreach"])

    def test_check_email_groups_accounts_and_breaches(self):
        async def fake_account(email, client, platform):
            return {"service": platform["name"], "category": platform["category"], "status": MANUAL, "found": False}

        async def fake_breach(email, client, platform):
            return {"service": platform["name"], "section": "breach", "status": NOT_CONFIGURED, "found": False, "breaches": []}

        with (
            patch.object(checker, "ACCOUNT_PLATFORMS", [{"name": "Manual", "category": "manual"}]),
            patch.object(checker, "BREACH_PLATFORMS", [{"name": "HIBP", "section": "breach"}]),
            patch.object(checker, "check_account_platform", fake_account),
            patch.object(checker, "check_breach_platform", fake_breach),
        ):
            result = asyncio.run(checker.check_email("owner@example.test"))

        self.assertEqual(result["accounts"][0]["status"], MANUAL)
        self.assertEqual(result["breaches"][0]["status"], NOT_CONFIGURED)

    def test_email_console_summary_separates_sections(self):
        results = {
            "accounts": [
                {"service": "GitHub", "status": MANUAL, "found": False, "detail": ""},
            ],
            "breaches": [
                {"service": "Have I Been Pwned", "status": NOT_CONFIGURED, "found": False, "detail": ""},
            ],
        }

        with patch("utils.display.console.print") as console_print:
            print_email_results("test@example.test", results)

        rendered = "\n".join(str(call.args[0]) for call in console_print.call_args_list if call.args)
        self.assertIn("Verified Accounts", rendered)
        self.assertIn("Manual Investigation", rendered)
        self.assertIn("Breaches", rendered)
        self.assertIn("Use --show-manual to display them.", rendered)
        self.assertNotIn("> GitHub", rendered)

    def test_email_console_can_show_manual_entries_on_request(self):
        results = {
            "accounts": [
                {"service": "GitHub", "status": MANUAL, "found": False, "detail": "Manual investigation required"},
            ],
            "breaches": [],
        }

        with patch("utils.display.console.print") as console_print:
            print_email_results("test@example.test", results, show_manual=True)

        rendered = "\n".join(str(call.args[0]) for call in console_print.call_args_list if call.args)
        self.assertIn(">[/cyan] GitHub - Manual investigation required", rendered)


class EmailCatalogAndReportTests(unittest.TestCase):
    def test_catalog_preserves_existing_service_count_and_manual_entries(self):
        names = [name for name, _platform in ALL_SERVICES]

        self.assertEqual(len(names), 110)
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("GitHub", names)
        self.assertIn("Have I Been Pwned", names)
        self.assertTrue(any(item["category"] == "manual" for item in EMAIL_PLATFORMS))
        self.assertTrue(any(name == "GitHub" for name, _platform in AUTOMATIC_ACCOUNT_PLATFORMS))

    def test_report_serializes_email_sections_to_json_and_html(self):
        payload = {
            "osint_email": {
                "target": "owner@example.test",
                "results": {
                    "accounts": [
                        {"service": "Gravatar", "status": FOUND, "found": True, "detail": "avatar"},
                        {"service": "Example", "status": POSSIBLE, "found": False, "detail": "marker"},
                        {"service": "Missing", "status": NOT_FOUND, "found": False, "detail": "HTTP 404"},
                        {"service": "GitHub", "status": MANUAL, "found": False, "detail": ""},
                    ],
                    "breaches": [
                        {
                            "service": "Have I Been Pwned",
                            "status": FOUND,
                            "found": True,
                            "detail": "2 breaches",
                            "breaches": ["A", "B"],
                        }
                    ],
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

        self.assertEqual(json_report["osint_email"]["results"]["accounts"][0]["status"], FOUND)
        self.assertIn("Verified Accounts", html_report)
        self.assertIn("Checked and Not Found", html_report)
        self.assertIn("Breaches", html_report)


if __name__ == "__main__":
    unittest.main()
