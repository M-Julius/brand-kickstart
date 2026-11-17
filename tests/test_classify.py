import json
import unittest

from _load import FIXTURES, check

P = check.load_platforms()


SAME_HOST = None  # sentinel: the response came from the requested URL (no redirect)


def R(status, body, url=SAME_HOST, headers=None):
    return check.Response(status=status, body=body, url=url, headers=headers or {})


def classify(platform, resp):
    if resp.url is SAME_HOST:
        resp.url = platform.get("url", "https://none.test/").format(name="x")
    return check.classify(platform, resp)


def fixture(path):
    meta = json.loads(path.with_name(path.name + ".meta.json").read_text(encoding="utf-8"))
    return R(meta["status"], path.read_text(encoding="utf-8"), meta["url"], meta["headers"])


class ClassifyTest(unittest.TestCase):
    def test_fixtures_classify(self):
        files = [f for f in FIXTURES.iterdir() if not f.name.endswith(".meta.json")]
        self.assertGreaterEqual(len(files), 14)
        for f in files:
            key, want = f.stem.rsplit("_", 1)
            free = ("unknown", "likely_free") if P[key]["check"].get("available_unconfirmed") else ("available", None)
            expected = ("taken", None) if want == "taken" else free
            with self.subTest(fixture=f.name):
                self.assertEqual(classify(P[key], fixture(f)), expected)

    def test_rate_limit_statuses(self):
        for code in (429, 503):
            self.assertEqual(classify(P["youtube"], R(code, "")), ("unknown", "rate_limited"))

    def test_server_error(self):
        for code in (500, 502, 504):
            self.assertEqual(classify(P["x"], R(code, '{"errors":[{"code":131}]}')), ("unknown", "server_error"))

    def test_blocked(self):
        self.assertEqual(classify(P["youtube"], R(403, "")), ("unknown", "blocked"))
        login = R(200, "<html>", url="https://www.instagram.com/accounts/login/?next=x")
        self.assertEqual(classify(P["instagram"], login), ("unknown", "login_wall"))

    def test_sandbox_proxy_403(self):
        proxy = R(403, "Host not in allowlist")
        self.assertEqual(classify(P["youtube"], proxy), ("unknown", "sandbox_blocked"))

    def test_body_without_any_marker_is_unknown(self):
        self.assertEqual(classify(P["instagram"], R(200, "<html></html>")),
                         ("unknown", "unexpected_response"))

    def test_json_unknown_reason(self):
        self.assertEqual(classify(P["x"], R(200, '{"reason":"something_new"}')),
                         ("unknown", "unexpected_response"))
        self.assertEqual(classify(P["x"], R(200, "not json")), ("unknown", "unexpected_response"))

    def test_json_invalid_reason_uses_platform_message(self):
        body = '{"valid":false,"reason":"is_banned_word","desc":"This username is not allowed."}'
        self.assertEqual(classify(P["x"], R(200, body)),
                         ("invalid", "rule:This username is not allowed."))

    def test_network_error(self):
        self.assertEqual(classify(P["tiktok"], R(0, "timed out")), ("unknown", "network_error"))

    def test_manual_only(self):
        self.assertEqual(classify(P["producthunt"], R(0, "")), ("unknown", "manual_only"))


class FetchTest(unittest.TestCase):
    def test_user_agent_header(self):
        sent = []

        class Resp:
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b"ok"
            def geturl(self): return "https://www.instagram.com/x/"

        def urlopen(req, timeout):
            sent.append(req.get_header("User-agent"))
            return Resp()
        real = check.urllib.request.urlopen
        check.urllib.request.urlopen = urlopen
        try:
            check.fetch("https://www.instagram.com/x/", user_agent=check.PLAIN_UA)
            check.fetch("https://www.youtube.com/@x")
        finally:
            check.urllib.request.urlopen = real
        self.assertEqual(sent, [check.PLAIN_UA, check.HEADERS["User-Agent"]])
        self.assertNotIn("Chrome", check.PLAIN_UA)  # a fake browser UA gets Instagram's error page

    def test_network_error_is_status_zero(self):
        r = check.fetch("http://127.0.0.1:9/", timeout=2)
        self.assertEqual(r.status, 0)


if __name__ == "__main__":
    unittest.main()
