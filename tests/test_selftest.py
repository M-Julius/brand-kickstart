import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _load import FIXTURES, check

P = check.load_platforms()


def fixture(key, which):
    path = next(f for f in FIXTURES.glob(f"{key}_{which}.*") if not f.name.endswith(".meta.json"))
    meta = json.loads(path.with_name(path.name + ".meta.json").read_text(encoding="utf-8"))
    return check.Response(meta["status"], path.read_text(encoding="utf-8"), meta["url"], meta["headers"])


def fixture_fetch(overrides=None):
    table = {}
    for key, p in P.items():
        if "canary" in p:
            table[p["url"].format(name=p["canary"]["taken"])] = fixture(key, "taken")
            table[p["url"].format(name=p["canary"]["available"])] = fixture(key, "free")
    table.update(overrides or {})

    def fetch(url, **kw):
        return table[url]

    return fetch


def states(results):
    return {r["platform"]: r["state"] for r in results}


class SelfTest(unittest.TestCase):
    def test_all_ok_from_fixtures(self):
        got = states(check.self_test(P, fixture_fetch(), lambda s: None))
        for key, p in P.items():
            want = "skipped" if p["check"]["type"] in ("manual_only", "same_as") else "ok"
            self.assertEqual(got[key], want, key)

    def test_broken_detected(self):
        yt_free = P["youtube"]["url"].format(name=P["youtube"]["canary"]["available"])
        fetch = fixture_fetch({yt_free: fixture("youtube", "taken")})
        got = check.self_test(P, fetch, lambda s: None)
        self.assertEqual(states(got)["youtube"], "broken")
        with mock.patch.object(check, "fetch", fetch), mock.patch.object(check.time, "sleep", lambda s: None):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(["--self-test"]), 1)

    def test_blocked_is_not_broken(self):
        ig_canary = P["instagram"]["url"].format(name=P["instagram"]["canary"]["taken"])
        fetch = fixture_fetch({ig_canary: check.Response(403, "", ig_canary)})
        self.assertEqual(states(check.self_test(P, fetch, lambda s: None))["instagram"], "blocked")
        with mock.patch.object(check, "fetch", fetch), mock.patch.object(check.time, "sleep", lambda s: None):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(check.main(["--self-test"]), 0)
            self.assertIn("blocked", out.getvalue())


if __name__ == "__main__":
    unittest.main()
