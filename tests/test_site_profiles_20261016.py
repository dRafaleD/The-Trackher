"""Independent reduced HTML controls from the remaining-site review."""
import asyncio
import json
from pathlib import Path
import re
import unittest

import httpx

from osint.profile_evidence import evaluate_profile
from osint.username_checker import USERNAME_PLATFORMS, check_single_username


FIXTURES = json.loads((Path(__file__).parent / 'fixtures/site_profiles_20261016.json').read_text(encoding='utf-8'))
PLATFORMS = {p['name']: p for p in USERNAME_PLATFORMS if p.get('review_batch') == '2026-10-16'}


def fixture(name, username='sample', missing=False):
    row = FIXTURES[name]
    return httpx.Response(row['negative_status'] if missing else 200,
                          text=row['negative_html'] if missing else row['positive_html'].replace('sample', username))


class RemainingProfileTests(unittest.TestCase):
    def run_case(self, name, response, username='sample'):
        async def run():
            def handler(request):
                if name == 'Osu!' and response.status_code == 200 and '/users/2' not in request.url.path:
                    return httpx.Response(302, headers={'Location': 'https://osu.ppy.sh/users/2'})
                return response
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username(username, PLATFORMS[name], client)
        return asyncio.run(run())

    def test_ten_captured_positive_and_negative_controls(self):
        self.assertEqual(set(PLATFORMS), set(FIXTURES))
        self.assertEqual(len(PLATFORMS), 10)
        for name in PLATFORMS:
            with self.subTest(site=name):
                self.assertEqual(self.run_case(name, fixture(name))['status'], 'found')
                self.assertEqual(self.run_case(name, fixture(name, missing=True))['status'], FIXTURES[name]['negative_result'])

    def test_username_echo_wrong_identity_and_hidden_html_are_unknown(self):
        for name, row in FIXTURES.items():
            for body in ('<title>sample</title><h1>sample</h1>', row['positive_html'].replace('sample', 'someone_else'), '<script>' + row['positive_html'] + '</script>', '<!--' + row['positive_html'] + '-->'):
                with self.subTest(site=name):
                    self.assertEqual(self.run_case(name, httpx.Response(200, text=body))['status'], 'unknown')

    def test_each_identity_element_is_required(self):
        for name, row in FIXTURES.items():
            body = row['positive_html']
            for match in re.finditer(r'<(?:meta|link)\b[^>]*>|<(title|h1|span|a)\b[^>]*>.*?</\1>', body, re.S):
                reduced = body[:match.start()] + body[match.end():]
                with self.subTest(site=name, removed=match.group()[:70]):
                    self.assertEqual(self.run_case(name, httpx.Response(200, text=reduced))['status'], 'unknown')

    def test_challenges_errors_and_limits_never_prove_absence(self):
        for name, row in FIXTURES.items():
            for status in (202, 401, 403, 406, 429, 500, 503):
                with self.subTest(site=name, status=status):
                    self.assertEqual(self.run_case(name, httpx.Response(status, text=row['positive_html']))['status'], 'unknown')
            self.assertEqual(self.run_case(name, httpx.Response(404, text='<title>Client Challenge</title>'))['status'], 'unknown')

    def test_foreign_hosts_and_other_paths_rejected_even_with_profile_html(self):
        for name, platform in PLATFORMS.items():
            for url in ('https://example.test/sample', 'https://' + platform['profile_allowed_hosts'][0] + '/login'):
                response = httpx.Response(200, text=FIXTURES[name]['positive_html'], request=httpx.Request('GET', url))
                self.assertEqual(evaluate_profile('sample', platform, response)[0], 'unknown')

    def test_osu_redirect_requires_matching_numeric_id_and_requested_name(self):
        platform = PLATFORMS['Osu!']
        body = FIXTURES['Osu!']['positive_html']
        for path in ('/users/3', '/users/2/edit', '/users/not-a-number', '/users/02', '/login'):
            response = httpx.Response(200, text=body, request=httpx.Request('GET', 'https://osu.ppy.sh' + path))
            self.assertEqual(evaluate_profile('sample', platform, response)[0], 'unknown')
        self.assertEqual(self.run_case('Osu!', httpx.Response(200, text=body.replace('sample', 'other')))['status'], 'unknown')

    def test_youtube_channel_id_must_be_valid_and_consistent(self):
        body = FIXTURES['YouTube']['positive_html']
        for old, new in (('https://www.youtube.com/channel/', 'https://example.test/channel/'), ('UCBR8-60-B28hp2BmDPdntcQ', 'UCbad'), ('rel="canonical"', 'rel="alternate"')):
            self.assertEqual(self.run_case('YouTube', httpx.Response(200, text=body.replace(old, new)))['status'], 'unknown')
        mismatched = body.replace('property="og:url" content="https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ"', 'property="og:url" content="https://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa"')
        self.assertNotEqual(mismatched, body)
        self.assertEqual(self.run_case('YouTube', httpx.Response(200, text=mismatched))['status'], 'unknown')

    def test_audiomack_soft404_requires_both_site_url_and_missing_heading(self):
        body = FIXTURES['Audiomack']['negative_html']
        for changed in (body.replace('NotFoundPage-title', 'other'), body.replace('https://audiomack.com/', 'https://example.test/')):
            self.assertEqual(self.run_case('Audiomack', httpx.Response(200, text=changed))['status'], 'unknown')

    def test_youtube_large_page_has_a_finite_site_specific_size_limit(self):
        body = FIXTURES['YouTube']['positive_html']
        self.assertEqual(self.run_case('YouTube', httpx.Response(200, text=body + '<script>' + 'x' * 2_100_000 + '</script>'))['status'], 'found')
        self.assertEqual(self.run_case('YouTube', httpx.Response(200, text=body + 'x' * 3_000_000))['status'], 'unknown')
        self.assertEqual(self.run_case('Spotify', httpx.Response(200, text=FIXTURES['Spotify']['positive_html'] + 'x' * 2_000_000))['status'], 'unknown')
