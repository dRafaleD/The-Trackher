import unittest

from osint.dorking import generate_dorks


class DorkingTests(unittest.TestCase):
    def test_generate_dorks_returns_standard_search_links(self):
        dorks = generate_dorks("new_account")

        self.assertEqual(len(dorks), 8)
        self.assertTrue(all(item["url"] for item in dorks))
        self.assertTrue(any("new_account" in item["url"] for item in dorks))
        self.assertTrue(any(item["type"] == "Sosyal Medya Arama" for item in dorks))

    def test_generate_dorks_encodes_special_characters(self):
        dorks = generate_dorks("test user")

        self.assertTrue(any("test+user" in item["url"] for item in dorks))
        self.assertTrue(all(" " not in item["url"] for item in dorks))

    def test_generate_dorks_uses_email_specific_templates(self):
        dorks = generate_dorks("owner@example.com")

        self.assertEqual(len(dorks), 8)
        self.assertTrue(any("Tam E-posta Arama" == item["type"] for item in dorks))
        self.assertTrue(any("owner%40example.com" in item["url"] for item in dorks))
        self.assertFalse(any(item["type"] == "Sosyal Medya Arama" for item in dorks))


if __name__ == "__main__":
    unittest.main()
