"""Reflections, shells and weak API fallbacks must never confirm a profile."""
import asyncio
import unittest

import httpx

from osint.username_checker import USERNAME_PLATFORMS, check_single_username


def fixture(name, username='sample'):
    if name == 'Kongregate':
        body = f'''<title>{username}'s profile on Kongregate</title>
<link rel="canonical" href="https://www.kongregate.com/en/accounts/{username}">
<h1 class="text-3xl font-bold text-white mb-4">{username}</h1>'''
    else:
        body = f'''<title>{username} - Wattpad</title>
<link rel="canonical" href="https://www.wattpad.com/user/{username}">
<h1 class="profile-name h3" aria-label="{username}'s profile">{username}</h1>'''
    return httpx.Response(200, text=body)


class FalsePositiveGuardTests(unittest.TestCase):
    def test_evidence_policy_change_invalidates_previous_health_fingerprint(self):
        import hashlib
        import json
        from unittest.mock import patch
        from utils.public_data import configuration_fingerprint
        definition={'name':'Echo','url':'https://example.test/{}'}
        legacy=hashlib.sha256(json.dumps(definition,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()[:16]
        current=configuration_fingerprint(definition)
        self.assertNotEqual(current,legacy)
        with patch('utils.public_data.EVIDENCE_POLICY_REVISION','future-policy'):
            self.assertNotEqual(current,configuration_fingerprint(definition))

    def check(self, platform, body, status=200):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(status,text=body))) as client:
                return await check_single_username('nonexistent_q7z9',platform,client)
        return asyncio.run(run())

    def test_catalog_html_echoes_cannot_confirm_any_account(self):
        body='<title>nonexistent_q7z9</title><h1>nonexistent_q7z9</h1><p>Search results for nonexistent_q7z9</p>'
        for p in USERNAME_PLATFORMS:
            if p.get('check','html') not in ('html','404','content','profile_html','structured_profile'):continue
            with self.subTest(site=p['name']):
                result=self.check(p,body)
                self.assertNotEqual(result['status'],'found')
                self.assertFalse(result['found'])

    def test_legacy_raw_marker_and_title_opt_in_cannot_bypass_guard(self):
        for name in ('Facebook','VK','DonanımHaber','Pastebin','Bitchute'):
            p=next(p for p in USERNAME_PLATFORMS if p['name']==name)
            markers='\n'.join(p['raw_found_markers']).replace('{username}','nonexistent_q7z9')
            for body in (markers,'<script>'+markers+'</script>','<!--'+markers+'-->'):
                self.assertEqual(self.check(p,body)['status'],'unknown')
        p={'name':'Title echo','url':'https://example.test/{}','allow_title_username_match':True}
        self.assertEqual(self.check(p,'<title>nonexistent_q7z9</title><h1>nonexistent_q7z9</h1>')['status'],'unknown')

    def test_api_error_cannot_be_upgraded_by_reflected_public_page(self):
        p={'name':'API fallback','url':'https://example.test/{}','probe_url':'https://api.example.test/{}','check':'json','json_path':'username'}
        async def run():
            def handler(req):
                return httpx.Response(403) if req.url.host.startswith('api.') else httpx.Response(200,text='<h1>nonexistent_q7z9</h1>')
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username('nonexistent_q7z9',p,client)
        result=asyncio.run(run());self.assertEqual(result['status'],'unknown');self.assertTrue(result['fallback_used'])

    def test_structured_profiles_require_all_observed_fields(self):
        for name in ('Kongregate','Wattpad'):
            p=next(p for p in USERNAME_PLATFORMS if p['name']==name)
            body=fixture(name,'nonexistent_q7z9').text
            self.assertEqual(self.check(p,body)['status'],'found')
            for line in body.splitlines():
                self.assertEqual(self.check(p,body.replace(line,''))['status'],'unknown')
            self.assertEqual(self.check(p,body.replace('/nonexistent_q7z9','/other'))['status'],'unknown')
            self.assertEqual(self.check(p,'',404)['status'],'not_found')
