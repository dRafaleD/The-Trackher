"""Regression cases based on public API shapes inspected 2026-09-08.

These expectations deliberately do not build responses from catalog rules.
"""
import asyncio
import unittest
import httpx
from osint.username_checker import USERNAME_PLATFORMS, check_single_username, _check_json_response

PAYLOADS = {
    'GitHub': {'login': 'sample'},
    'Reddit': {'data': {'name': 'sample'}},
    'Dailymotion': {'username': 'sample'},
    'Mixcloud': {'username': 'sample'},
    'GitLab': [{'username': 'sample'}],
    'Gitea': {'login': 'sample'},
    'DockerHub': {'username': 'sample'},
    'Chess.com': {'username': 'sample'},
    'Lichess': {'username': 'sample'},
    'Dev.to': {'username': 'sample'},
    'WordPress': {'ID': 123, 'URL': 'https://sample.wordpress.com'},
    'AniList': {'data': {'User': {'name': 'sample'}}},
    'Wikipedia': {'query': {'users': [{'name': 'Sample', 'userid': 123}]}},
    'Arduino Forum': {'user': {'username': 'sample'}},
    'Codeforces': {'status': 'OK', 'result': [{'handle': 'sample'}]},
    'Speedrun.com': {'data': [{'names': {'international': 'sample'}}]},
    'Discogs': {'username': 'sample'},
    'Lobsters': {'username': 'sample'},
    'Kitsu': {'data': [{'id': '42', 'attributes': {'name': 'sample'}}]},
    'Bangumi': {'username': 'sample'},
    'Shikimori': {'nickname': 'sample'},
    'Trakt Forums': {'user': {'username': 'sample'}},
    'Codeberg': {'login': 'sample'},
    'Codewars': {'username': 'sample'},
    'Keybase': {'status': {'code': 0}, 'them': {'basics': {'username': 'sample'}}},
    'Open Collective': {'slug': 'sample'},
    'Playstrategy': {'username': 'sample'},
    'RubyGems': {'handle': 'sample'},
    'Ask Fedora': {'user': {'username': 'sample'}},
    'Caddy Community': {'user': {'username': 'sample'}},
    'Cfx.re Forum': {'user': {'username': 'sample'}},
    'Chaos.social': {'username': 'sample', 'acct': 'sample'},
    'Fosstodon': {'username': 'sample', 'acct': 'sample'},
    'Ionic Forum': {'user': {'username': 'sample'}},
    'Joplin Forum': {'user': {'username': 'sample'}},
    'Mamot': {'username': 'sample', 'acct': 'sample'},
    'n8n Community': {'user': {'username': 'sample'}},
    'Kayıp Rıhtım Forum': {'user': {'username': 'sample'}},
    'Discourse Meta': {'user': {'username': 'sample'}},
    'Python Discuss': {'user': {'username': 'sample'}},
}


class ApiHardeningTests(unittest.TestCase):
    def run_case(self, name, response, username='sample'):
        platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
        requests = []
        def handler(request):
            requests.append(request)
            return response
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username(username, platform, client)
        result = asyncio.run(run())
        self.assertEqual(len(requests), 1, 'Uncertain API must not trigger weak HTML evidence')
        return result

    def test_exactly_40_sites_have_pinned_regression_contracts(self):
        self.assertEqual({p['name'] for p in USERNAME_PLATFORMS if p.get('strict_api') and not p.get('review_batch')}, set(PAYLOADS))
        self.assertEqual(len(PAYLOADS), 40)

    def test_valid_profile_contracts(self):
        for name, payload in PAYLOADS.items():
            with self.subTest(site=name):
                self.assertEqual(self.run_case(name, httpx.Response(200, json=payload))['status'], 'found')

    def test_schema_changes_are_unknown_not_missing(self):
        for name in PAYLOADS:
            for payload in ({}, {'errors': ['maintenance']}, {'unrelated': 'sample'}, None):
                with self.subTest(site=name, payload=payload):
                    self.assertEqual(self.run_case(name, httpx.Response(200, json=payload))['status'], 'unknown')

    def test_blocked_limited_and_outage_responses_stay_unknown(self):
        for name in PAYLOADS:
            for status in (401, 403, 429, 500, 503):
                with self.subTest(site=name, status=status):
                    result = self.run_case(name, httpx.Response(status, json={'message': 'Not Found'}))
                    self.assertEqual(result['status'], 'unknown')

    def test_username_echo_in_html_cannot_verify_an_api_profile(self):
        for name in PAYLOADS:
            with self.subTest(site=name):
                self.assertEqual(self.run_case(name, httpx.Response(200, text='<h1>sample</h1>'))['status'], 'unknown')

    def test_codeforces_only_specific_400_means_missing(self):
        result = self.run_case('Codeforces', httpx.Response(400, json={'status': 'FAILED', 'comment': 'handles: User with handle sample not found'}))
        self.assertEqual(result['status'], 'not_found')
        result = self.run_case('Codeforces', httpx.Response(400, json={'status': 'FAILED', 'comment': 'Call limit exceeded'}))
        self.assertEqual(result['status'], 'unknown')

    def test_keybase_invalid_name_is_not_a_missing_profile(self):
        result = self.run_case('Keybase', httpx.Response(200, json={'status': {'code': 100, 'name': 'INPUT_ERROR'}}))
        self.assertEqual(result['status'], 'unknown')

    def test_keybase_missing_user_code_is_recognized(self):
        result = self.run_case('Keybase', httpx.Response(200, json={'status': {'code': 205, 'name': 'NOT_FOUND'}}))
        self.assertEqual(result['status'], 'not_found')

    def test_api_identity_does_not_coerce_numbers_or_remove_accents(self):
        for value, username in [(123, '123'), ('sámple', 'sample')]:
            result = self.run_case('GitHub', httpx.Response(200, json={'login': value}), username=username)
            self.assertEqual(result['status'], 'unknown')

    def test_mastodon_remote_namesake_is_not_local_account(self):
        for name in ('Chaos.social', 'Fosstodon', 'Mamot'):
            result = self.run_case(name, httpx.Response(200, json={'username': 'sample', 'acct': 'sample@elsewhere.test'}))
            self.assertEqual(result['status'], 'unknown')

    def test_wordpress_requires_real_id_and_matching_site(self):
        for identifier in (False, 0, '', [], {}):
            result = self.run_case('WordPress', httpx.Response(200, json={'ID': identifier, 'URL': 'https://sample.wordpress.com'}))
            self.assertEqual(result['status'], 'unknown')
        result = self.run_case('WordPress', httpx.Response(200, json={'ID': 42, 'URL': 'https://another.wordpress.com'}))
        self.assertEqual(result['status'], 'unknown')

    def test_wikipedia_echoed_missing_user_is_not_found(self):
        result = self.run_case('Wikipedia', httpx.Response(200, json={'query': {'users': [{'name': 'Sample', 'missing': ''}]}}))
        self.assertEqual(result['status'], 'not_found')

    def test_lists_reject_malformed_items(self):
        for name, payload in [('GitLab', [{}]), ('Kitsu', {'data': [{}]}), ('Speedrun.com', {'data': [{}]}), ('Codeforces', {'status': 'OK', 'result': [{}]})]:
            self.assertEqual(self.run_case(name, httpx.Response(200, json=payload))['status'], 'unknown')

    def test_foreign_host_and_challenge_cannot_mean_missing(self):
        for name in PAYLOADS:
            with self.subTest(site=name):
                r = httpx.Response(404, request=httpx.Request('GET', 'https://login.example.test/sample'))
                platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
                self.assertEqual(_check_json_response('sample', platform, r, {})['status'], 'unknown')
                r = httpx.Response(404, text='<html>Verify you are human</html>')
                self.assertEqual(self.run_case(name, r)['status'], 'unknown')
