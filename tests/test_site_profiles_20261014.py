"""Reduced live HTML from the October 14 review, plus adversarial controls."""
import asyncio
import json
import re
from pathlib import Path
import unittest

import httpx

from osint.profile_evidence import evaluate_profile
from osint.username_checker import USERNAME_PLATFORMS, check_single_username


FIXTURES = json.loads((Path(__file__).parent / 'fixtures' / 'site_profiles_20261014.json').read_text(encoding='utf-8'))
PLATFORMS = {p['name']: p for p in USERNAME_PLATFORMS if p.get('review_batch') == '2026-10-14-30'}


def fixture(name, username='sample', missing=False):
    entry = FIXTURES[name]
    if missing:
        return httpx.Response(entry['negative_status'], text=entry['negative_html'])
    return httpx.Response(200, text=entry['positive_html'].replace('sample', username))


class OctoberSiteProfileTests(unittest.TestCase):
    def run_case(self, name, response, username='sample'):
        calls = []
        def handler(request):
            calls.append(request)
            return response
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username(username, PLATFORMS[name], client)
        result = asyncio.run(run())
        self.assertEqual(len(calls), 1)
        return result

    def test_thirty_sites_have_independent_captured_controls(self):
        self.assertEqual(set(PLATFORMS), set(FIXTURES))
        self.assertEqual(len(PLATFORMS), 30)
        for name in PLATFORMS:
            with self.subTest(site=name):
                self.assertEqual(self.run_case(name, fixture(name))['status'], 'found')
                self.assertEqual(self.run_case(name, fixture(name, missing=True))['status'], FIXTURES[name]['negative_result'])

    def test_generic_echo_wrong_identity_and_hidden_evidence_are_unknown(self):
        for name, entry in FIXTURES.items():
            for body in ('<title>sample</title><h1>sample</h1>',
                         entry['positive_html'].replace('sample', 'someone_else'),
                         '<script>' + entry['positive_html'] + '</script>',
                         '<!--' + entry['positive_html'] + '-->'):
                with self.subTest(site=name, body=body[:80]):
                    self.assertEqual(self.run_case(name, httpx.Response(200, text=body))['status'], 'unknown')

    def test_every_profile_evidence_element_is_required(self):
        for name, entry in FIXTURES.items():
            body = entry['positive_html']
            # Remove each complete element, including individual metadata fields.
            fragments = list(re.finditer(r'<(?:meta|link)\b[^>]*>|<(title|h1|h2|div|span|a)\b[^>]*>.*?</\1>', body, re.S))
            self.assertGreaterEqual(len(fragments), 2)
            for fragment in fragments:
                stripped = body[:fragment.start()] + body[fragment.end():]
                with self.subTest(site=name, removed=fragment.group()[:80]):
                    self.assertEqual(self.run_case(name, httpx.Response(200, text=stripped))['status'], 'unknown')

    def test_blocked_statuses_challenges_and_service_errors_remain_unknown(self):
        for name, entry in FIXTURES.items():
            for status in (202, 401, 403, 406, 429, 500, 503):
                with self.subTest(site=name, status=status):
                    self.assertEqual(self.run_case(name, httpx.Response(status, text=entry['positive_html']))['status'], 'unknown')
            for status in (200, 404, 410):
                result = self.run_case(name, httpx.Response(status, text='<title>Just a moment...</title>' + entry['positive_html']))
                self.assertEqual(result['status'], 'unknown')
                self.assertEqual(result['unknown_cause'], 'bot_blocked')

    def test_foreign_hosts_other_profiles_and_unsupported_schemes_are_unknown(self):
        for name, platform in PLATFORMS.items():
            body = FIXTURES[name]['positive_html']
            url = platform['url'].format('sample')
            from urllib.parse import urlsplit
            parsed = urlsplit(url)
            for target in (url.replace(parsed.netloc, 'example.test'),
                           url.replace('sample', 'someone_else'),
                           url.replace('https:', 'ftp:'),
                           url.replace(parsed.netloc, parsed.netloc + '.example.test')):
                response = httpx.Response(200, text=body, request=httpx.Request('GET', target))
                with self.subTest(site=name, target=target):
                    self.assertEqual(evaluate_profile('sample', platform, response)[0], 'unknown')

    def test_hashnode_soft404_requires_site_identity_and_exact_missing_title(self):
        for body in ('<title>User not found | Other Site</title>',
                     '<title>User not found | Hashnode</title>',
                     '<script>' + FIXTURES['Hashnode']['negative_html'] + '</script>'):
            self.assertEqual(self.run_case('Hashnode', httpx.Response(200, text=body))['status'], 'unknown')

    def test_geocaching_query_must_identify_requested_user(self):
        p = PLATFORMS['Geocaching']
        for query in ('u=other', '', 'u=sample&u=other'):
            response = httpx.Response(200, text=FIXTURES['Geocaching']['positive_html'], request=httpx.Request('GET', 'https://www.geocaching.com/p/default.aspx?' + query))
            self.assertEqual(evaluate_profile('sample', p, response)[0], 'unknown')

    def test_codechef_homepage_redirect_does_not_prove_absence(self):
        p = PLATFORMS['CodeChef']
        response = httpx.Response(200, text=FIXTURES['CodeChef']['negative_html'], request=httpx.Request('GET', 'https://www.codechef.com/'))
        self.assertEqual(evaluate_profile('sample', p, response)[0], 'unknown')

    def test_username_punctuation_is_literal(self):
        for name in ('Instructables', 'Disqus', 'MyAnimeList', 'Gradle'):
            self.assertEqual(self.run_case(name, fixture(name, 'sample.x'), 'sample.x')['status'], 'found')
            self.assertEqual(self.run_case(name, fixture(name, 'sampleax'), 'sample.x')['status'], 'unknown')
