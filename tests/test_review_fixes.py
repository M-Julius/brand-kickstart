import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _load import check
from test_selftest import fixture_fetch

P = check.load_platforms()


class ReviewFixes(unittest.TestCase):
    def test_non_decomposable_letters_transliterated(self):
        self.assertEqual(check.to_handle("Bjørn Brew"), "bjornbrew")
        self.assertEqual(check.to_handle("Straße"), "strasse")
        self.assertEqual(check.to_handle("Łódź Kopi"), "lodzkopi")
        self.assertEqual(check.to_handle("Æther"), "aether")

    def test_unconvertible_letters_rejected(self):
        with self.assertRaises(ValueError):
            check.tokenize("Kopi 東京")

    def test_malformed_handles_rejected_by_rules(self):
        for key, bad in [("instagram", ".kopi"), ("instagram", "kopi."), ("instagram", "ko..pi"),
                         ("threads", "kopi."), ("tiktok", "kopi."), ("youtube", "-kopi"), ("youtube", "kopi.")]:
            with self.subTest(key=key, handle=bad):
                self.assertIsNotNone(check.rule_error(P[key], bad))
        self.assertIsNone(check.rule_error(P["instagram"], "acme.studio"))
        self.assertIsNone(check.rule_error(P["instagram"], "_kopi_"))

    def test_trailing_punctuation_stripped_from_exact_handle(self):
        self.assertEqual(check.to_handle("Kopi."), "kopi")
        self.assertEqual(check.to_handle("-acme.studio-"), "acme.studio")

    def test_redirect_to_other_host_is_blocked(self):
        resp = check.Response(200, "<html>consent</html>", "https://consent.youtube.com/m?continue=x")
        self.assertEqual(check.classify(P["youtube"], resp), ("unknown", "blocked"))
        same = check.Response(200, "", "https://www.youtube.com/@youtube")
        self.assertEqual(check.classify(P["youtube"], same), ("taken", None))

    def test_country_lowercased(self):
        calls = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"BRAND_KICKSTART_CONFIG": os.path.join(d, "c.json")}), \
                mock.patch.object(check, "run", lambda e, *a, **k: calls.append(e) or []), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            check.main(["acme studio", "--variants", "--country", ".ID", "--json"])
        self.assertIn("acmestudio.id", [e["handle"] for e in calls[0]])

    def test_self_test_network_error_is_not_broken(self):
        yt = P["youtube"]["url"].format(name=P["youtube"]["canary"]["taken"])
        fetch = fixture_fetch({yt: check.Response(0, "timed out", yt)})
        state = {r["platform"]: r["state"] for r in check.self_test(P, fetch, lambda s: None)}
        self.assertEqual(state["youtube"], "blocked")


if __name__ == "__main__":
    unittest.main()
