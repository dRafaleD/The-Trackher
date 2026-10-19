"""Passive candidates, source attribution and bounded homepage references."""
import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from osint.organization import research_brand, research_organization, _public_addresses


class OrganizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_homepage_http_timeout_is_not_a_generic_network_error(self):
        def handler(request):
            raise httpx.ReadTimeout('read deadline', request=request)
        rows = await self.org(handler)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertEqual(rows[0]['unknown_cause'], 'timeout')

    async def org(self, handler, domain='acme.com'):
        def html_handler(request):
            response = handler(request)
            if response.status_code == 200:
                response.headers['content-type'] = 'text/html; charset=utf-8'
            return response
        async with httpx.AsyncClient(transport=httpx.MockTransport(html_handler)) as client:
            with patch('osint.organization._public_addresses', new=AsyncMock(return_value='8.8.8.8')):
                return await research_organization(domain, client)

    async def test_homepage_only_public_visible_links_and_pinned_address(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url), 'https://8.8.8.8/')
            self.assertEqual(request.headers['host'], 'acme.com')
            self.assertEqual(request.extensions['sni_hostname'], 'acme.com')
            return httpx.Response(200, text='''
              <a href="https://github.com/acme">Social</a>
              <a href="https://partner.com/">Partner</a>
              <a href="https://partner.com/">Duplicate</a>
              <a href="/about">Internal</a><a href="http://127.0.0.1/">Unsafe</a>
              <script><a href="https://fake.com/">Script</a></script>
              <!-- <a href="https://comment.com/">Comment</a> -->
              <div hidden><a href="https://hidden.com/">Hidden</a></div>
              <template><a href="https://template.com/">Template</a></template>''')
        rows = await self.org(handler)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['public_metadata']['category'], 'catalog_profile')
        self.assertEqual(rows[0]['public_metadata']['linked_platform'], 'GitHub')
        self.assertEqual(rows[1]['public_metadata']['category'], 'external_domain')
        self.assertTrue(all(r['public_metadata']['source_url'] == 'https://acme.com/' for r in rows))
        self.assertFalse(rows[0]['public_metadata']['ownership_verified'])

    async def test_private_resolution_never_fetched(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: self.fail('unsafe fetch'))) as client:
            with patch('osint.organization._public_addresses', new=AsyncMock(return_value='')):
                rows = await research_organization('acme.com', client)
        self.assertEqual(rows[0]['unknown_cause'], 'unsafe_target')

    async def test_mixed_public_private_dns_rejected(self):
        resolver = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
                                           (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', resolver):
            self.assertEqual(await _public_addresses('acme.com'), '')

    async def test_redirect_blocked_empty_and_large(self):
        for code in (302, 403, 429):
            rows = await self.org(lambda _: httpx.Response(code, headers={'Location': 'http://127.0.0.1/'}))
            self.assertEqual(rows[0]['status'], 'unknown')
        rows = await self.org(lambda _: httpx.Response(200, text='<html>No outgoing links</html>'))
        self.assertEqual(rows[0]['status'], 'not_found')
        rows = await self.org(lambda _: httpx.Response(200, text='x' * 2_000_001))
        self.assertEqual(rows[0]['unknown_cause'], 'parser_mismatch')

    async def test_link_cap(self):
        rows = await self.org(lambda _: httpx.Response(200, text=''.join(f'<a href="https://partner{i}.com/">P</a>' for i in range(100))))
        self.assertEqual(len(rows), 30)

    async def test_http200_challenge_never_infers_links(self):
        for title in ('Just a moment...', 'Access Denied', 'Attention Required! | Cloudflare', 'Client Challenge'):
            rows = await self.org(lambda _: httpx.Response(200, text='<title>' + title + '</title><a href="https://cloudflare.com/">Help</a>'))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['unknown_cause'], 'bot_blocked')
            self.assertNotIn('public_links', rows[0]['public_metadata'])

    async def test_brand_passive_filter_provenance_and_no_candidate_requests(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, 'crt.sh')
            return httpx.Response(200, json=[{'entry_timestamp': '2026-01-01', 'name_value':
                '*.acme-shop.com\nacme.net\nwww.acme.com\nmacme.com\nsub.notacme.com\nacme.local\nacme.net'}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await research_brand('acme.com', client)
        self.assertEqual(len(calls), 1)
        self.assertEqual([r['public_metadata']['candidate_domain'] for r in rows], ['acme-shop.com', 'acme.net'])
        self.assertTrue(all(not r['public_metadata']['candidate_visited'] for r in rows))
        self.assertTrue(all(r['public_metadata']['assessment'] == 'unverified_candidate' for r in rows))
        self.assertEqual(rows[0]['public_metadata']['certificate_timestamp'], '2026-01-01T00:00:00+00:00')

    async def test_safe_www_redirects_pinned_and_provenance(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(301, headers={'location': 'https://www.acme.com/home'})
            self.assertEqual(request.headers['host'], 'www.acme.com')
            self.assertEqual(request.url.path, '/home')
            return httpx.Response(200, headers={'content-type': 'text/html'}, text='<a href="https://partner.com/">Partner</a>')
        rows = await self.org(handler)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rows[0]['public_metadata']['source_url'], 'https://www.acme.com/home')

    async def test_foreign_downgrade_and_loop_redirects_rejected(self):
        for target in ('https://other.com/', 'http://www.acme.com/', 'https://www.acme.com:80/', 'https://acme.com/'):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(302, headers={'location': target})
            rows = await self.org(handler)
            self.assertEqual(len(calls), 1)
            self.assertEqual(rows[0]['unknown_cause'], 'redirect_changed')

    async def test_redirect_hop_dns_rechecked_and_maximum_two_hops(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={'location': 'https://www.acme.com/' + str(len(calls))})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch('osint.organization._public_addresses', new=AsyncMock(side_effect=['8.8.8.8', ''])) as resolver:
                rows = await research_organization('acme.com', client)
                self.assertEqual(resolver.await_count, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]['unknown_cause'], 'unsafe_target')
        calls.clear()
        rows = await self.org(handler)
        self.assertEqual(len(calls), 3)
        self.assertEqual(rows[0]['unknown_cause'], 'redirect_changed')

    async def test_brand_bad_empty_blocked_cap_and_generic(self):
        for payload, status in (({}, 'unknown'), ([], 'not_found'), ([None, {'name_value': None}], 'unknown')):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
                self.assertEqual((await research_brand('acme.com', client))[0]['status'], status)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403))) as client:
            self.assertEqual((await research_brand('acme.com', client))[0]['unknown_cause'], 'blocked')
            self.assertEqual((await research_brand('ab.com', client))[0]['unknown_cause'], 'insufficient_input')
        payload = [{'name_value': '\n'.join('acme-' + str(i) + '.com' for i in range(100))}]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
            rows = await research_brand('acme.com', client)
        self.assertEqual(len(rows), 30)
        self.assertTrue(rows[0]['public_metadata']['truncated'])

    async def test_total_deadline(self):
        async def slow(_):
            await asyncio.sleep(.1)
            return httpx.Response(200, json=[])
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            with patch('osint.organization.TOTAL_TIMEOUT', .001):
                self.assertEqual((await research_brand('acme.com', client))[0]['unknown_cause'], 'timeout')

    async def test_stream_size_limit_closes_without_reading_remainder(self):
        class Stream(httpx.AsyncByteStream):
            closed = False
            chunks = 0

            async def __aiter__(self):
                for _ in range(20):
                    self.chunks += 1
                    yield b'x' * 1_000_001

            async def aclose(self):
                self.closed = True
        stream = Stream()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))) as client:
            rows = await research_brand('acme.com', client)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertTrue(stream.closed)
        self.assertEqual(stream.chunks, 2)


if __name__ == '__main__':
    unittest.main()
