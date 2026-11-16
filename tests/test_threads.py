"""Threads: checked directly, then read together with Instagram, which holds every Threads handle."""
import unittest

from _load import FIXTURES, check

P = check.load_platforms()
TH = P["threads"]
IG_TAKEN = (FIXTURES / "instagram_taken.html").read_text(encoding="utf-8")
IG_FREE = (FIXTURES / "instagram_free.html").read_text(encoding="utf-8")
TH_ACTIVE = "<html><head><title>Acme (&#064;acme) • Threads, Say more</title></head></html>"
TH_LOGIN = "<html><head><title>Threads • Log in</title></head></html>"


def fake(ig, th):
    """ig/th: handle -> body; canaries answer as a healthy IP would."""
    def fetch(url, **kw):
        if "instagram.com" in url:
            name = url.rstrip("/").rsplit("/", 1)[1]
            body = IG_TAKEN if name == P["instagram"]["canary"]["taken"] else ig[name]
        else:
            name = url.rsplit("@", 1)[1]
            body = TH_ACTIVE if name == TH["canary"]["taken"] else th[name]
        return check.Response(200, body, url)
    return fetch


def threads_result(ig, th, keys=("instagram", "threads")):
    entries = [{"input": h, "handle": h, "labels": []} for h in ig]
    out = check.run(entries, list(keys), [], P, fake(ig, th), lambda s: None)
    return {r["handle"]: r for r in out if r["platform"] == "threads"}


class ThreadsClassifyTest(unittest.TestCase):
    def test_active_profile_and_login_page(self):
        self.assertEqual(check.classify(TH, check.Response(200, TH_ACTIVE, "https://www.threads.com/@acme")),
                         ("taken", None))
        login = check.Response(200, TH_LOGIN, "https://www.threads.com/login/?next=x")
        self.assertEqual(check.classify(TH, login), ("available", None))


class ThreadsHeldByInstagramTest(unittest.TestCase):
    def test_instagram_taken_threads_not_active_is_held(self):
        r = threads_result({"acmestudio": IG_TAKEN}, {"acmestudio": TH_LOGIN})["acmestudio"]
        self.assertEqual((r["status"], r["reason"]), ("taken", "held_by:instagram"))

    def test_both_free(self):
        r = threads_result({"acmestudio": IG_FREE}, {"acmestudio": TH_LOGIN})["acmestudio"]
        self.assertEqual((r["status"], r["reason"]), ("available", None))

    def test_active_threads_is_plain_taken(self):
        r = threads_result({"acmestudio": IG_TAKEN}, {"acmestudio": TH_ACTIVE})["acmestudio"]
        self.assertEqual((r["status"], r["reason"]), ("taken", None))

    def test_instagram_unknown_makes_threads_unknown(self):
        r = threads_result({"acmestudio": "<html>no marker</html>"}, {"acmestudio": TH_LOGIN})["acmestudio"]
        self.assertEqual(r["status"], "unknown")

    def test_threads_column_alone_still_asks_instagram(self):
        r = threads_result({"acmestudio": IG_TAKEN}, {"acmestudio": TH_LOGIN}, keys=("threads",))
        self.assertEqual(r["acmestudio"]["reason"], "held_by:instagram")

    def test_render_lock_and_hint(self):
        results = [{"input": "a", "handle": "acmestudio", "platform": "threads", "status": "taken",
                    "reason": "held_by:instagram", "url": "https://www.threads.com/@acmestudio"}]
        md = check.render_markdown(results, ["threads"], [], P)
        row = next(l for l in md.splitlines() if l.startswith("| Threads"))
        self.assertIn("🔒", row)
        self.assertIn("🔒 held by the Instagram account", md)
        self.assertEqual(md.count("turn on Threads"), 1)
        self.assertIn("https://www.instagram.com/acmestudio/", md)  # the holder's profile, not Threads' error page


if __name__ == "__main__":
    unittest.main()
