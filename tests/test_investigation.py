"""Public evidence, one-hop budgets, correlation, and authoritative domain data."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from osint.discovery import linked_candidates, discover_linked_profiles
from osint.domain_research import normalize_domain, research_domain
from osint.evidence import enrich_profile, finalize_username, email_evidence_view
from utils.correlation import build_identity_correlation, _extract_avatar_hash
from utils.public_data import public_url
from utils.reporter import export_to_html, export_to_json


class PublicEvidenceTests(unittest.TestCase):
    def test_metadata_provenance_and_only_explicit_public_links(self):
        body = '''<meta property="og:title" content="Public display">
        <meta property="og:description" content="Public bio">
        <meta property="og:image" content="https://cdn.example.com/avatar.jpg">
        <h1 class="name">Public Display</h1>
        <a rel="me" href="https://github.com/example">Account</a>
        <a href="https://instagram.com/advertiser">Ordinary ad</a>
        <footer><a rel="me" href="https://github.com/siteowner">Footer</a></footer>
        <div class="comments"><a rel="me" href="https://github.com/commenter">Comment</a></div>
        <a rel="me" href="http://127.0.0.1/private">Local</a>
        <script><a rel="me" href="https://github.com/fake">Fake</a></script>'''
        response = httpx.Response(200, text=body, request=httpx.Request('GET', 'https://profile.example.com/person'))
        result = enrich_profile({'found': True, 'status': 'found', 'url': str(response.url)}, 'person', {'check': 'structured_profile'}, response)
        metadata = result['public_metadata']
        self.assertEqual(metadata['public_links'], ['https://github.com/example'])
        self.assertEqual(metadata['bio'], 'Public bio')
        self.assertEqual(metadata['display_name'], 'Public Display')
        card = finalize_username(result, 'person', {'check': 'structured_profile'})['evidence_card']
        self.assertEqual(card['http_status'], 200)
        self.assertTrue(card['checked_at'])
        self.assertEqual(next(f for f in card['fields'] if f['field'] == 'bio')['source'], 'meta:og:description')

    def test_negative_or_blocked_results_do_not_gain_profile_metadata(self):
        response = httpx.Response(403, text='<meta property="og:description" content="fake">', request=httpx.Request('GET', 'https://example.com/person'))
        result = enrich_profile({'found': False, 'status': 'unknown'}, 'person', {}, response)
        self.assertNotIn('public_metadata', result)

    def test_email_candidates_and_manual_results_are_not_promoted(self):
        accounts = [{'service': 'GitHub', 'status': 'POSSIBLE', 'public_metadata': {'public_email': 'sample@example.com', 'commit_url': 'https://github.com/org/repo/commit/123'}}, {'service': 'Manual', 'status': 'MANUAL'}]
        view = email_evidence_view(accounts, [], {'domain': 'example.com', 'status': 'MX_FOUND'})
        self.assertEqual(len(view), 3)
        self.assertEqual(accounts[0]['status'], 'POSSIBLE')
        self.assertEqual(accounts[0]['evidence_card']['identity_claim'], 'candidate_only')
        self.assertEqual(accounts[1]['status'], 'MANUAL')

    def test_unsafe_urls_cannot_become_discovery_candidates(self):
        for value in ('file:///tmp/a', 'http://localhost/x', 'http://10.0.0.1/x', 'http://[::1]/x', 'https://a:b@example.com', 'https://example.com:8443/a', 'https://[bad', 'https://example.com/\nheader'):
            self.assertEqual(public_url(value), '')

    def test_sha256_avatar_evidence_is_preserved_without_md5_truncation(self):
        digest = 'a' * 64
        self.assertEqual(_extract_avatar_hash({'avatar_hash': digest}), digest)
        self.assertEqual(_extract_avatar_hash({'avatar_url': 'https://cdn.example.com/' + digest + '.png'}), digest)
        self.assertEqual(_extract_avatar_hash({'avatar_hash': 'a' * 32}), 'a' * 32)
        self.assertNotEqual(_extract_avatar_hash({'avatar_hash': digest}), _extract_avatar_hash({'avatar_hash': 'a' * 32}))
        self.assertEqual(_extract_avatar_hash({'avatar_hash': 'a' * 32, 'hash_algorithm': 'sha256'}), '')

    def test_shared_social_site_is_not_a_shared_personal_website_signal(self):
        rows = [{'platform': name, 'status': 'found', 'found': True, 'reliability': 'verified', 'url': f'https://{name}.example.com/person',
                 'public_metadata': {'username': 'person', 'website': 'https://github.com'}} for name in ('one', 'two')]
        self.assertFalse(build_identity_correlation({'osint_username': {'target': 'person', 'results': rows}})['available'])

    def test_reciprocal_declared_links_explain_the_correlation(self):
        results = [
            {'platform': 'A', 'url': 'https://a.example.com/alice', 'found': True, 'status': 'found', 'reliability': 'verified', 'public_metadata': {'public_links': ['https://b.example.com/bob']}},
            {'platform': 'B', 'url': 'https://b.example.com/bob', 'found': True, 'status': 'found', 'reliability': 'verified', 'public_metadata': {'public_links': ['https://a.example.com/alice']}},
        ]
        correlation = build_identity_correlation({'osint_username': {'results': results}})
        self.assertTrue(correlation['available'])
        self.assertIn('reciprocal_profile_link', {e['signal'] for e in correlation['items'][0]['evidence']})
        self.assertIn('does not prove', correlation['disclaimer'])

    def test_html_and_json_exports_preserve_cards_and_escape_untrusted_metadata(self):
        result = finalize_username({'platform': 'Example', 'url': 'https://example.com/a', 'found': True, 'status': 'found', 'public_metadata': {'bio': '<script>alert(1)</script>'}}, 'sample', {'check': 'json'})
        payload = {'osint_username': {'target': 'sample', 'results': [result]}, 'domain_research': {'domain': 'example.com', 'dns': {}, 'rdap': {'status': 'UNKNOWN'}}}
        with tempfile.TemporaryDirectory() as directory:
            html, output = Path(directory) / 'report.html', Path(directory) / 'report.json'
            export_to_html(payload, str(html)); export_to_json(payload, str(output))
            self.assertIn('Evidence cards', html.read_text(encoding='utf-8'))
            self.assertNotIn('<script>alert(1)</script>', html.read_text(encoding='utf-8'))
            self.assertIn('evidence_card', json.loads(output.read_text(encoding='utf-8'))['osint_username']['results'][0])


class LinkedDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def seed(self, links):
        return {'platform': 'Source', 'queried_username': 'alice', 'found': True, 'reliability': 'verified', 'url': 'https://source.example.com/alice', 'public_metadata': {'public_links': links}}

    async def test_discovery_is_one_hop_deduplicated_and_catalog_only(self):
        catalog = [{'name': 'Target', 'url': 'https://target.example.com/{}', 'check': 'structured_profile'}]
        seeds = [self.seed(['https://target.example.com/bob', 'https://target.example.com/bob/', 'https://target.example.com.evil.org/bob', 'http://127.0.0.1/private'])]
        calls = []
        async def detector(username, platform, client):
            calls.append(username)
            return {'platform': platform['name'], 'found': True, 'status': 'found', 'public_metadata': {'public_links': ['https://target.example.com/charlie']}}
        with patch('osint.username_checker.check_single_username', detector):
            results = await discover_linked_profiles(seeds, catalog, object())
        self.assertEqual(calls, ['bob'])
        self.assertEqual(results[0]['discovered_from']['depth'], 1)
        self.assertFalse(results[0]['discovered_from']['ownership_verified'])

    async def test_limit_and_unverified_seed_guards(self):
        catalog = [{'name': 'Target', 'url': 'https://target.example.com/{}', 'strict_api': True}]
        source = self.seed([f'https://target.example.com/person{i}' for i in range(20)])
        self.assertEqual(len(linked_candidates([source], catalog, 100)), 10)
        self.assertEqual(linked_candidates([source], catalog, 0), [])
        source['reliability'] = 'unreliable'
        self.assertEqual(linked_candidates([source], catalog), [])

    async def test_stalled_link_checks_are_cancelled_and_reported_as_unknown(self):
        from osint import discovery
        catalog = [{'name': 'Target', 'url': 'https://target.example.com/{}', 'strict_api': True}]
        source = self.seed([f'https://target.example.com/person{i}' for i in range(4)])
        active, maximum = 0, 0
        async def stalled(*args):
            nonlocal active, maximum
            active += 1; maximum = max(maximum, active)
            try:await asyncio.sleep(10)
            finally:active -= 1
        with patch('osint.username_checker.check_single_username', stalled), patch.object(discovery, 'DISCOVERY_REQUEST_TIMEOUT_SECONDS', .02), patch.object(discovery, 'DISCOVERY_TOTAL_TIMEOUT_SECONDS', .03):
            results = await asyncio.wait_for(discover_linked_profiles([source], catalog, object()), 1)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r['status'] == 'unknown' and r['unknown_cause'] == 'timeout' for r in results))
        self.assertEqual(active, 0)
        self.assertLessEqual(maximum, 2)


class DomainResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_and_authoritative_rdap_identity(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            if request.url.host == 'dns.google':
                code = {'A': 1, 'AAAA': 28, 'MX': 15, 'NS': 2}[request.url.params['type']]
                return httpx.Response(200, json={'Status': 0, 'Answer': [{'type': code, 'data': 'public record'}]})
            if request.url.host == 'data.iana.org':
                return httpx.Response(200, json={'services': [[['com'], ['https://rdap.example.com/']]]})
            return httpx.Response(200, json={'objectClassName': 'domain', 'ldhName': 'EXAMPLE.COM', 'events': [{'eventAction': 'registration', 'eventDate': '2000-01-01T00:00:00Z'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain('example.com', client)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['rdap']['status'], 'FOUND')
        self.assertEqual(len(calls), 6)
        self.assertIn('https://rdap.example.com/domain/example.com', calls)

    async def test_wrong_domain_and_redirect_do_not_become_found(self):
        for rdap_response in (httpx.Response(200, json={'objectClassName': 'domain', 'ldhName': 'wrong.com'}), httpx.Response(302, headers={'Location': 'http://127.0.0.1/'})):
            def handler(request):
                if request.url.host == 'dns.google':return httpx.Response(200, json={'Status': 3})
                if request.url.host == 'data.iana.org':return httpx.Response(200, json={'services': [[['com'], ['https://rdap.example.com/']]]})
                return rdap_response
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                result = await research_domain('example.com', client)
            self.assertEqual(result['rdap']['status'], 'UNKNOWN')

    async def test_private_bootstrap_endpoints_never_requested(self):
        calls = []
        def handler(request):
            calls.append(request.url.host)
            if request.url.host == 'dns.google':return httpx.Response(200, json={'Status': 0})
            return httpx.Response(200, json={'services': [[['com'], ['https://127.0.0.1/']]]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await research_domain('example.com', client)
        self.assertEqual(result['rdap']['status'], 'UNKNOWN')
        self.assertNotIn('127.0.0.1', calls)

    async def test_domain_validation_rejects_urls_ips_and_local_names(self):
        for value in ('https://example.com', '127.0.0.1', 'user@example.com', '-bad.com', 'a..com', 'host.local', 'host.invalid'):
            with self.assertRaises(ValueError):normalize_domain(value)
        self.assertEqual(normalize_domain('EXAMPLE.COM.'), 'example.com')


class HealthHistoryTests(unittest.TestCase):
    def test_changed_rule_configuration_invalidates_recent_cached_validation(self):
        from utils import platform_health as health
        original = next(item for item in health._platform_items() if item[0]['scope'] == 'username' and item[0]['platform'] == 'GitHub')
        changed = deepcopy(original)
        changed[1]['timeout_seconds'] = 11
        calls = []
        async def probe(*args):
            calls.append(True)
            return {'state': 'HEALTHY', 'detail': 'Reference pair passed', 'reference_pair_passed': True}
        entries = iter([[deepcopy(original)], [changed]])
        with tempfile.TemporaryDirectory() as directory, patch.object(health, '_platform_items', side_effect=lambda: next(entries)), patch.object(health, '_perform_live_probe', probe):
            first = health.run_platform_health_check(live=True, cache_dir=Path(directory))
            second = health.run_platform_health_check(live=True, cache_dir=Path(directory))
        self.assertEqual(len(calls), 2)
        self.assertEqual(second['cache_hits'], 0)
        self.assertNotEqual(first['items'][0]['rule_fingerprint'], second['items'][0]['rule_fingerprint'])

    def test_reference_validation_excludes_entries_without_control_profiles(self):
        from utils import platform_health as health
        with tempfile.TemporaryDirectory() as directory:
            report = health.run_platform_health_check(reference_only=True, cache_dir=Path(directory))
        self.assertTrue(report['items'])
        definitions = {p['name']: p for p in health.USERNAME_PLATFORMS}
        self.assertTrue(all(row['scope'] == 'username' and (definitions[row['platform']].get('reference_username') or definitions[row['platform']].get('validation_username')) for row in report['items']))

    def test_last_success_survives_later_live_failure(self):
        from utils import platform_health as health
        entry = next(item for item in health._platform_items() if item[0]['scope'] == 'username' and item[0]['platform'] == 'GitHub')
        outcomes = iter([{'state': 'HEALTHY', 'detail': 'Reference pair passed', 'reference_pair_passed': True}, {'state': 'DEGRADED', 'detail': 'Rate limited'}])
        async def probe(*args):return next(outcomes)
        with tempfile.TemporaryDirectory() as directory, patch.object(health, '_platform_items', side_effect=lambda: [deepcopy(entry)]), patch.object(health, '_perform_live_probe', probe):
            first = health.run_platform_health_check(live=True, ttl_seconds=-1, cache_dir=Path(directory))
            second = health.run_platform_health_check(live=True, ttl_seconds=-1, cache_dir=Path(directory))
        self.assertTrue(first['items'][0]['last_reference_success_at'])
        self.assertEqual(first['items'][0]['last_reference_success_at'], second['items'][0]['last_reference_success_at'])
        self.assertEqual(second['items'][0]['state'], 'DEGRADED')
