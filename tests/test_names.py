import unittest

from _load import check


class NamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.P = check.load_platforms()

    def test_all_platforms_have_required_keys(self):
        for key, p in self.P.items():
            for field in ("name", "profile_url", "check", "rule", "modes"):
                self.assertIn(field, p, f"{key} missing {field}")
            if p["check"]["type"] not in ("manual_only", "same_as"):
                self.assertIn("url", p, key)
                self.assertIn("canary", p, key)

    def test_tokenize_accents_and_case(self):
        self.assertEqual(check.tokenize("Kopi Café"), ["kopi", "cafe"])
        self.assertEqual(check.tokenize("Acme Studio"), ["acme", "studio"])
        self.assertEqual(check.tokenize("acmestudio.id"), ["acmestudio", "id"])
        self.assertEqual(check.to_handle("Acme Studio"), "acmestudio")
        self.assertEqual(check.to_handle("acmestudio.id"), "acmestudio.id")
        self.assertEqual(check.to_handle("AcmeStudio_ID"), "acmestudio_id")
        self.assertEqual(check.to_handle("Kopi Café"), "kopicafe")

    def test_rule_error_x(self):
        x = self.P["x"]
        self.assertIsNone(check.rule_error(x, "acmestudio"))
        self.assertIsNotNone(check.rule_error(x, "acme.studio"))
        self.assertIsNotNone(check.rule_error(x, "a" * 16))

    def test_variants_brand(self):
        self.assertEqual(
            check.variants(["acme", "studio"], "brand", "id"),
            ["acmestudio", "acme.studio", "acme_studio", "acme-studio",
             "acmestudio.id", "acmestudio_id", "acmestudioofficial", "acmestudiohq", "theacmestudio"],
        )

    def test_variants_project_adds_get_and_app_and_caps(self):
        v = check.variants(["acme", "studio"], "project", "id")
        self.assertIn("getacmestudio", v)
        self.assertIn("acmestudioapp", v)
        self.assertLessEqual(len(v), check.MAX_VARIANTS)

    def test_variants_single_token_no_country(self):
        self.assertEqual(check.variants(["kopi"], "brand", None),
                         ["kopi", "kopiofficial", "kopihq", "thekopi"])


if __name__ == "__main__":
    unittest.main()
