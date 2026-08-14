import unittest

from osint.dorking import (
    generate_dorks,
    get_email_trace_domains,
    get_priority_email_trace_domains,
    get_username_platform_domains,
)


class DorkingTests(unittest.TestCase):
    def test_email_dorks_include_username_platform_domains(self):
        dorks = generate_dorks("new-account@example.test")
        platform_dorks = [
            item for item in dorks
            if item["type"].startswith("Eğitim/Abonelik + Platform Arama")
        ]

        self.assertGreater(len(platform_dorks), 0)
        self.assertIn("%22new-account%40example.test%22", platform_dorks[0]["url"])
        self.assertIn("site:sorbil.org", platform_dorks[0]["url"])
        self.assertIn("site:udemy.com", platform_dorks[0]["url"])

    def test_username_dorks_do_not_expand_to_platform_domain_searches(self):
        dorks = generate_dorks("new_account")

        self.assertFalse(
            any(
                item["type"].startswith("Eğitim/Abonelik + Platform Arama")
                for item in dorks
            )
        )

    def test_username_platform_domains_are_deduplicated(self):
        domains = get_username_platform_domains()

        self.assertEqual(len(domains), len(set(domains)))
        self.assertIn("myanimelist.net", domains)

    def test_priority_email_trace_domains_include_education_and_subscriptions(self):
        domains = get_priority_email_trace_domains()

        self.assertEqual(len(domains), len(set(domains)))
        self.assertIn("sorbil.org", domains)
        self.assertIn("udemy.com", domains)
        self.assertIn("netflix.com", domains)

    def test_email_trace_domains_merge_priority_and_username_domains(self):
        domains = get_email_trace_domains()

        self.assertEqual(len(domains), len(set(domains)))
        self.assertLess(
            len(get_username_platform_domains()),
            len(domains),
        )
        self.assertIn("sorbil.org", domains)
        self.assertIn("github.com", domains)


if __name__ == "__main__":
    unittest.main()
