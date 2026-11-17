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
        self.assertEqual(seen, [{"timeout": FB["timeout"], "user_agent": check.PLAIN_UA}] * 2)  # preflight + name

    def test_self_test_accepts_likely_free(self):
        def fetch(url, **kw):
            return R(TAKEN if url.endswith("/" + FB["canary"]["taken"]) else FREE)
        report = check.self_test({"facebook": FB}, fetch, lambda s: None)
        self.assertEqual(report[0]["state"], "ok", report)

    def test_generic_page_for_everyone_is_blocked_not_likely_free(self):
        # seen from a sandbox IP: even the taken canary gets the bare "Facebook" page
        res = check.check_platform("facebook", P, ["acmestudio", "kukikalabs"], lambda url, **kw: R(FREE),
                                   lambda s: None)
        self.assertEqual({r["reason"] for r in res.values()}, {"blocked"})

    def test_walled_page_falls_back_to_graph_api(self):
        graph = FB["fallback"]["url"]

        def fetch(url, **kw):
            if url == graph.format(name=FB["fallback"]["canary"]["taken"]):
                return check.Response(200, "{}", url)
            if url.startswith("https://graph.facebook.com/"):
                return check.Response(404, "{}", url)
            return R("<html>", url="https://www.facebook.com/login/?next=x")  # main page walled
        res = check.check_platform("facebook", P, ["kukikalabs"], fetch, lambda s: None)
        r = res["kukikalabs"]
        self.assertEqual((r["status"], r["reason"], r["via"]), ("unknown", "likely_free", FB["fallback"]["fallback_name"]))
        self.assertEqual(r["url"], "https://www.facebook.com/kukikalabs")  # links to the profile, not the API
        self.assertIn("public Pages", check._hints([{**r, "input": "kukikalabs"}], ["facebook"], P)[0])


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
