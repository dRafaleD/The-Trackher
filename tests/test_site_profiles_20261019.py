"""Reduced observed public response shapes, with identity and redirect adversaries."""
import asyncio
from copy import deepcopy
import unittest

import httpx

from osint.username_checker import USERNAME_PLATFORMS, check_single_username


GENIUS = '''<html><head>
<link rel="canonical" href="https://genius.com/artists/{username}">
<meta property="og:url" content="https://genius.com/artists/{username}">
<meta property="og:site_name" content="Genius">
<title>Taylor Swift Lyrics, Songs, and Albums | Genius</title>
</head><body><h1 class="profile_identity-name_iq_and_role_icon u-hair_bottom_margin">Taylor Swift</h1></body></html>'''


def channel_payload(username='sample', missing=False):
    query = 'lbry://@' + username
    claim = '80d2590ad04e36fb1d077a9b9e3a8bba76defdf8'
    entry = {'name': '@' + username, 'normalized_name': '@' + username.casefold(),
             'claim_id': claim, 'value_type': 'channel', 'value': {'title': 'Public channel'},
             'permanent_url': f'lbry://@{username}#{claim}'}
    if missing:
        entry = {'error': {'name': 'NOT_FOUND', 'text': f'Could not find channel in "{query}".'}}
    return {'jsonrpc': '2.0', 'id': 1, 'result': {query: entry}}


def fixture(name, username='sample', missing=False):
    if name == 'Odysee':
        return httpx.Response(200, json=channel_payload(username, missing))
    return httpx.Response(404 if missing else 200, text='' if missing else GENIUS.format(username=username))


class CurrentSiteTests(unittest.TestCase):
    def run_site(self, name, response, username='sample'):
        platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: response)) as client:
                return await check_single_username(username, platform, client)
        return asyncio.run(run())

    def test_observed_pairs(self):
        for name in ('Genius Artists', 'Odysee'):
            for missing in (True, False):
                self.assertEqual(self.run_site(name, fixture(name, missing=missing))['status'], 'not_found' if missing else 'found')

    def test_genius_requires_each_identity_field(self):
        body = GENIUS.format(username='sample')
        for line in body.splitlines()[1:-1]:
            with self.subTest(removed=line):
                self.assertEqual(self.run_site('Genius Artists', httpx.Response(200, text=body.replace(line,'')))['status'], 'unknown')
        for invalid in (body.replace('/sample','/other'), body.replace('profile_identity-name_iq_and_role_icon','unrelated'), '<h1>sample Genius</h1>', '<script>'+body+'</script>'):
            self.assertEqual(self.run_site('Genius Artists',httpx.Response(200,text=invalid))['status'],'unknown')

    def test_odysee_rejects_unbound_or_invalid_claims(self):
        original = channel_payload()
        for field, invalid in [('name','@other'),('normalized_name','@other'),('claim_id','bad'),('value_type','stream'),('value',[]),('permanent_url','lbry://@other#123')]:
            data=deepcopy(original); data['result']['lbry://@sample'][field]=invalid
            self.assertEqual(self.run_site('Odysee',httpx.Response(200,json=data))['status'],'unknown')
        for data in ({}, {'jsonrpc':'2.0','id':True,'result':original['result']}, channel_payload('other'),
                     dict(original,error={'code':-1}), dict(original,jsonrpc='1.0')):
            self.assertEqual(self.run_site('Odysee',httpx.Response(200,json=data))['status'],'unknown')

    def test_odysee_missing_must_be_explicit_and_query_bound(self):
        for error in ({'name':'NOT_FOUND'}, {'name':'NOT_FOUND','text':'Could not find channel in "lbry://@other".'}, {'name':'OTHER','text':'missing'}):
            data=channel_payload(); data['result']['lbry://@sample']={'error':error}
            self.assertEqual(self.run_site('Odysee',httpx.Response(200,json=data))['status'],'unknown')

    def test_conflicting_channel_and_absence_evidence_is_unknown(self):
        data=channel_payload()
        data['result']['lbry://@sample']['error']=channel_payload(missing=True)['result']['lbry://@sample']['error']
        self.assertEqual(self.run_site('Odysee',httpx.Response(200,json=data))['status'],'unknown')

    def test_odysee_transport_failures_and_old_oembed_are_unknown(self):
        for response in [httpx.Response(code,json=channel_payload()) for code in (302,401,403,404,429,500)]+[
            httpx.Response(200,text='The URL is not associated with a video claim.'),
            httpx.Response(200,text='x'*1_000_001)]:
            self.assertEqual(self.run_site('Odysee',response)['status'],'unknown')

    def test_odysee_only_sends_anonymous_read_only_resolve(self):
        platform=next(p for p in USERNAME_PLATFORMS if p['name']=='Odysee')
        def handler(req):
            import json
            self.assertEqual(req.method,'POST')
            self.assertNotIn('authorization',req.headers)
            self.assertEqual(json.loads(req.content),{'jsonrpc':'2.0','method':'resolve','params':{'urls':['lbry://@sample']},'id':1})
            return fixture('Odysee')
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username('sample',platform,client)
        self.assertEqual(asyncio.run(run())['status'],'found')

    def test_wrong_profile_type_redirects_remain_unknown(self):
        for name, destination in [('Genius Users','https://genius.com/artists/sample'),('Society6','https://society6.com/collections/sample'),('ReverbNation','https://legacy.reverbnation.com/')]:
            platform=next(p for p in USERNAME_PLATFORMS if p['name']==name)
            async def run():
                def handler(req):
                    if str(req.url)!=destination:
                        return httpx.Response(302,headers={'Location':destination})
                    return httpx.Response(200,text='<h1>sample</h1> Profile not found')
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                    return await check_single_username('sample',platform,client)
            self.assertEqual(asyncio.run(run())['status'],'unknown')
            self.assertEqual(self.run_site(name,httpx.Response(404))['status'],'not_found')
