import asyncio
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import unittest

import httpx

from osint.embedded_profiles import missing_profile_state, evaluate_hackernews
from osint.profile_evidence import evaluate_profile
from osint.username_checker import USERNAME_PLATFORMS, check_single_username


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/unresolved_profiles_20261017.json').read_text(encoding='utf-8'))
SITES = {p['name']: p for p in USERNAME_PLATFORMS}


def html_fixture(site, data=None):
    scripts = (data or FIXTURE[site])['scripts']
    return ''.join('<script ' + ' '.join(f'{key}="{escape(value, quote=True)}"' for key, value in row['attrs'].items())
                   + '>' + json.dumps(row['payload'], ensure_ascii=False) + '</script>' for row in scripts)


def evaluate(site, body, username='sample', status=200, url=None):
    definition = SITES[site]
    response = httpx.Response(status, text=body, request=httpx.Request('GET', url or definition['url'].format(username)))
    return evaluate_profile(username, definition, response)


class EmbeddedMissingTests(unittest.TestCase):
    def test_captured_instagram_and_pinterest_specific_missing_state(self):
        for site in ('Instagram', 'Pinterest'):
            with self.subTest(site=site):
                self.assertEqual(evaluate(site, html_fixture(site))[0], 'not_found')

    def test_error_for_a_different_username_does_not_prove_absence(self):
        for site in ('Instagram', 'Pinterest'):
            self.assertEqual(evaluate(site, html_fixture(site), username='other')[0], 'unknown')

    def test_strings_shared_assets_comments_and_hidden_templates_do_not_count(self):
        for site in ('Instagram', 'Pinterest'):
            body = html_fixture(site)
            for wrapper in ('<!--{}-->', '<noscript>{}</noscript>', '<template>{}</template>', '<article>{}</article>'):
                with self.subTest(site=site, wrapper=wrapper):
                    self.assertEqual(evaluate(site, wrapper.format(body))[0], 'unknown')
            self.assertEqual(evaluate(site, body.replace('application/json', 'text/javascript'))[0], 'unknown')
            self.assertEqual(evaluate(site, '<script>"User not found.";"PolarisErrorRoute";</script>')[0], 'unknown')

    def test_duplicate_active_routes_or_resource_scripts_are_inconclusive(self):
        for site in ('Instagram', 'Pinterest'):
            body = html_fixture(site)
            self.assertEqual(evaluate(site, body + body)[0], 'unknown')

    def test_instagram_restrictions_and_login_reasons_are_not_absence(self):
        for property_name, changed in [('restricted_age', 18), ('failure_reason', 'login_required'),
                                       ('page_type', 'POST'), ('show_lox_redesigned_404_page', False),
                                       ('show_lox_redesigned_404_page', 1)]:
            data = deepcopy(FIXTURE['Instagram'])
            route = data['scripts'][0]['payload']['initialRouteInfo']['route']
            for view in ('rootView', 'hostableView'):
                route[view]['props'][property_name] = changed
            with self.subTest(field=property_name, value=changed):
                self.assertEqual(evaluate('Instagram', html_fixture('Instagram', data))[0], 'unknown')

    def test_instagram_requires_active_route_identity_not_generic_error_route(self):
        for key in ('url', 'canonicalRouteName', 'tracePolicy', 'polarisRouteConfig', 'rootView', 'hostableView'):
            data = deepcopy(FIXTURE['Instagram'])
            data['scripts'][0]['payload']['initialRouteInfo']['route'].pop(key)
            with self.subTest(key=key):
                self.assertEqual(evaluate('Instagram', html_fixture('Instagram', data))[0], 'unknown')
        data = deepcopy(FIXTURE['Instagram'])
        data['scripts'][0]['payload'] = {'prefetchedRoute': data['scripts'][0]['payload']['initialRouteInfo']['route']}
        self.assertEqual(evaluate('Instagram', html_fixture('Instagram', data))[0], 'unknown')

    def test_pinterest_requires_bound_request_context_and_error_type(self):
        for field, value in [('current_url', 'https://www.pinterest.com/other/'), ('path', '/other/'), ('is_authenticated', True)]:
            data = deepcopy(FIXTURE['Pinterest'])
            data['scripts'][0]['payload']['context'][field] = value
            self.assertEqual(evaluate('Pinterest', html_fixture('Pinterest', data))[0], 'unknown')
        for field, value in [('httpStatus', 403), ('httpStatus', 404.0), ('message', 'User not found.')]:
            data = deepcopy(FIXTURE['Pinterest'])
            resource = data['scripts'][1]['payload']['initialReduxState']['resources']['UserResource']
            next(iter(resource.values()))['error'][field] = value
            self.assertEqual(evaluate('Pinterest', html_fixture('Pinterest', data))[0], 'unknown')

    def test_pinterest_success_or_conflicting_resource_records_do_not_prove_absence(self):
        data = deepcopy(FIXTURE['Pinterest'])
        resource = data['scripts'][1]['payload']['initialReduxState']['resources']['UserResource']
        row = next(iter(resource.values()))
        row['data'] = {'username': 'sample'}
        self.assertEqual(evaluate('Pinterest', html_fixture('Pinterest', data))[0], 'unknown')
        row['data'] = None
        resource[json.dumps([['username', 'sample'], ['field_set_key', 'unauth_profile'], ['extra', True]])] = {'data': {'username': 'sample'}}
        self.assertEqual(evaluate('Pinterest', html_fixture('Pinterest', data))[0], 'unknown')

    def test_challenges_redirects_and_http_errors_stay_unknown(self):
        for site in ('Instagram', 'Pinterest'):
            body = html_fixture(site)
            for status in (401, 403, 429, 500):
                self.assertEqual(evaluate(site, body, status=status)[0], 'unknown')
            self.assertEqual(evaluate(site, '<title>Client Challenge</title>' + body)[0], 'unknown')
            self.assertEqual(evaluate(site, body, url='https://example.org/sample/')[0], 'unknown')

    def test_conflicting_positive_and_negative_evidence_stays_unknown(self):
        from test_site_profiles_20261016 import FIXTURES
        for site in ('Instagram', 'Pinterest'):
            body = FIXTURES[site]['positive_html'] + html_fixture(site)
            self.assertEqual(evaluate(site, body)[0], 'unknown')

    def test_malformed_and_oversized_script_state_is_bounded(self):
        for site in ('Instagram', 'Pinterest'):
            body = html_fixture(site)
            self.assertEqual(evaluate(site, body.replace('"initial', 'INVALID"initial'))[0], 'unknown')
            self.assertEqual(evaluate(site, body + 'x' * 2_000_000)[0], 'unknown')
        scripts = '<script type="application/json" data-sjs>{}</script>' * 65
        self.assertIsNone(missing_profile_state(scripts, 'sample', 'instagram_state', 'https://www.instagram.com/sample/'))


class HackerNewsFallbackTests(unittest.TestCase):
    def run_check(self, api_body='null', public_body=None, api_status=200):
        requests = []
        async def run():
            def handler(request):
                requests.append(str(request.url))
                if request.url.host == 'hacker-news.firebaseio.com':
                    return httpx.Response(api_status, text=api_body, headers={'content-type': 'application/json'})
                return httpx.Response(200, text=public_body if public_body is not None else FIXTURE['HackerNews']['negative_html'])
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username('sample', SITES['HackerNews'], client)
        return asyncio.run(run()), requests

    def test_api_null_needs_independent_public_missing_evidence(self):
        result, requests = self.run_check()
        self.assertEqual(result['status'], 'not_found')
        self.assertEqual(len(requests), 2)
        self.assertEqual(result['detector_used'], 'hackernews_profile')
        self.assertEqual(result['evidence'][0]['status'], 'unknown')

    def test_api_null_can_still_find_a_user_without_api_activity(self):
        result, _ = self.run_check(public_body=FIXTURE['HackerNews']['positive_html'])
        self.assertEqual(result['status'], 'found')

    def test_null_api_and_login_or_generic_html_remain_unknown(self):
        for body in ('', '<title>Log in</title>', '<script>No such user.</script>', '<h1>sample</h1>'):
            result, _ = self.run_check(public_body=body)
            self.assertEqual(result['status'], 'unknown')

    def test_case_sensitive_api_identity_and_single_request_success(self):
        result, requests = self.run_check(api_body='{"id":"sample"}')
        self.assertEqual(result['status'], 'found')
        self.assertEqual(len(requests), 1)
        result, _ = self.run_check(api_body='{"id":"Sample"}', public_body=FIXTURE['HackerNews']['positive_html'].replace('sample', 'Sample'))
        self.assertEqual(result['status'], 'unknown')

    def test_rate_limit_does_not_trigger_additional_requests(self):
        result, requests = self.run_check(api_status=429)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['unknown_cause'], 'rate_limited')
        self.assertEqual(len(requests), 1)

    def test_authentication_rejection_does_not_trigger_fallback(self):
        for status in (401, 403):
            result, requests = self.run_check(api_status=status)
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(len(requests), 1)

    def test_html_requires_all_identity_fields_and_rejects_redirects(self):
        body = FIXTURE['HackerNews']['positive_html']
        for changed in (body.replace('rel="canonical"', 'rel="other"'), body.replace('Profile: sample', 'Profile: other'), body.replace('class="hnuser"', 'class="other"')):
            response = httpx.Response(200, text=changed, request=httpx.Request('GET', 'https://news.ycombinator.com/user?id=sample'))
            self.assertEqual(evaluate_hackernews('sample', response)[0], 'unknown')
        for url in ('https://news.ycombinator.com/user?id=Sample', 'https://news.ycombinator.com:444/user?id=sample', 'https://example.org/user?id=sample'):
            response = httpx.Response(200, text='No such user.', request=httpx.Request('GET', url))
            self.assertEqual(evaluate_hackernews('sample', response)[0], 'unknown')


if __name__ == '__main__':
    unittest.main()
