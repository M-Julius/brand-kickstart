"""Facebook: taken is definite, a missing page is only *likely* free (age-restricted pages look the same)."""
import unittest

from _load import check

P = check.load_platforms()
FB = P["facebook"]
TAKEN = '<meta property="al:android:url" content="fb://profile/100044561550831" />'
FREE = "<html><head><title>Facebook</title></head><body></body></html>"


def R(body, url="https://web.facebook.com/x?_rdc=1&_rdr", status=200):
    return check.Response(status, body, url)


class FacebookClassifyTest(unittest.TestCase):
    def test_taken_and_likely_free(self):
        self.assertEqual(check.classify(FB, R(TAKEN)), ("taken", None))
        self.assertEqual(check.classify(FB, R(FREE)), ("unknown", "likely_free"))

    def test_alias_hosts_allowed_other_hosts_blocked(self):
        self.assertEqual(check.classify(FB, R(TAKEN, "https://m.facebook.com/x")), ("taken", None))
        self.assertEqual(check.classify(FB, R(TAKEN, "https://evil.example/x")), ("unknown", "blocked"))
        yt = check.Response(200, "<html>", "https://consent.youtube.com/m?continue=x")
        self.assertEqual(check.classify(P["youtube"], yt), ("unknown", "blocked"))

    def test_rule(self):
        self.assertIsNone(check.rule_error(FB, "acme.studio"))
        self.assertIsNotNone(check.rule_error(FB, "acme"))        # 5 characters minimum
        self.assertIsNotNone(check.rule_error(FB, "acme_studio"))  # letters, digits and periods only


class FacebookRunTest(unittest.TestCase):
    def test_platform_timeout_is_passed(self):
        seen = []

        def fetch(url, **kw):
            seen.append(kw)
            return R(TAKEN)
        check.check_platform("facebook", P, ["acmestudio"], fetch, lambda s: None)
        self.assertEqual(seen, [{"timeout": FB["timeout"], "user_agent": check.PLAIN_UA}])

    def test_self_test_accepts_likely_free(self):
        def fetch(url, **kw):
            return R(TAKEN if url.endswith("/" + FB["canary"]["taken"]) else FREE)
        report = check.self_test({"facebook": FB}, fetch, lambda s: None)
        self.assertEqual(report[0]["state"], "ok", report)


class FacebookRenderTest(unittest.TestCase):
    def res(self, inp, platform, status, reason=None):
        return {"input": inp, "handle": inp, "platform": platform, "status": status, "reason": reason,
                "url": f"https://{platform}.test/{inp}"}

    def test_likely_free_cell_hint_and_order(self):
        results = [self.res("aaaaa", "facebook", "taken"), self.res("aaaaa", "youtube", "available"),
                   self.res("bbbbb", "facebook", "unknown", "likely_free"), self.res("bbbbb", "youtube", "available")]
        md = check.render_markdown(results, ["facebook", "youtube"], [], P)
        header = md.splitlines()[0]
        self.assertLess(header.index("bbbbb"), header.index("aaaaa"))   # likely free still sorts first
        fb_row = next(l for l in md.splitlines() if l.startswith("| Facebook"))
        self.assertIn("✅?", fb_row)
        self.assertIn("✅? probably free", md)
        self.assertEqual(md.count("age-restricted"), 1)
        self.assertIn("https://facebook.test/bbbbb", md)


if __name__ == "__main__":
    unittest.main()
