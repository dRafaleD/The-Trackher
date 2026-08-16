import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from osint.services import ACCOUNT_DETECTORS, check_account_platform
from utils.platform_health import (
    BROKEN,
    DEGRADED,
    HEALTHY,
    UNKNOWN,
    run_platform_health_check,
)
from utils.reporter import export_to_html, export_to_json


class FakeAsyncClient:
    def __init__(self, handler):
        self._handler = handler
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        request = httpx.Request("GET", url, headers=kwargs.get("headers"))
        self.requests.append(request)
        result = self._handler(request, **kwargs)
        if isinstance(result, Exception):
            raise result
        return result


class PlatformHealthTests(unittest.TestCase):
    def run_health(
        self,
        *,
        account_platforms=None,
        breach_platforms=None,
        username_platforms=None,
        live=False,
        handler=None,
        cache_dir=None,
        ttl_seconds=3600,
        use_cache=False,
    ):
        account_platforms = account_platforms or []
        breach_platforms = breach_platforms or []
        username_platforms = username_platforms or []
        patches = [
            patch("utils.platform_health.ACCOUNT_PLATFORMS", account_platforms),
            patch("utils.platform_health.BREACH_PLATFORMS", breach_platforms),
            patch("utils.platform_health.USERNAME_PLATFORMS", username_platforms),
        ]
        if handler is not None:
            client = FakeAsyncClient(handler)
            patches.append(
                patch(
                    "utils.platform_health.httpx.AsyncClient",
                    side_effect=lambda **kwargs: client,
                )
            )
        else:
            client = None

        with patches[0], patches[1], patches[2]:
            if len(patches) == 4:
                with patches[3]:
                    result = run_platform_health_check(
                        live=live,
                        use_cache=use_cache,
                        cache_dir=cache_dir,
                        ttl_seconds=ttl_seconds,
                    )
            else:
                result = run_platform_health_check(
                    live=live,
                    use_cache=use_cache,
                    cache_dir=cache_dir,
                    ttl_seconds=ttl_seconds,
                )
        return result, client

    def test_healthy_schema(self):
        result, _client = self.run_health(
            account_platforms=[
                {
                    "name": "Gravatar",
                    "category": "verified",
                    "section": "account",
                    "check": "gravatar",
                    "url": "https://gravatar.com/",
                }
            ]
        )

        self.assertEqual(result["counts"][HEALTHY], 1)
        self.assertEqual(result["items"][0]["state"], HEALTHY)

    def test_malformed_platform_is_broken(self):
        result, _client = self.run_health(
            account_platforms=[
                {
                    "name": "Broken",
                    "category": "verified",
                    "section": "account",
                    "check": "gravatar",
                }
            ]
        )

        self.assertEqual(result["items"][0]["state"], BROKEN)
        self.assertIn("Missing required field: url", result["items"][0]["detail"])

    def test_unsupported_detector_is_broken(self):
        result, _client = self.run_health(
            username_platforms=[
                {
                    "name": "Unsupported",
                    "url": "https://example.test/{}",
                    "error_type": "message",
                    "error_msg": "not found",
                    "reliability": "verified",
                    "check": "xmlrpc",
                }
            ]
        )

        self.assertEqual(result["items"][0]["state"], BROKEN)
        self.assertIn("Unsupported detector type", result["items"][0]["detail"])

    def test_safe_live_success(self):
        result, client = self.run_health(
            username_platforms=[
                {
                    "name": "Example",
                    "url": "https://example.test/users/{}",
                    "error_type": "status_code",
                    "expected_status": [404],
                    "reliability": "verified",
                    "check": "html",
                }
            ],
            live=True,
            handler=lambda request, **kwargs: httpx.Response(404, request=request),
        )

        self.assertEqual(result["items"][0]["state"], HEALTHY)
        self.assertEqual(client.requests[0].method, "GET")

    def test_timeout_becomes_degraded(self):
        result, _client = self.run_health(
            username_platforms=[
                {
                    "name": "Example",
                    "url": "https://example.test/users/{}",
                    "error_type": "status_code",
                    "expected_status": [404],
                    "reliability": "verified",
                    "check": "html",
                }
            ],
            live=True,
            handler=lambda request, **kwargs: httpx.ReadTimeout("slow"),
        )

        self.assertEqual(result["items"][0]["state"], DEGRADED)

    def test_rate_limit_becomes_degraded(self):
        result, _client = self.run_health(
            username_platforms=[
                {
                    "name": "Example",
                    "url": "https://example.test/users/{}",
                    "error_type": "status_code",
                    "expected_status": [404],
                    "reliability": "verified",
                    "check": "html",
                }
            ],
            live=True,
            handler=lambda request, **kwargs: httpx.Response(429, request=request),
        )

        self.assertEqual(result["items"][0]["state"], DEGRADED)

    def test_unexpected_response_becomes_unknown(self):
        result, _client = self.run_health(
            account_platforms=[
                {
                    "name": "GitHub",
                    "category": "heuristic",
                    "section": "account",
                    "check": "public_profile_email",
                    "url": "https://github.com/",
                    "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
                    "items_path": "items",
                    "profile_url_field": "url",
                    "profile_email_field": "email",
                }
            ],
            live=True,
            handler=lambda request, **kwargs: httpx.Response(200, request=request, text="not-json"),
        )

        self.assertEqual(result["items"][0]["state"], UNKNOWN)

    def test_cache_behavior_reuses_recent_live_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            first, first_client = self.run_health(
                username_platforms=[
                    {
                        "name": "Example",
                        "url": "https://example.test/users/{}",
                        "error_type": "status_code",
                        "expected_status": [404],
                        "reliability": "verified",
                        "check": "html",
                    }
                ],
                live=True,
                handler=lambda request, **kwargs: httpx.Response(404, request=request),
                cache_dir=cache_dir,
                use_cache=True,
            )
            second, second_client = self.run_health(
                username_platforms=[
                    {
                        "name": "Example",
                        "url": "https://example.test/users/{}",
                        "error_type": "status_code",
                        "expected_status": [404],
                        "reliability": "verified",
                        "check": "html",
                    }
                ],
                live=True,
                handler=lambda request, **kwargs: self.fail("live probe should have been cached"),
                cache_dir=cache_dir,
                use_cache=True,
            )

        self.assertEqual(first["items"][0]["state"], HEALTHY)
        self.assertEqual(second["items"][0]["state"], HEALTHY)
        self.assertEqual(second["cache_hits"], 1)
        self.assertEqual(len(first_client.requests), 1)
        self.assertEqual(len(second_client.requests), 0)

    def test_one_health_failure_does_not_disable_detector(self):
        result, _client = self.run_health(
            account_platforms=[
                {
                    "name": "Gravatar",
                    "category": "verified",
                    "section": "account",
                    "check": "gravatar",
                    "url": "https://gravatar.com/",
                }
            ],
            live=True,
            handler=lambda request, **kwargs: httpx.ReadTimeout("slow"),
        )

        self.assertEqual(result["items"][0]["state"], DEGRADED)
        self.assertIsNotNone(ACCOUNT_DETECTORS.get("gravatar"))

        async def execute():
            transport = httpx.MockTransport(lambda request: httpx.Response(404, request=request))
            async with httpx.AsyncClient(transport=transport) as client:
                return await check_account_platform(
                    "owner@example.test",
                    client,
                    {
                        "name": "Gravatar",
                        "category": "verified",
                        "check": "gravatar",
                        "url": "https://gravatar.com/",
                    },
                )

        follow_up = asyncio.run(execute())
        self.assertEqual(follow_up["status"], "NOT_FOUND")

    def test_no_side_effect_detector_paths_are_used(self):
        account = {
            "name": "GitHub",
            "category": "heuristic",
            "section": "account",
            "check": "public_profile_email",
            "url": "https://github.com/",
            "probe_url": "https://api.github.com/search/users?q=%22{email}%22%20in:email",
            "items_path": "items",
            "profile_url_template": "https://api.github.com/users/{id}",
            "profile_email_field": "email",
        }

        result, client = self.run_health(
            account_platforms=[account],
            live=True,
            handler=lambda request, **kwargs: httpx.Response(200, request=request, json={"items": []}),
        )

        self.assertEqual(result["items"][0]["state"], HEALTHY)
        urls = [str(request.url) for request in client.requests]
        self.assertEqual(len(urls), 1)
        self.assertIn("/search/users", urls[0])
        self.assertFalse(any("/users/" in url for url in urls))

    def test_health_report_serializes_separately(self):
        payload, _client = self.run_health(
            account_platforms=[
                {
                    "name": "Gravatar",
                    "category": "verified",
                    "section": "account",
                    "check": "gravatar",
                    "url": "https://gravatar.com/",
                }
            ]
        )
        report_data = {"platform_health": payload}

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "health.json"
            html_path = Path(temp_dir) / "health.html"
            export_to_json(report_data, str(json_path))
            export_to_html(report_data, str(html_path))
            json_report = json.loads(json_path.read_text(encoding="utf-8"))
            html_report = html_path.read_text(encoding="utf-8")

        self.assertIn("platform_health", json_report)
        self.assertIn("Platform / Detector Health", html_report)


if __name__ == "__main__":
    unittest.main()
