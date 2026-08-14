import asyncio
import inspect
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from osint import checker
from osint.services import (
    ALL_SERVICES,
    PASSIVE_SERVICES,
    _found,
    check_gravatar,
    check_haveibeenpwned,
)
from utils.display import print_email_results


class EmailDetectionTests(unittest.TestCase):
    def run_check(self, check_fn, response: httpx.Response) -> dict:
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: response)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_fn("new-account@example.test", client)

        return asyncio.run(execute())

    def test_unverified_positive_is_not_reported_as_an_account(self):
        result = _found("Example", "Hesap var izlenimi")

        self.assertFalse(result["found"])
        self.assertEqual(result["status"], "unknown")

    def test_gravatar_uses_documented_status_codes(self):
        found = self.run_check(check_gravatar, httpx.Response(200))
        missing = self.run_check(check_gravatar, httpx.Response(404))

        self.assertEqual(found["status"], "found")
        self.assertEqual(missing["status"], "not_found")

    def test_hibp_requires_an_explicit_api_key_without_network_access(self):
        def reject_request(_request: httpx.Request) -> httpx.Response:
            self.fail("HIBP request should not be sent without an API key")

        async def execute() -> dict:
            transport = httpx.MockTransport(reject_request)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_haveibeenpwned("owner@example.test", client)

        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(execute())

        self.assertEqual(result["status"], "unknown")
        self.assertIn("HIBP_API_KEY", result["detail"])

    def test_hibp_structured_result_is_verified(self):
        response = httpx.Response(200, json=[{"Name": "ExampleBreach"}])
        with patch.dict("os.environ", {"HIBP_API_KEY": "a" * 32}, clear=False):
            result = self.run_check(check_haveibeenpwned, response)

        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "found")
        self.assertIn("ExampleBreach", result["detail"])

    def test_email_console_summary_separates_unknown_results(self):
        results = [
            {"service": "Example", "found": False, "status": "unknown", "detail": ""}
        ]

        with patch("utils.display.console.print") as console_print:
            print_email_results("test@example.test", results)

        summary = console_print.call_args_list[-1].args[0]
        self.assertIn("sonuç doğrulanamadı", summary)


class EmailSafetyTests(unittest.TestCase):
    def test_catalog_counts_and_names_are_stable(self):
        names = [name for name, _check in ALL_SERVICES]

        self.assertEqual(len(names), 110)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(PASSIVE_SERVICES), 2)
        self.assertIn("Sorbil", names)

    def test_passive_allowlist_contains_only_get_checks(self):
        self.assertGreater(len(PASSIVE_SERVICES), 0)
        self.assertLess(len(PASSIVE_SERVICES), len(ALL_SERVICES))
        for name, check_fn in PASSIVE_SERVICES:
            with self.subTest(service=name):
                self.assertNotIn("client.post", inspect.getsource(check_fn))

    def test_reported_false_positive_services_are_catalog_only(self):
        passive_names = {name for name, _check in PASSIVE_SERVICES}
        catalog_names = {name for name, _check in ALL_SERVICES}
        risky_names = {"Last.fm", "VK", "Dribbble", "BiTaksi", "Papara", "iyzico", "Biletix"}

        self.assertTrue(risky_names.issubset(catalog_names))
        self.assertTrue(risky_names.isdisjoint(passive_names))

    def test_side_effectful_check_is_skipped_without_being_called(self):
        unsafe_check = AsyncMock()
        with (
            patch.object(checker, "ALL_SERVICES", [("Unsafe", unsafe_check)]),
            patch.object(checker, "PASSIVE_SERVICE_FUNCTIONS", frozenset()),
        ):
            results = asyncio.run(checker.check_email("owner@example.test"))

        unsafe_check.assert_not_awaited()
        self.assertEqual(results[0]["status"], "skipped")
        self.assertIn("gönderilmedi", results[0]["detail"])


if __name__ == "__main__":
    unittest.main()
