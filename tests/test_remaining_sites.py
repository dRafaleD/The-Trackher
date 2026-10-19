"""Reduced observed metadata, not generic username echoes, confirms these sites."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import unittest

import httpx

from osint.username_checker import USERNAME_PLATFORMS, check_single_username
from osint.profile_evidence import evaluate_profile


FIXTURES = json.loads((Path(__file__).parent / 'fixtures/remaining_sites_20261017.json').read_text(encoding='utf-8'))


def fixture(name, username='sample', missing=False):
    if missing:
        return httpx.Response(404, text='<title>Profile unavailable</title>')
    body = FIXTURES[name]['body'].replace('sample', username)
    if name == 'Patreon':
        body = body.replace('/cw/' + username, '/' + username)
    return httpx.Response(200, text=body)


class RemainingSiteTests(unittest.TestCase):
    def evaluate(self, name, body=None, *, url=None, status=200):
        platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
        fixture = FIXTURES[name]
        response = httpx.Response(status, text=fixture['body'] if body is None else body,
                                  request=httpx.Request('GET', url or fixture['url']))
        return evaluate_profile('sample', platform, response)

    def test_observed_custom_display_names_do_not_require_handle_in_text(self):
        for name in FIXTURES:
            with self.subTest(site=name):
                self.assertEqual(self.evaluate(name)[0], 'found')

    def test_other_profile_echo_and_hidden_content_cannot_confirm(self):
        for name, fixture in FIXTURES.items():
            body = fixture['body']
            for invalid in (body.replace('sample', 'other'), '<h1>sample</h1>',
                            '<script>' + body + '</script>', '<!--' + body + '-->',
                            '<template>' + body + '</template>', '<noscript>' + body + '</noscript>',
                            '<footer>' + body + '</footer>', '<article>' + body + '</article>'):
                with self.subTest(site=name, body=invalid[:80]):
                    self.assertEqual(self.evaluate(name, invalid)[0], 'unknown')

    def test_missing_required_identity_field_cannot_confirm(self):
        from osint.profile_evidence import ProfileDocument
        for name, fixture in FIXTURES.items():
            platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
            rules = platform['profile_evidence']
            for rule in rules:
                for line in fixture['body'].splitlines():
                    doc = ProfileDocument()
                    doc.feed(line)
                    if doc.matches(rule, 'sample'):
                        with self.subTest(site=name, removed=line):
                            self.assertEqual(self.evaluate(name, fixture['body'].replace(line, ''))[0], 'unknown')

    def test_challenges_rate_limits_and_foreign_redirects_remain_unknown(self):
        for name, fixture in FIXTURES.items():
            for status in (401, 403, 429, 500):
                self.assertEqual(self.evaluate(name, status=status)[0], 'unknown')
            self.assertEqual(self.evaluate(name, '<title>Just a moment</title>' + fixture['body'], status=404)[0], 'unknown')
            for url in ('https://foreign.example/sample', 'https://foreign.example:443/sample',
                        fixture['url'] + '/login'):
                self.assertEqual(self.evaluate(name, url=url)[0], 'unknown')

    def test_direct_404_is_missing_but_giphy_search_redirect_is_not(self):
        for name in FIXTURES:
            self.assertEqual(self.evaluate(name, '<title>Profile unavailable</title>', status=404)[0], 'not_found')
        self.assertEqual(self.evaluate('Giphy', url='https://giphy.com/explore/sample')[0], 'unknown')

    def test_patreon_current_route_must_agree_with_canonical_and_og(self):
        original = FIXTURES['Patreon']['body']
        for prefix in ('', '/c', '/cw'):
            body = original.replace('/cw/sample', prefix + '/sample')
            self.assertEqual(self.evaluate('Patreon', body, url='https://www.patreon.com' + prefix + '/sample')[0], 'found')
        self.assertEqual(self.evaluate('Patreon', original.replace('/cw/sample', '/c/sample'))[0], 'unknown')
        self.assertEqual(self.evaluate('Patreon', url='https://www.patreon.com/cw/other')[0], 'unknown')

    def test_substack_host_template_accepts_only_requested_publication(self):
        body = FIXTURES['Substack']['body']
        self.assertEqual(self.evaluate('Substack', body, url='https://sample.substack.com/')[0], 'found')
        for host in ('other.substack.com', 'sample.substack.com.foreign.example', 'sample-substack.com'):
            self.assertEqual(self.evaluate('Substack', body, url='https://' + host + '/')[0], 'unknown')

    def test_kaggle_competition_metadata_keeps_exact_profile_identity(self):
        body = FIXTURES['Kaggle']['body']
        self.assertEqual(self.evaluate('Kaggle', body.replace('/sample/competitions', '/sample'))[0], 'found')
        self.assertEqual(self.evaluate('Kaggle', body.replace('/sample/competitions', '/other/competitions'))[0], 'unknown')

    def test_trakt_generic_application_shell_is_not_an_account(self):
        platform = next(p for p in USERNAME_PLATFORMS if p['name'] == 'Trakt')
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, text='<title>Trakt Web: Profile</title><h1>Trakt</h1>'))) as client:
                return await check_single_username('trakt', platform, client)
        self.assertEqual(asyncio.run(run())['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
