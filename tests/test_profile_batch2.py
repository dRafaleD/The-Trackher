"""Independent reduced fixtures from the second 40-site review."""
import asyncio
import unittest
import httpx
from osint.username_checker import USERNAME_PLATFORMS, check_single_username
from osint.profile_evidence import evaluate_profile

FORUMS = (
    'OpenAI Developer Community', 'Mozilla Discourse', 'Unreal Engine Forums',
    'Brave Community', 'Elastic Discuss', 'Ubuntu Community Hub', 'Signal Community',
    'Obsidian Forum', 'Home Assistant Community', 'Hugging Face Forums', 'PyTorch Forums',
    'Rust Users Forum', 'Jupyter Community', 'Django Forum', 'KDE Discuss', 'Godot Forum',
    'YazBel Forum', 'Pardus Forumları', 'Hack The Box Forum', 'Car Talk Community',
    'Cloudflare Community', 'Envato Forum', 'Icons8 Community', 'Leasehackr',
)
API = {'HackerNews': {'id':'sample'}, 'Hugging Face': {'user':'sample'},
       'TopCoder': {'handle':'sample'}, 'Gravatar': {'entry':[{'preferredUsername':'sample'}]},
       'Coderwall': {'username':'sample'}}
UNVERIFIED = ('Bitbucket', 'HackerRank', 'ArtStation', 'Sketchfab', 'NotABug.org', 'PyPi')
HTML = {
 'Telegram': '<title>Telegram: View @sample</title><div class="tgme_page_title"><span>Channel</span></div>',
 'AtCoder': '<title>sample - AtCoder</title><meta content="https://atcoder.jp/users/sample" property="og:url">',
 'Twitch': '<meta content="https://www.twitch.tv/sample" property="og:url"><meta content="video.other" property="og:type">',
 'Last.fm': '<meta content="https://www.last.fm/user/sample" property="og:url"><h1 class="header-title">Sample</h1>',
 'Steam': '<profile><steamID64>76561197968052866</steamID64><customURL>sample</customURL></profile>',
}
NAMES = set(FORUMS) | set(API) | set(UNVERIFIED) | set(HTML)


def fixture(name, username='sample', missing=False):
    if name in FORUMS:
        return httpx.Response(404, json={'errors':['The requested URL or resource could not be found.'],'error_type':'not_found'}) if missing else httpx.Response(200, json={'user':{'id':42,'username':username}})
    if name in API:
        if missing:
            if name=='HackerNews':
                return httpx.Response(200, content=b'null', headers={'Content-Type':'application/json'})
            if name=='Gravatar':
                return httpx.Response(404, json='User not found')
            return httpx.Response(404, json={'error':'Not found'})
        import json
        return httpx.Response(200, json=json.loads(json.dumps(API[name]).replace('sample',username)))
    if name in UNVERIFIED:
        return httpx.Response(404 if missing else 200, text=f'<title>{username}</title><h1>{username}</h1>')
    if missing:
        if name=='Steam':
            return httpx.Response(200, text='<response><error>The specified profile could not be found.</error></response>')
        if name in ('AtCoder','Last.fm'):
            return httpx.Response(404, text='<h1>Not found</h1>')
        return httpx.Response(200, text=f'<title>Contact {username}</title><h1>{username}</h1>')
    return httpx.Response(200, text=HTML[name].replace('sample',username).replace('Sample',username))


def expected(name, missing=False):
    if name=='YazBel Forum' or name in UNVERIFIED:
        return 'unknown'
    if missing and name in ('HackerNews','Telegram','Twitch'):
        return 'unknown'
    return 'not_found' if missing else 'found'


class ProfileBatchTwoTests(unittest.TestCase):
    def run_case(self, name, response, user='sample'):
        platform=next(p for p in USERNAME_PLATFORMS if p['name']==name)
        calls=[]
        def handler(req):
            calls.append(req)
            return response
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await check_single_username(user,platform,client)
        result=asyncio.run(run())
        self.assertLessEqual(len(calls),1)
        return result

    def test_exactly_40_additional_sites_no_overlap(self):
        from test_api_hardening import PAYLOADS
        selected={p['name'] for p in USERNAME_PLATFORMS if p.get('review_batch')=='2026-09-08-2'}
        self.assertEqual(selected,NAMES)
        self.assertEqual(len(selected),40)
        self.assertFalse(selected & PAYLOADS.keys())
        self.assertEqual(len(selected | PAYLOADS.keys()),80)

    def test_reduced_positive_and_negative_contracts(self):
        for name in sorted(NAMES):
            for missing in (False,True):
                with self.subTest(site=name,missing=missing):
                    self.assertEqual(self.run_case(name,fixture(name,missing=missing))['status'],expected(name,missing))

    def test_rate_limits_authentication_and_service_errors(self):
        for name in sorted(NAMES):
            for code in (401,403,429,500,503):
                with self.subTest(site=name,status=code):
                    self.assertEqual(self.run_case(name,httpx.Response(code,text='sample'))['status'],'unknown')

    def test_api_schema_drift_and_html_echo_stay_unknown(self):
        for name in FORUMS+tuple(API):
            for response in (httpx.Response(200,json={}), httpx.Response(200,text='<h1>sample</h1>')):
                with self.subTest(site=name):
                    self.assertEqual(self.run_case(name,response)['status'],'unknown')

    def test_profile_evidence_in_script_or_comment_is_ignored(self):
        for name in ('Telegram','AtCoder','Twitch','Last.fm'):
            for body in ('<script>'+HTML[name]+'</script>', '<!--'+HTML[name]+'-->'):
                with self.subTest(site=name):
                    self.assertEqual(self.run_case(name,httpx.Response(200,text=body))['status'],'unknown')

    def test_twitch_person_marker_or_canonical_alone_is_insufficient(self):
        for body in ('<script>{"@type":"Person"}</script>', '<link rel="canonical" href="https://www.twitch.tv/sample">', '<meta property="og:url" content="https://www.twitch.tv/sample">'):
            self.assertEqual(self.run_case('Twitch',httpx.Response(200,text=body))['status'],'unknown')

    def test_steam_requires_matching_vanity_and_numeric_id(self):
        for body in ('<profile><steamID64>76561197968052866</steamID64><customURL>someone_else</customURL></profile>', '<profile><steamID64>oops</steamID64><customURL>sample</customURL></profile>', '<!DOCTYPE profile><profile/>', '<profile><steamID64>'):
            self.assertEqual(self.run_case('Steam',httpx.Response(200,text=body))['status'],'unknown')

    def test_html_attributes_can_change_order_and_quotes(self):
        body="<META CONTENT='video.other' PROPERTY='og:type'/><META CONTENT='https://www.twitch.tv/sample' PROPERTY='og:url'/>"
        self.assertEqual(self.run_case('Twitch',httpx.Response(200,text=body))['status'],'found')

    def test_login_redirect_and_browser_challenge_are_unknown(self):
        platform=next(p for p in USERNAME_PLATFORMS if p['name']=='AtCoder')
        response=httpx.Response(404,request=httpx.Request('GET','https://atcoder.jp/login'))
        self.assertEqual(evaluate_profile('sample',platform,response)[0],'unknown')
        for name in HTML:
            result=self.run_case(name,httpx.Response(404,text='<title>Client Challenge</title>'))
            self.assertEqual(result['status'],'unknown')

    def test_hackernews_null_is_not_absence_proof(self):
        self.assertEqual(self.run_case('HackerNews',httpx.Response(200,content=b'null'))['status'],'unknown')
