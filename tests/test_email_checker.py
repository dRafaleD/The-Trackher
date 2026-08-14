import asyncio
import unittest
from unittest.mock import patch

import httpx

from osint.services import (
    check_biletix,
    check_bitaksi,
    check_dribbble,
    check_iyzico,
    check_lastfm,
    check_papara,
    check_vk,
)
from utils.display import print_email_results


class EmailDetectionTests(unittest.TestCase):
    def run_check(self, check_fn, response: httpx.Response) -> dict:
        async def execute() -> dict:
            transport = httpx.MockTransport(lambda request: response)
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_fn("new-account@example.test", client)

        return asyncio.run(execute())

    def test_heuristic_responses_are_not_reported_as_verified_accounts(self):
        cases = [
            (check_lastfm, httpx.Response(200, json={"email": {"valid": False}})),
            (check_vk, httpx.Response(200, text="email")),
            (check_dribbble, httpx.Response(200, text="email")),
            (check_bitaksi, httpx.Response(200, json={"success": True})),
            (check_papara, httpx.Response(200, json={"success": True})),
            (check_iyzico, httpx.Response(200, json={"success": True})),
            (check_biletix, httpx.Response(200, json={"success": True})),
        ]

        for check_fn, response in cases:
            with self.subTest(check=check_fn.__name__):
                result = self.run_check(check_fn, response)
                self.assertFalse(result["found"])
                self.assertEqual(result["status"], "unknown")

    def test_email_console_summary_separates_unknown_results(self):
        results = [
            {"service": "Example", "found": False, "status": "unknown", "detail": ""}
        ]

        with patch("utils.display.console.print") as console_print:
            print_email_results("test@example.test", results)

        summary = console_print.call_args_list[-1].args[0]
        self.assertIn("sonuç doğrulanamadı", summary)


if __name__ == "__main__":
    unittest.main()
