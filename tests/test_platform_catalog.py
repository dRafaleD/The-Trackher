import asyncio
import json
import unittest

import httpx

from osint.username_checker import PLATFORMS_PATH, USERNAME_PLATFORMS, check_single_username


class PlatformCatalogTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        with open(PLATFORMS_PATH, "r", encoding="utf-8") as file_obj:
            cls.raw_platforms = json.load(file_obj)

    def _set_json_value(self, data: dict, path: str, value):
        current = data
        parts = path.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value

    def _found_response(self, platform: dict, username: str) -> httpx.Response:
        check = platform.get("check", "html")
        if check == "json":
            payload: dict = {}
            self._set_json_value(payload, platform["json_path"], username)
            return httpx.Response(200, json=payload)
        if check == "json_list":
            item: dict = {}
            self._set_json_value(item, platform["json_path"], username)
            if platform.get("profile_id_path"):
                self._set_json_value(item, platform["profile_id_path"], "42")
            payload: dict = {}
            self._set_json_value(payload, platform["json_list_path"], [item])
            return httpx.Response(200, json=payload)
        body = f"<html><title>{username}</title><body><h1>{username}</h1></body></html>"
        return httpx.Response(200, text=body)

    def _missing_response(self, platform: dict, username: str) -> httpx.Response:
        error_type = platform.get("error_type", "message")
        if error_type == "status_code":
            expected = platform.get("expected_status", [404])
            status_code = expected[0] if isinstance(expected, list) else expected
            return httpx.Response(int(status_code))
        if error_type == "response_url":
            request = httpx.Request("GET", f"https://example.test/{username}")
            redirect = httpx.Response(302, request=request)
            return httpx.Response(
                200,
                request=request,
                history=[redirect],
                text="<html><title>Community</title><body>Welcome</body></html>",
            )
        return httpx.Response(
            200,
            text=f"<html><title>{username}</title><body>Profile not found</body></html>",
        )

    def _run_platform(self, platform: dict, response: httpx.Response, username: str) -> dict:
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: response)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_single_username(username, platform, client)

        return asyncio.run(execute())

    def test_json_catalog_entries_have_required_fields(self):
        self.assertEqual(len(self.raw_platforms), 197)
        self.assertEqual(len(self.raw_platforms), len(USERNAME_PLATFORMS))

        allowed_error_types = {"status_code", "message", "response_url"}
        allowed_reliability = {"verified", "unreliable"}

        for platform in self.raw_platforms:
            with self.subTest(platform=platform["name"]):
                self.assertIn("name", platform)
                self.assertIn("url_pattern", platform)
                self.assertIn("{username}", platform["url_pattern"])
                self.assertIn(platform["error_type"], allowed_error_types)
                self.assertIn(platform["reliability"], allowed_reliability)
                if platform["error_type"] == "status_code":
                    self.assertIn("expected_status", platform)
                if platform["error_type"] == "message":
                    self.assertIn("error_msg", platform)

    def test_every_platform_definition_supports_found_and_missing_scenarios(self):
        username = "fixture_user"

        for platform in USERNAME_PLATFORMS:
            with self.subTest(platform=platform["name"], scenario="found"):
                result = self._run_platform(
                    platform,
                    self._found_response(platform, username),
                    username,
                )
                self.assertEqual(result["status"], "found")
                self.assertTrue(result["found"])
                self.assertEqual(result["reliability"], platform["reliability"])
                if platform.get("check") == "json_list" and platform.get("profile_url"):
                    self.assertTrue(result["url"].endswith("/42"))

            with self.subTest(platform=platform["name"], scenario="missing"):
                result = self._run_platform(
                    platform,
                    self._missing_response(platform, username),
                    username,
                )
                self.assertEqual(result["status"], "not_found")
                self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
