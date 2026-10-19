"""Reduced public-response controls for two observed markup variations."""
from pathlib import Path
import unittest
import httpx

from osint.profile_evidence import evaluate_profile
from osint.username_checker import USERNAME_PLATFORMS


class LiveMarkupVariants(unittest.TestCase):
    def evaluate(self, name, body, url=None, status=200):
        site = next(p for p in USERNAME_PLATFORMS if p['name'] == name)
        response = httpx.Response(status, text=body, request=httpx.Request('GET', url or site['url'].format('sample')))
        return evaluate_profile('sample', site, response)[0]

    def fixture(self, name):
        return (Path(__file__).parent / 'fixtures' / name).read_text(encoding='utf-8')

    def test_snapchat_turkish_title_retains_all_three_identity_requirements(self):
        body = self.fixture('snapchat_tr_20261017.html')
        self.assertEqual(self.evaluate('Snapchat', body), 'found')
        for removed in body.splitlines():
            with self.subTest(removed=removed):
                self.assertEqual(self.evaluate('Snapchat', body.replace(removed, '')), 'unknown')
        self.assertEqual(self.evaluate('Snapchat', body.replace('sample', 'someone_else')), 'unknown')

    def test_snapchat_unknown_title_challenge_and_redirect_remain_unknown(self):
        body = self.fixture('snapchat_tr_20261017.html')
        self.assertEqual(self.evaluate('Snapchat', body.replace('Snapchat Hikayeleri', 'Unrecognized title')), 'unknown')
        self.assertEqual(self.evaluate('Snapchat', body, url='https://www.snapchat.com/login'), 'unknown')
        self.assertEqual(self.evaluate('Snapchat', '<title>Client Challenge</title>' + body, status=403), 'unknown')

    def test_aboutme_profile_type_variation_does_not_accept_unrelated_pages(self):
        body = self.fixture('aboutme_profile_20261017.html')
        self.assertEqual(self.evaluate('About.me', body), 'found')
        self.assertEqual(self.evaluate('About.me', body.replace('content="profile"', 'content="aboutme_prod:page"')), 'found')
        self.assertEqual(self.evaluate('About.me', body.replace('content="profile"', 'content="article"')), 'unknown')
        self.assertEqual(self.evaluate('About.me', body.replace('/sample', '/other')), 'unknown')
        self.assertEqual(self.evaluate('About.me', body.replace('<h1 class="name">Tony Conrad</h1>', '')), 'unknown')


if __name__ == '__main__':
    unittest.main()
