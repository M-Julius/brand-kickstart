import dataclasses
import json
import unittest

from _load import FIXTURES, check

P = check.load_platforms()
IG_TAKEN = (FIXTURES / "instagram_taken.html").read_text(encoding="utf-8")
IG_FREE = (FIXTURES / "instagram_free.html").read_text(encoding="utf-8")


def R(status, body="", headers=None, url="https://example.test/"):
    return check.Response(status, body, url, headers or {})


class Fake:
    """Scripted fetch: url -> list of responses (last one repeats). Records every call."""

    def __init__(self, script=None, default=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.default = default
        self.calls = []
        self.kwargs = []
        self.sleeps = []

    def fetch(self, url, **kw):
        self.calls.append(url)
        self.kwargs.append(kw)
        queue = self.script.get(url)
        if queue:
            resp = queue.pop(0) if len(queue) > 1 else queue[0]
            # Scripted responses come from the requested URL unless a test sets a redirect target.
            return dataclasses.replace(resp, url=url) if resp.url == "https://example.test/" else resp
        if self.default:
            return self.default(url)
        raise AssertionError(f"unexpected request {url}")

    def sleep(self, seconds):
        self.sleeps.append(seconds)


def ig(name):
    return P["instagram"]["url"].format(name=name)


def yt(name):
    return P["youtube"]["url"].format(name=name)


class RunnerTest(unittest.TestCase):
    def test_sequential_with_interval(self):
        f = Fake({yt("aaa"): [R(200)], yt("bbb"): [R(404)], yt("ccc"): [R(200)]})
        out = check.check_platform("youtube", P, ["aaa", "bbb", "ccc"], f.fetch, f.sleep)
        self.assertEqual(f.sleeps, [0.3, 0.3])
        self.assertEqual([out[h]["status"] for h in ("aaa", "bbb", "ccc")], ["taken", "available", "taken"])
        self.assertEqual(out["aaa"]["url"], "https://www.youtube.com/@aaa")

    def test_retry_after_then_stop(self):
        f = Fake({ig("instagram"): [R(200, IG_TAKEN)],
                  ig("hone"): [R(429, headers={"retry-after": "7"}), R(429)]})
        out = check.check_platform("instagram", P, ["hone", "htwo"], f.fetch, f.sleep)
        self.assertEqual((out["hone"]["status"], out["hone"]["reason"]), ("unknown", "rate_limited"))
        self.assertEqual((out["htwo"]["status"], out["htwo"]["reason"]), ("unknown", "rate_limited"))
        self.assertIn(7, f.sleeps)
        self.assertNotIn(ig("htwo"), f.calls)

    def test_retry_once_then_success(self):
        f = Fake({yt("aaa"): [R(503), R(404)]})
        out = check.check_platform("youtube", P, ["aaa"], f.fetch, f.sleep)
        self.assertEqual(out["aaa"]["status"], "available")
        self.assertEqual(f.sleeps, [5])

    def test_server_error_retried_then_platform_continues(self):
        x = lambda n: P["x"]["url"].format(name=n)  # noqa: E731
        f = Fake({x("aaaaa"): [R(500, "{}"), R(500, "{}")],
                  x("bbbbb"): [R(500, "{}"), R(200, '{"reason":"available"}')]})
        out = check.check_platform("x", P, ["aaaaa", "bbbbb"], f.fetch, f.sleep)
        self.assertEqual((out["aaaaa"]["status"], out["aaaaa"]["reason"]), ("unknown", "server_error"))
        self.assertEqual(out["bbbbb"]["status"], "available")  # one server error does not stop X

    def test_network_error_retried_once(self):
        x = lambda n: P["x"]["url"].format(name=n)  # noqa: E731
        f = Fake({x("aaaaa"): [R(0, "timed out"), R(200, '{"reason":"taken"}')]})
        out = check.check_platform("x", P, ["aaaaa"], f.fetch, f.sleep)
        self.assertEqual(out["aaaaa"]["status"], "taken")
        self.assertEqual(f.calls, [x("aaaaa"), x("aaaaa")])

    def test_canary_blocked_marks_all(self):
        f = Fake({ig("instagram"): [R(200, "<html>no marker</html>")]})
        out = check.check_platform("instagram", P, ["hone", "htwo"], f.fetch, f.sleep)
        self.assertEqual({(r["status"], r["reason"]) for r in out.values()}, {("unknown", "blocked")})
        self.assertEqual(f.calls, [ig("instagram")])

    def test_plain_user_agent_only_where_declared(self):
        f = Fake({yt("acmestudio"): [R(200)], ig("instagram"): [R(200, IG_TAKEN)], ig("acmestudio"): [R(200, IG_FREE)]})
        entries = [{"input": "acmestudio", "handle": "acmestudio", "labels": []}]
        check.run(entries, ["instagram", "youtube"], [], P, f.fetch, f.sleep)
        by_url = dict(zip(f.calls, f.kwargs))
        self.assertEqual(by_url[ig("acmestudio")].get("user_agent"), check.PLAIN_UA)
        self.assertNotIn("user_agent", by_url[yt("acmestudio")])

    def test_invalid_sends_no_request(self):
        f = Fake()
        entries = [{"input": "acme.studio", "handle": "acme.studio", "labels": []}]
        out = check.run(entries, ["x"], [], P, f.fetch, f.sleep)
        self.assertEqual(out[0]["status"], "invalid")
        self.assertTrue(out[0]["reason"].startswith("rule:"))
        self.assertEqual(f.calls, [])

    def test_duplicate_handles_requested_once(self):
        f = Fake({yt("acmestudio"): [R(200)]})
        entries = [{"input": "Acme Studio", "handle": "acmestudio", "labels": []},
                   {"input": "acmestudio", "handle": "acmestudio", "labels": []}]
        out = check.run(entries, ["youtube"], [], P, f.fetch, f.sleep)
        self.assertEqual(len(out), 2)
        self.assertEqual(f.calls, [yt("acmestudio")])

    def test_domains_included(self):
        boot = {"services": [[["com"], ["https://rdap.test/"]]]}
        f = Fake({check.IANA_BOOTSTRAP: [R(200, json.dumps(boot))],
                  "https://rdap.test/domain/acmestudio.com": [R(404)],
                  "https://rdap.test/domain/acme-studio.com": [R(200)]})
        entries = [{"input": "Acme Studio", "handle": "acmestudio", "labels": ["acmestudio", "acme-studio"]}]
        out = check.run(entries, [], ["com"], P, f.fetch, f.sleep)
        self.assertEqual([(r["platform"], r["handle"], r["status"]) for r in out],
                         [(".com", "acmestudio.com", "available"), (".com", "acme-studio.com", "taken")])
        self.assertEqual(out[0]["input"], "Acme Studio")

    def test_manual_only_sends_no_request(self):
        f = Fake()
        entries = [{"input": "acmestudio", "handle": "acmestudio", "labels": []}]
        out = check.run(entries, ["producthunt"], [], P, f.fetch, f.sleep)
        self.assertEqual((out[0]["status"], out[0]["reason"]), ("unknown", "manual_only"))
        self.assertEqual(f.calls, [])


if __name__ == "__main__":
    unittest.main()
