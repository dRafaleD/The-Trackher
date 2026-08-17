import asyncio
import unittest

import httpx

from osint.detector_runtime import (
    DetectorRegistry,
    normalize_breach_result,
    normalize_email_result,
    normalize_username_result,
)
from osint.services import ACCOUNT_DETECTORS, BREACH_DETECTORS, check_account_platform
from osint.username_checker import USERNAME_DETECTORS


class DetectorRegistryTests(unittest.TestCase):
    def test_registry_supports_registration_and_lookup(self):
        registry = DetectorRegistry()

        async def detector(*_args, **_kwargs):
            return {"status": "ok"}

        registry.register("sample", detector)

        self.assertEqual(registry.names(), ("sample",))
        self.assertIs(registry.get("sample"), detector)
        self.assertIsNone(registry.get("missing"))

    def test_builtin_detector_registries_expose_expected_names(self):
        self.assertIn("manual", ACCOUNT_DETECTORS.names())
        self.assertIn("public_profile_email", ACCOUNT_DETECTORS.names())
        self.assertIn("hibp", BREACH_DETECTORS.names())
        self.assertIn("html", USERNAME_DETECTORS.names())
        self.assertIn("content", USERNAME_DETECTORS.names())
        self.assertIn("json", USERNAME_DETECTORS.names())
        self.assertIn("graphql", USERNAME_DETECTORS.names())


class NormalizationTests(unittest.TestCase):
    def test_verified_and_heuristic_email_normalization_preserves_states(self):
        platform = {"name": "GitLab", "category": "verified", "url": "https://gitlab.com/"}
        verified = normalize_email_result(platform, "FOUND", "exact")
        heuristic = normalize_email_result(
            {"name": "GitHub", "category": "heuristic", "url": "https://github.com/"},
            "POSSIBLE",
            "marker",
        )

        self.assertTrue(verified["found"])
        self.assertEqual(verified["status"], "FOUND")
        self.assertFalse(heuristic["found"])
        self.assertEqual(heuristic["status"], "POSSIBLE")

    def test_username_and_breach_normalization_keep_expected_shape(self):
        username = normalize_username_result({"name": "Reddit", "reliability": "verified"}, status="found")
        breach = normalize_breach_result({"name": "HIBP", "section": "breach"}, "ERROR", "boom")

        self.assertEqual(username["platform"], "Reddit")
        self.assertTrue(username["found"])
        self.assertEqual(breach["section"], "breach")
        self.assertEqual(breach["status"], "ERROR")
        self.assertEqual(breach["breaches"], [])


class DetectorIsolationTests(unittest.TestCase):
    def test_email_detector_exception_is_normalized(self):
        platform = {
            "name": "Explodes",
            "category": "verified",
            "check": "boom",
            "url": "https://example.test/",
        }

        async def execute() -> dict:
            async def broken(_email, _client, _platform):
                raise RuntimeError("broken")

            ACCOUNT_DETECTORS.register("boom", broken)
            transport = httpx.MockTransport(lambda request: httpx.Response(200))
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform("owner@example.test", client, platform)

        result = asyncio.run(execute())

        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["found"])
        self.assertEqual(result["detail"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
