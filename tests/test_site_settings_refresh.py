"""Independent evidence fixtures for the additional October site review."""
import asyncio
import unittest
import httpx
from osint.username_checker import USERNAME_PLATFORMS, check_single_username

BODIES = {
    'Crowdin': '<title>Public Display Name (sample) \u2013 Crowdin</title><link rel="canonical" href="https://crowdin.com/profile/sample">',
    'Linktree': '<meta property="og:url" content="https://linktr.ee/sample"><meta property="og:type" content="profile"><meta property="profile:username" content="sample">',
}

def fixture(name, username='sample', missing=False):
    if missing:
        return httpx.Response(404 if name == 'Crowdin' else 406, text='Profile unavailable')
    return httpx.Response(200, text=BODIES[name].replace('sample', username))

class SiteSettingsRefreshTests(unittest.TestCase):
    def run_case(self, name, response, username='sample', url=None):
        platform = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
        def handler(req):
            if url and req.url.host != 'example.test':
                return httpx.Response(302, headers={'Location': url})
            return response
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
                return await check_single_username(username, platform, client)
        return asyncio.run(run())

    def test_real_profile_shapes_and_negative_controls(self):
        for name in BODIES:
            self.assertEqual(self.run_case(name, fixture(name))['status'], 'found')
            self.assertEqual(self.run_case(name, fixture(name, missing=True))['status'], 'not_found' if name == 'Crowdin' else 'unknown')

    def test_username_echo_and_missing_identity_are_insufficient(self):
        for name, body in BODIES.items():
            for invalid in ('<h1>sample</h1>', body.replace('sample', 'someone_else'), '<script>'+body+'</script>', '<!--'+body+'-->'):
                with self.subTest(name=name, body=invalid):
                    self.assertEqual(self.run_case(name, httpx.Response(200, text=invalid))['status'], 'unknown')

    def test_each_evidence_element_is_required(self):
        for body in (
            BODIES['Linktree'].replace('profile:username', 'generic:username'),
            BODIES['Linktree'].replace('content="profile"', 'content="website"'),
            BODIES['Linktree'].replace('https://linktr.ee/sample', 'https://linktr.ee/other'),
        ):
            self.assertEqual(self.run_case('Linktree', httpx.Response(200, text=body))['status'], 'unknown')
        for body in (BODIES['Crowdin'].replace('(sample)', '(samples)'), BODIES['Crowdin'].replace('canonical', 'alternate'), BODIES['Crowdin'].replace('Crowdin</title>', 'Crowdin login</title>')):
            self.assertEqual(self.run_case('Crowdin', httpx.Response(200, text=body))['status'], 'unknown')

    def test_renamed_display_title_does_not_change_linktree_identity(self):
        body='<title>Anything the owner wants</title>'+BODIES['Linktree']
        self.assertEqual(self.run_case('Linktree', httpx.Response(200, text=body))['status'], 'found')

    def test_challenges_errors_and_foreign_redirects_are_unknown(self):
        for name in BODIES:
            for code in (401,403,429,500,503):
                self.assertEqual(self.run_case(name, httpx.Response(code, text=BODIES[name]))['status'], 'unknown')
            self.assertEqual(self.run_case(name, httpx.Response(404, text='<title>Client Challenge</title>'))['status'], 'unknown')
            self.assertEqual(self.run_case(name, fixture(name), url='https://example.test/sample')['status'], 'unknown')

    def test_usernames_with_regex_characters_are_literal(self):
        self.assertEqual(self.run_case('Crowdin', fixture('Crowdin', 'sample.x'), username='sample.x')['status'], 'found')
        self.assertEqual(self.run_case('Crowdin', fixture('Crowdin', 'sampleax'), username='sample.x')['status'], 'unknown')
