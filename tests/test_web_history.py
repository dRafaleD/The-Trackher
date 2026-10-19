import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from osint.web_history import research_history, research_mentions, compare_archived_pages, MAX_RESPONSE_BYTES


HEADER = ['timestamp', 'original', 'mimetype', 'statuscode', 'digest']


def capture(url='https://example.com/about', stamp='20200102030405'):
    return [stamp, url, 'text/html', '200', 'digest']


def rss(items=''):
    return '<rss version="2.0"><channel><title>News</title>' + items + '</channel></rss>'


def item(title='Example story', url='https://news.example.com/a', date='Wed, 01 Jan 2020 12:00:00 GMT'):
    return ('<item><title>' + title + '</title><link>' + url + '</link><pubDate>' + date +
            '</pubDate><source url="https://news.example.com">Example News</source></item>')


class WebResearchTests(unittest.IsolatedAsyncioTestCase):
    async def run_request(self, function, query, payload, status=200):
        requests = []
        def handler(request):
            requests.append(request)
            if isinstance(payload, (list, dict)):
                return httpx.Response(status, json=payload)
            return httpx.Response(status, content=payload)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await function(query, client)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(rows), 1)
        return rows[0], requests[0]

    async def test_history_contract_and_only_index_request(self):
        row, request = await self.run_request(research_history, 'EXAMPLE.com', [HEADER, capture()])
        self.assertEqual(row['status'], 'found')
        self.assertEqual(row['queried_username'], 'example.com')
        self.assertEqual(row['evidence_type'], 'archive_index')
        record = row['public_metadata']['records'][0]
        self.assertEqual(record['timestamp'], '2020-01-02T03:04:05+00:00')
        self.assertEqual(record['archive_url'], 'https://web.archive.org/web/20200102030405/https://example.com/about')
        self.assertEqual(request.url.host, 'web.archive.org')
        self.assertEqual(request.url.params['limit'], '30')

    async def test_history_strict_target_and_timestamp(self):
        rows = [capture('https://example.com.attacker.org'), capture('https://notexample.com'),
                capture('https://example.com@attacker.org'), capture(stamp='20200230000000'),
                capture(stamp='29990101000000'), capture('https://example.com:444/'), capture('javascript:bad')]
        row, _ = await self.run_request(research_history, 'example.com', [HEADER] + rows)
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['unknown_cause'], 'parser_mismatch')
        self.assertEqual(row['public_metadata']['rejected_records'], len(rows))

    async def test_history_subdomain_and_duplicate(self):
        row, _ = await self.run_request(research_history, 'example.com',
            [HEADER, capture(), capture(), capture('https://blog.example.com/')])
        self.assertEqual(len(row['public_metadata']['records']), 2)

    async def test_history_empty_is_not_found(self):
        for data in ([], [HEADER]):
            row, _ = await self.run_request(research_history, 'example.com', data)
            self.assertEqual(row['status'], 'not_found')

    async def test_history_malformed_is_unknown(self):
        for data in ({}, [['original', 'timestamp']], b'<html>Challenge</html>', b'null'):
            row, _ = await self.run_request(research_history, 'example.com', data)
            self.assertEqual(row['status'], 'unknown')

    async def test_record_bound(self):
        row, _ = await self.run_request(research_history, 'example.com',
            [HEADER] + [capture('https://example.com/' + str(i)) for i in range(50)])
        self.assertEqual(len(row['public_metadata']['records']), 30)
        self.assertTrue(row['public_metadata']['limit_reached'])

    async def test_provider_failures_and_redirects(self):
        for function, query in ((research_history, 'example.com'), (research_mentions, 'Example')):
            for status, cause in ((429, 'rate_limited'), (403, 'blocked'), (401, 'blocked'),
                                  (302, 'redirect_changed'), (500, 'provider_error')):
                row, _ = await self.run_request(function, query, b'', status)
                self.assertEqual(row['status'], 'unknown')
                self.assertEqual(row['unknown_cause'], cause)

    async def test_mentions_source_and_unverified_relevance(self):
        row, request = await self.run_request(research_mentions, 'Example Brand', rss(item()))
        self.assertEqual(request.url.host, 'news.google.com')
        self.assertEqual(request.url.params['q'], 'Example Brand')
        self.assertEqual(row['status'], 'found')
        record = row['public_metadata']['records'][0]
        self.assertEqual(record['relevance'], 'unverified')
        self.assertEqual(record['source'], 'Example News')
        self.assertEqual(record['published'], '2020-01-01T12:00:00+00:00')

    async def test_mentions_group_normalized_links_and_titles(self):
        payload = rss(item('Same story', 'https://news.example.com/a?utm_source=x') +
                      item('Different title', 'https://news.example.com/a') +
                      item('SAME STORY!', 'https://other.example.com/report'))
        row, _ = await self.run_request(research_mentions, 'Example', payload)
        records = row['public_metadata']['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['duplicate_count'], 2)
        self.assertEqual(len(records[0]['related_urls']), 2)
        json.dumps(row)

    async def test_mentions_empty_and_invalid(self):
        row, _ = await self.run_request(research_mentions, 'Example', rss())
        self.assertEqual(row['status'], 'not_found')
        for payload in ('<html/>', '<rss><channel/></rss>', '<rss>', rss(item(url='http://localhost/a')),
                        '<!DOCTYPE rss [<!ENTITY x "bad">]>' + rss(),
                        ('<!DOCTYPE rss [<!ENTITY x "bad">]>' + rss()).encode('utf-16'),
                        rss(item(title='!!!'))):
            row, _ = await self.run_request(research_mentions, 'Example', payload)
            self.assertEqual(row['status'], 'unknown')

    async def test_mentions_missing_date_keeps_candidate(self):
        row, _ = await self.run_request(research_mentions, 'Example', rss(item(date='bad')))
        self.assertEqual(row['status'], 'found')
        self.assertEqual(row['public_metadata']['records'][0]['published'], '')

    async def test_mentions_record_bound(self):
        payload = rss(''.join(item('Story ' + str(i), 'https://news.example.com/' + str(i)) for i in range(50)))
        row, _ = await self.run_request(research_mentions, 'Example', payload)
        self.assertEqual(len(row['public_metadata']['records']), 30)

    async def test_size_cap(self):
        row, _ = await self.run_request(research_mentions, 'Example', b'x' * (MAX_RESPONSE_BYTES + 1))
        self.assertEqual(row['unknown_cause'], 'response_too_large')

    async def test_input_rejected_before_request(self):
        for query in ('', 'a', 'x' * 161, 'Example\nBrand', None):
            with self.assertRaises(ValueError):
                await research_mentions(query)
        for domain in ('https://example.com', 'localhost', '127.0.0.1'):
            with self.assertRaises(ValueError):
                await research_history(domain)

    async def test_timeout_and_network(self):
        class Slow:
            async def get(self, *args, **kwargs):
                await asyncio.sleep(1)
        with patch('osint.web_history.DEADLINE_SECONDS', .001):
            row = (await research_mentions('Example', Slow()))[0]
        self.assertEqual(row['unknown_cause'], 'timeout')
        class Broken:
            async def get(self, *args, **kwargs):
                raise httpx.ConnectError('unavailable')
        row = (await research_history('example.com', Broken()))[0]
        self.assertEqual(row['unknown_cause'], 'network_error')

    async def test_archived_content_compare(self):
        requests = []
        def handler(request):
            requests.append(request)
            old = '20200102030405' in str(request.url)
            return httpx.Response(200, text=('<html><title>' + ('Old' if old else 'New') +
                '</title><body>Hello<script>not visible</script><a href="/' + ('before' if old else 'after') + '">Link</a></body></html>'))
        urls = ['https://web.archive.org/web/' + stamp + '/https://example.com/' for stamp in ('20200102030405', '20210102030405')]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            row = (await compare_archived_pages('example.com', urls, client))[0]
        self.assertEqual(row['status'], 'found')
        comparison = row['public_metadata']['comparison']
        self.assertTrue(comparison['content_changed'])
        self.assertTrue(comparison['title_changed'])
        self.assertEqual(comparison['added_links'], ['https://example.com/after'])
        self.assertEqual(comparison['removed_links'], ['https://example.com/before'])
        self.assertTrue(all(r.url.host == 'web.archive.org' and 'id_/' in r.url.path for r in requests))

    async def test_unavailable_archive_never_means_removed(self):
        def handler(request):
            if '20200102030405' in str(request.url):
                return httpx.Response(403)
            return httpx.Response(200, text='<html><title>New</title><body>Text</body></html>')
        urls = ['https://web.archive.org/web/' + stamp + '/https://example.com/' for stamp in ('20200102030405', '20210102030405')]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            row = (await compare_archived_pages('example.com', urls, client))[0]
        self.assertEqual(row['public_metadata']['comparison']['status'], 'unknown')
        self.assertNotIn('removed_links', row['public_metadata']['comparison'])
        self.assertEqual(len(row['public_metadata']['records']), 1)

    async def test_archive_selection_validation(self):
        for urls in ([], ['https://attacker.org/web/20200102030405/https://example.com/'],
                     ['https://web.archive.org/web/20200102030405/https://other.com/'],
                     ['https://web.archive.org/web/20200230030405/https://example.com/']):
            with self.assertRaises(ValueError):
                await compare_archived_pages('example.com', urls)

    async def test_hidden_content_and_self_closing_tags_do_not_create_changes(self):
        def handler(request):
            old = '20200102030405' in str(request.url)
            hidden = '<div hidden><a href="/fake-old">Old</a></div>' if old else '<div style="display:none"><a href="/fake-new">New</a></div>'
            return httpx.Response(200, text='<html><title>Same</title><body>Visible' + hidden +
                                  '<script/><a href="/real">Reference</a></body></html>')
        urls = ['https://web.archive.org/web/' + stamp + '/https://example.com/' for stamp in ('20200102030405', '20210102030405')]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            row = (await compare_archived_pages('example.com', urls, client))[0]
        self.assertEqual(row['public_metadata']['records'][0]['public_links'], ['https://example.com/real'])
        self.assertFalse(row['public_metadata']['comparison']['content_changed'])
        self.assertEqual(row['public_metadata']['comparison']['removed_links'], [])

    async def test_opt_in_keeps_index_if_snapshot_blocked(self):
        def handler(request):
            if request.url.path.startswith('/cdx'):
                return httpx.Response(200, json=[HEADER, capture()])
            return httpx.Response(429)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await research_history('example.com', client, inspect_pages=True)
        self.assertEqual(rows[0]['status'], 'found')
        self.assertEqual(rows[1]['status'], 'unknown')
        self.assertEqual(rows[1]['unknown_cause'], 'rate_limited')


if __name__ == '__main__':
    unittest.main()
