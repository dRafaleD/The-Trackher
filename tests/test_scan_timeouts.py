"""Scans must finish even when the final response never stops streaming."""
import asyncio
import unittest
from unittest.mock import patch

import httpx

from osint import checker, username_checker
from osint.request_policy import PoliteAsyncClient
from osint.services import check_gravatar


class NeverEndingBody(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        while True:
            await asyncio.sleep(0.005)
            yield b'x'

    async def aclose(self):
        self.closed = True


class ScanTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_username_inherits_client_timeout_instead_of_disabling_it(self):
        observed = []
        def handler(request):
            observed.append(request.extensions['timeout'])
            return httpx.Response(403)
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=8), transport=httpx.MockTransport(handler)) as client:
            platform = {'name': 'Test', 'url': 'https://example.test/{}', 'check': 'content'}
            await username_checker.check_single_username('sample', platform, client)
            await username_checker.check_single_username('sample', dict(platform, timeout_seconds='invalid'), client)
            await username_checker.check_single_username('sample', dict(platform, timeout_seconds=20), client)
        self.assertEqual(observed[0], {'connect': 8, 'read': 12, 'write': 12, 'pool': 12})
        self.assertEqual(observed[1], observed[0])
        self.assertTrue(all(value == 20 for value in observed[2].values()))

    async def test_total_deadline_closes_body_and_releases_concurrency_slot(self):
        body = NeverEndingBody()
        started = asyncio.Event()
        def handler(request):
            if request.url.host == 'slow.test':
                started.set()
                return httpx.Response(200, stream=body)
            return httpx.Response(200, text='done')
        async with httpx.AsyncClient(timeout=.05, transport=httpx.MockTransport(handler)) as raw:
            client = PoliteAsyncClient(raw, max_concurrent=1, origin_interval_seconds=0)
            pending = asyncio.create_task(client.get('https://slow.test/'))
            await asyncio.wait_for(started.wait(), .5)
            queued = asyncio.create_task(client.get('https://fast.test/'))
            with self.assertRaises(httpx.ReadTimeout):
                await asyncio.wait_for(pending, .5)
            response = await asyncio.wait_for(queued, .5)
            self.assertEqual(response.text, 'done')
        self.assertTrue(body.closed)

    async def test_email_detector_reports_timeout_for_endless_response(self):
        body = NeverEndingBody()
        async with httpx.AsyncClient(timeout=.05, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body))) as raw:
            client = PoliteAsyncClient(raw, origin_interval_seconds=0)
            result = await asyncio.wait_for(check_gravatar('diagnostic@example.invalid', client), .5)
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['unknown_cause'], 'timeout')
        self.assertFalse(result['found'])
        self.assertTrue(body.closed)

    async def test_username_scan_completes_with_final_site_timeout(self):
        platform = {'name': 'Slow', 'url': 'https://example.test/{}', 'check': 'content', 'reliability': 'verified'}
        raw = httpx.AsyncClient(timeout=.05, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=NeverEndingBody())))
        with patch.object(username_checker, 'USERNAME_PLATFORMS', [platform]), patch.object(username_checker.httpx, 'AsyncClient', return_value=raw):
            results = await asyncio.wait_for(username_checker.check_username_async('sample'), .5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'unknown')
        self.assertEqual(results[0]['unknown_cause'], 'timeout')

    async def test_email_scan_completes_with_final_service_timeout(self):
        raw = httpx.AsyncClient(timeout=.05, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=NeverEndingBody())))
        async def domain(*args):
            return {'domain': 'example.invalid', 'status': 'UNKNOWN', 'mail_routable': None, 'mx_hosts': []}
        with patch.object(checker, 'ACCOUNT_PLATFORMS', [{'name': 'Gravatar', 'check': 'gravatar', 'category': 'verified', 'retry_attempts': 1}]), patch.object(checker, 'BREACH_PLATFORMS', []), patch.object(checker, 'check_email_domain', domain), patch.object(checker.httpx, 'AsyncClient', return_value=raw):
            results = await asyncio.wait_for(checker.check_email('diagnostic@example.invalid'), .5)
        self.assertEqual(len(results['accounts']), 1)
        self.assertEqual(results['accounts'][0]['unknown_cause'], 'timeout')

    async def test_no_timeout_and_large_override_still_have_finite_total_limit(self):
        async with httpx.AsyncClient(timeout=None) as raw:
            client = PoliteAsyncClient(raw)
            self.assertEqual(client._request_duration({}), 30)
            self.assertEqual(client._request_duration({'timeout': None}), 30)
            self.assertEqual(client._request_duration({'timeout': 600}), 30)
            self.assertEqual(client._request_duration({'timeout': 20}), 20)
