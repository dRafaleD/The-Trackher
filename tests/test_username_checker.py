import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from osint.username_checker import (
    USERNAME_PLATFORMS,
    _ENTERTAINMENT_FORUM_PLATFORMS,
    check_single_username,
)
from utils.display import print_username_results
from utils.reporter import UNRELIABLE_WARNING, export_to_html, export_to_json


class UsernameDetectionTests(unittest.TestCase):
    def run_check(
        self,
        handler,
        platform: dict | None = None,
        username: str = "missing_user_123",
    ) -> dict:
        target = platform or {
            "name": "Example",
            "url": "https://example.test/users/{}",
        }

        async def execute() -> dict:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_single_username(username, target, client)

        return asyncio.run(execute())

    def test_generic_200_page_is_not_reported_as_found(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<html><title>Community</title><body>Welcome</body></html>",
            )
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")

    def test_not_found_page_that_echoes_username_stays_not_found(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<h1>User missing_user_123</h1><p>Profile not found</p>",
            )
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "not_found")

    def test_visible_exact_username_is_reported_as_found(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<html><title>missing_user_123</title><h1>missing_user_123</h1></html>",
            )
        )

        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "found")

    def test_non_success_response_is_unknown(self):
        result = self.run_check(
            lambda request: httpx.Response(403, text="Access denied")
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "bot_blocked")

    def test_plain_forbidden_response_has_forbidden_cause(self):
        result = self.run_check(
            lambda request: httpx.Response(403, text="Forbidden")
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "forbidden")

    def test_rate_limit_response_has_rate_limited_cause(self):
        result = self.run_check(
            lambda request: httpx.Response(429, text="Too many requests")
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "rate_limited")

    def test_malformed_platform_configuration_is_isolated(self):
        result = self.run_check(
            lambda request: httpx.Response(500),
            platform={"name": "Broken Platform"},
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertIn("yapılandırma", result["detail"])

    def test_unsupported_detector_type_is_isolated(self):
        result = self.run_check(
            lambda request: httpx.Response(200),
            platform={
                "name": "Unsupported Platform",
                "url": "https://example.test/users/{}",
                "check": "xmlrpc",
            },
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertIn("Desteklenmeyen detector tipi", result["detail"])
        self.assertEqual(result["unknown_cause"], "unsupported_detector")

    def test_successful_bot_challenge_page_is_unknown(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<title>Just a moment...</title><p>Verify you are human</p>",
            )
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "bot_blocked")

    def test_title_only_username_is_not_enough_for_found(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<html><title>missing_user_123 profile</title><body>Loading</body></html>",
            )
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "parser_mismatch")

    def test_platform_can_disable_generic_html_found(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text="<html><body><h1>missing_user_123</h1></body></html>",
            ),
            platform={
                "name": "Echoing Search Page",
                "url": "https://example.test/{}",
                "disable_html_found": True,
            },
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "parser_mismatch")

    def test_not_found_redirect_marker_fixture(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            request = httpx.Request("GET", "https://giphy.test/explore/missing_user_123")
            redirect = httpx.Response(301, request=httpx.Request("GET", "https://giphy.test/missing_user_123"))
            return httpx.Response(
                200,
                request=request,
                history=[redirect],
                text="<html><title>missing_user_123 GIFs</title><body>missing_user_123</body></html>",
            )

        result = self.run_check(
            handler,
            platform={
                "name": "Giphy Example",
                "url": "https://giphy.test/explore/{}",
                "not_found_url_contains": ["giphy.test/explore/"],
            },
        )

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["diagnostic_cause"], "redirect_changed")

    def test_json_probe_requires_exact_username(self):
        platform = {
            "name": "JSON Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://api.example.test/users/{}",
            "check": "json",
            "json_path": "user.username",
        }
        found = self.run_check(
            lambda request: httpx.Response(
                200, json={"user": {"username": "missing_user_123"}}
            ),
            platform,
        )
        missing = self.run_check(
            lambda request: httpx.Response(200, json={"user": {"username": None}}),
            platform,
        )

        self.assertEqual(found["status"], "found")
        self.assertEqual(missing["status"], "not_found")
        self.assertEqual(found["public_metadata"]["username"], "missing_user_123")
        self.assertEqual(missing["diagnostic_cause"], "soft_404")

    def test_json_probe_parser_mismatch_has_cause(self):
        platform = {
            "name": "JSON Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://api.example.test/users/{}",
            "check": "json",
            "json_path": "user.username",
        }
        result = self.run_check(
            lambda request: httpx.Response(200, text="not-json"),
            platform,
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_cause"], "parser_mismatch")

    def test_json_list_supports_root_array(self):
        platform = {
            "name": "GitLab Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://api.example.test/users?username={}",
            "check": "json_list",
            "json_list_path": "",
            "json_path": "username",
        }
        found = self.run_check(
            lambda request: httpx.Response(200, json=[{"username": "missing_user_123"}]),
            platform,
        )
        missing = self.run_check(
            lambda request: httpx.Response(200, json=[]),
            platform,
        )

        self.assertEqual(found["status"], "found")
        self.assertEqual(missing["status"], "not_found")

    def test_raw_not_found_marker_can_resolve_soft_404(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text='<html><title></title><script>{"message":"User not found."}</script></html>',
            ),
            platform={
                "name": "Pinterest Example",
                "url": "https://example.test/{}",
                "raw_not_found_markers": ["User not found."],
            },
        )

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["diagnostic_cause"], "soft_404")

    def test_raw_found_marker_can_confirm_profile(self):
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                text='<html><head><meta property="og:url" content="https://example.test/users/missing_user_123"></head></html>',
            ),
            platform={
                "name": "Facebook Example",
                "url": "https://example.test/users/{}",
                "raw_found_markers": ['content="https://example.test/users/{username}"'],
            },
        )

        self.assertEqual(result["status"], "found")
        self.assertTrue(result["found"])

    def test_graphql_detector_supports_existing_and_missing_user(self):
        platform = {
            "name": "AniList Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://graphql.example.test",
            "check": "graphql",
            "accept": "application/json",
            "expected_status": [404],
            "query_body": {
                "query": "query ($name: String) { User(name: $name) { name } }",
                "variables": {"name": "{username}"},
            },
            "json_path": "data.User.name",
        }

        async def execute() -> tuple[dict, dict]:
            captured = []

            def handler(request: httpx.Request) -> httpx.Response:
                captured.append(request.read().decode("utf-8"))
                if "missing_user_123" in captured[-1]:
                    return httpx.Response(200, json={"data": {"User": {"name": "missing_user_123"}}})
                return httpx.Response(404, json={"errors": [{"message": "Not Found."}], "data": {"User": None}})

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                found = await check_single_username("missing_user_123", platform, client)
                missing = await check_single_username("absent_user_404", platform, client)
            return found, missing

        found, missing = asyncio.run(execute())

        self.assertEqual(found["status"], "found")
        self.assertEqual(missing["status"], "not_found")

    def test_json_probe_can_extract_public_metadata(self):
        platform = {
            "name": "GitHub Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://api.example.test/users/{}",
            "check": "json",
            "json_path": "login",
            "metadata_fields": {
                "display_name": "name",
                "website": "blog",
            },
        }
        result = self.run_check(
            lambda request: httpx.Response(
                200,
                json={
                    "login": "missing_user_123",
                    "name": "Missing User",
                    "blog": "https://example.test",
                },
            ),
            platform,
        )

        self.assertEqual(result["public_metadata"]["display_name"], "Missing User")
        self.assertEqual(result["public_metadata"]["website"], "https://example.test")

    def test_json_list_resolves_verified_profile_id(self):
        platform = {
            "name": "Kitsu Example",
            "url": "https://example.test/users/{}",
            "probe_url": "https://api.example.test/users?name={}",
            "check": "json_list",
            "accept": "application/vnd.api+json",
            "json_list_path": "data",
            "json_path": "attributes.name",
            "profile_id_path": "id",
            "profile_url": "https://example.test/users/{}",
        }
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.headers["accept"], "application/vnd.api+json"
            )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "42", "attributes": {"name": "missing_user_123"}}
                    ]
                },
            )

        result = self.run_check(handler, platform)

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["url"], "https://example.test/users/42")

    def test_username_is_safely_encoded_in_request_and_result_url(self):
        requested_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(404)

        result = self.run_check(handler, username="name with space")

        self.assertIn("name%20with%20space", requested_urls[0])
        self.assertIn("name%20with%20space", result["url"])


class UsernamePlatformTests(unittest.TestCase):
    def test_entertainment_and_forum_group_contains_30_unique_sites(self):
        names = [item["name"] for item in _ENTERTAINMENT_FORUM_PLATFORMS]

        self.assertEqual(len(names), 30)
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("Kayıp Rıhtım Forum", names)
        self.assertIn("YazBel Forum", names)
        self.assertIn("Pardus Forumları", names)

    def test_all_platform_names_are_unique(self):
        names = [item["name"] for item in USERNAME_PLATFORMS]

        self.assertEqual(len(names), len(set(names)))

    def test_all_platform_urls_are_https_and_renderable(self):
        for platform in USERNAME_PLATFORMS:
            with self.subTest(platform=platform["name"]):
                self.assertTrue(platform["url"].startswith("https://"))
                self.assertTrue(platform["url"].format("probe").startswith("https://"))
                if "probe_url" in platform:
                    self.assertTrue(
                        platform["probe_url"].format("probe").startswith("https://")
                    )


class UsernameReportTests(unittest.TestCase):
    def test_console_summary_counts_unknown_results(self):
        results = [
            {
                "platform": "Blocked Site",
                "url": "https://example.test/test-user",
                "found": False,
                "status": "unknown",
                "unknown_cause": "bot_blocked",
            }
        ]

        with patch("utils.display.console.print") as console_print:
            print_username_results("test-user", results)

        rendered = [
            call.args[0]
            for call in console_print.call_args_list
            if call.args and isinstance(call.args[0], str)
        ]
        summary = next(text for text in rendered if "sonuç doğrulanamadı" in text)
        self.assertIn("1 sonuç doğrulanamadı", summary)
        breakdown = next(text for text in rendered if "Doğrulanamayan nedenler:" in text)
        self.assertIn("bot blocked 1", breakdown)

    def test_unknown_result_is_not_rendered_as_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.html"
            export_to_html(
                {
                    "osint_username": {
                        "target": "test-user",
                        "results": [
                            {
                                "platform": "Blocked Site",
                                "url": "https://example.test/test-user",
                                "found": False,
                                "status": "unknown",
                                "unknown_cause": "bot_blocked",
                            }
                        ],
                    }
                },
                str(output),
            )
            report = output.read_text(encoding="utf-8")

        self.assertIn("Doğrulanamadı", report)
        self.assertIn('class="unknown"', report)
        self.assertIn("bot blocked", report)

    def test_unreliable_platform_warning_is_rendered_in_html_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.html"
            export_to_html(
                {
                    "osint_username": {
                        "target": "test-user",
                        "results": [
                            {
                                "platform": "Heuristic Site",
                                "url": "https://example.test/test-user",
                                "found": True,
                                "status": "found",
                                "reliability": "unreliable",
                            }
                        ],
                    }
                },
                str(output),
            )
            report = output.read_text(encoding="utf-8")

        self.assertIn(UNRELIABLE_WARNING, report)

    def test_unreliable_platform_warning_is_exported_in_json_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.json"
            export_to_json(
                {
                    "osint_username": {
                        "target": "test-user",
                        "results": [
                            {
                                "platform": "Heuristic Site",
                                "url": "https://example.test/test-user",
                                "found": True,
                                "status": "found",
                                "reliability": "unreliable",
                            }
                        ],
                    }
                },
                str(output),
            )
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            report["osint_username"]["results"][0]["warning"],
            UNRELIABLE_WARNING,
        )


if __name__ == "__main__":
    unittest.main()
