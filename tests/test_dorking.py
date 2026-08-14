import unittest

from osint.dorking import generate_dorks, get_username_platform_domains


class DorkingTests(unittest.TestCase):
    def test_email_dorks_include_username_platform_domains(self):
        dorks = generate_dorks("new-account@example.test")
        platform_dorks = [
            item for item in dorks
            if item["type"].startswith("Platform Domain Arama")
        ]

        self.assertGreater(len(platform_dorks), 0)
        self.assertIn("%22new-account%40example.test%22", platform_dorks[0]["url"])
        self.assertIn("site:github.com", platform_dorks[0]["url"])

    def test_username_dorks_do_not_expand_to_platform_domain_searches(self):
        dorks = generate_dorks("new_account")

        self.assertFalse(
            any(item["type"].startswith("Platform Domain Arama") for item in dorks)
        )

    def test_username_platform_domains_are_deduplicated(self):
        domains = get_username_platform_domains()

        self.assertEqual(len(domains), len(set(domains)))
        self.assertIn("myanimelist.net", domains)


if __name__ == "__main__":
    unittest.main()
