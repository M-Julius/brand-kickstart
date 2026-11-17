import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _load import check

P = check.load_platforms()


def res(inp, handle, platform, status, reason=None, url=None):
    return {"input": inp, "handle": handle, "platform": platform, "status": status,
            "reason": reason, "url": url or f"https://{platform}.test/{handle}"}


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "config.json")
        patcher = mock.patch.dict(os.environ, {"BRAND_KICKSTART_CONFIG": self.cfg})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.calls = []

        def fake_run(entries, keys, tlds, platforms, *a, **kw):
            self.calls.append({"entries": entries, "keys": keys, "tlds": tlds})
            return [res(e["input"], e["handle"], k, "available") for e in entries for k in keys]

        run_patch = mock.patch.object(check, "run", fake_run)
        run_patch.start()
        self.addCleanup(run_patch.stop)

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = check.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_select_modes(self):
        self.assertEqual(check.select_platforms(P, "brand", None, []),
                         ["instagram", "threads", "facebook", "tiktok", "youtube", "x"])
        self.assertEqual(check.select_platforms(P, "project", None, ["x"]),
                         ["github", "npm", "pypi", "producthunt"])
        self.assertEqual(len(check.select_platforms(P, "all", None, [])), len(P))
        self.assertEqual(check.select_platforms(P, "brand", ["ig", "yt"], []), ["instagram", "youtube"])

    def test_select_unknown_key_exits_2(self):
        self.assertEqual(self.main("a", "--skip", "myspace")[0], 2)
        self.assertEqual(self.main("a", "--mode", "nope")[0], 2)
        self.assertEqual(self.main("!!!")[0], 2)
        self.assertEqual(self.main()[0], 2)

    def test_config_merge(self):
        with open(self.cfg, "w") as f:
            json.dump({"tlds": ["com", "id"], "skip": ["x"]}, f)
        self.main("acmestudio", "--tlds", ".co", "--json")
        self.assertEqual(self.calls[0]["tlds"], ["co"])
        self.assertNotIn("x", self.calls[0]["keys"])

    def test_bad_config_warns_and_continues(self):
        with open(self.cfg, "w") as f:
            f.write("{oops")
        code, _, err = self.main("acmestudio", "--json")
        self.assertEqual(code, 0)
        self.assertIn("config", err.lower())

    def test_display_name_kept(self):
        code, out, _ = self.main("Acme Studio", "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["results"][0]["input"], "Acme Studio")
        self.assertEqual(data["results"][0]["handle"], "acmestudio")
        self.assertEqual(self.calls[0]["entries"][0]["labels"], ["acmestudio", "acme-studio"])

    def test_dotted_handle_domain_labels(self):
        self.main("acmestudio.id", "--json")
        e = self.calls[0]["entries"][0]
        self.assertEqual((e["handle"], e["labels"]), ("acmestudio.id", ["acmestudioid", "acmestudio-id"]))

    def test_no_domains(self):
        self.main("acmestudio", "--no-domains", "--json")
        self.assertEqual(self.calls[0]["tlds"], [])

    def test_variants_flag_expands(self):
        self.main("acme studio", "--variants", "--json")
        handles = [e["handle"] for e in self.calls[0]["entries"]]
        self.assertEqual(handles, check.variants(["acme", "studio"], "brand", None))
        labelled = [e for e in self.calls[0]["entries"] if e["labels"]]
        self.assertEqual(len(labelled), 1)

    def test_markdown_hints(self):
        results = [res("a", "a", "youtube", "unknown", "rate_limited"),
                   res("b", "b", "youtube", "unknown", "rate_limited")]
        md = check.render_markdown(results, ["instagram", "youtube"], [], P)
        self.assertEqual(md.count("YouTube limited"), 1)
        self.assertIn("https://youtube.test/a", md)

    def test_sandbox_hint_replaces_per_platform_hints(self):
        results = [res("a", "a", k, "unknown", "blocked") for k in ("instagram", "youtube", "x")]
        results.append(res("a", "a", "npm", "available"))
        hints = check._hints(results, ["instagram", "youtube", "x", "npm"], P)
        self.assertEqual(len(hints), 1)
        self.assertIn("could not be reached from this network", hints[0])
        self.assertNotIn("npm", hints[0])

    def test_markdown_order(self):
        results = [res("a", "aaa", "youtube", "taken"), res("a", "aaa", "x", "available"),
                   res("b", "bbb", "youtube", "available"), res("b", "bbb", "x", "available"),
                   res("b", "bbb", "producthunt", "unknown", "manual_only")]
        md = check.render_markdown(results, ["youtube", "x", "producthunt"], [], P)
        header = md.splitlines()[0]
        self.assertLess(header.index("bbb"), header.index("aaa"))  # all-free name is the first column

    def test_markdown_domain_cells(self):
        results = [res("Acme Studio", "acmestudio", "youtube", "taken"),
                   res("Acme Studio", "acmestudio.com", ".com", "available"),
                   res("Acme Studio", "acme-studio.com", ".com", "taken")]
        md = check.render_markdown(results, ["youtube"], ["com"], P)
        cells = lambda label: [c.strip() for c in next(  # noqa: E731
            l for l in md.splitlines() if l.startswith(f"| {label} ")).strip("|").split("|")]
        self.assertEqual(cells("Platform"), ["Platform", "acmestudio"])
        self.assertEqual(cells("Display"), ["Display", "Acme Studio"])
        self.assertEqual(cells("YouTube"), ["YouTube", "❌"])
        self.assertEqual(cells(".com"), [".com", "✅ / ❌"])


if __name__ == "__main__":
    unittest.main()


class TableLayoutTest(unittest.TestCase):
    def test_columns_aligned_in_terminal(self):
        results = [res("Acme Studio", "acmestudio", "youtube", "taken"),
                   res("Acme Studio", "acmestudio.com", ".com", "available"),
                   res("Acme Studio", "acme-studio.com", ".com", "unknown", "no_rdap"),
                   res("seduhpagi", "seduhpagi", "youtube", "available"),
                   res("seduhpagi", "seduhpagi.com", ".com", "available")]
        md = check.render_markdown(results, ["youtube"], ["com"], P)
        table = [line for line in md.splitlines() if line.startswith("|")]
        widths = {check.display_width(line) for line in table}
        self.assertEqual(len(widths), 1, "\n".join(table))
        def pipe_columns(line):  # terminal column of every "|"
            cols, x = [], 0
            for ch in line:
                if ch == "|":
                    cols.append(x)
                x += check.display_width(ch)
            return tuple(cols)

        self.assertEqual(len({pipe_columns(line) for line in table}), 1, "\n".join(table))

    def test_display_width_counts_emoji_as_two(self):
        self.assertEqual(check.display_width("✅"), 2)
        self.assertEqual(check.display_width("ab"), 2)
        self.assertEqual(check.display_width("✅ / ❓"), 7)



class VerticalTableTest(unittest.TestCase):
    def test_platforms_are_rows_and_names_centered(self):
        results = [res("Acme Studio", "acmestudio", "youtube", "taken"),
                   res("Acme Studio", "acmestudio", "x", "available"),
                   res("Acme Studio", "acmestudio.com", ".com", "available"),
                   res("Acme Studio", "acme-studio.com", ".com", "taken"),
                   res("Seduh Pagi", "seduhpagi", "youtube", "available"),
                   res("Seduh Pagi", "seduhpagi", "x", "available"),
                   res("Seduh Pagi", "seduhpagi.com", ".com", "available")]
        md = check.render_markdown(results, ["youtube", "x"], ["com"], P)
        table = [line for line in md.splitlines() if line.startswith("|")]
        self.assertEqual([l.split("|")[1].strip() for l in table],
                         ["Platform", "-" * len(table[1].split("|")[1]), "Display", "YouTube", "X", ".com"])
        sep = table[1].split("|")[2:-1]
        self.assertTrue(all(c.startswith(":") and c.endswith(":") for c in sep), sep)
        for line in table[3:]:
            for cell in line.split("|")[2:-1]:
                left, right = len(cell) - len(cell.lstrip(" ")), len(cell) - len(cell.rstrip(" "))
                self.assertGreaterEqual(min(left, right), 2, repr(cell))
                self.assertLessEqual(abs(left - right), 1, repr(cell))


class ManualOnlyDisplayTest(unittest.TestCase):
    def test_product_hunt_is_a_link_not_unknown(self):
        results = [res("acmestudio", "acmestudio", "github", "available"),
                   res("acmestudio", "acmestudio", "npm", "unknown", "network_error"),
                   res("acmestudio", "acmestudio", "producthunt", "unknown", "manual_only",
                       url="https://www.producthunt.com/products/acmestudio")]
        md = check.render_markdown(results, ["github", "npm", "producthunt"], [], P)
        ph_row = next(l for l in md.splitlines() if l.startswith("| Product Hunt"))
        self.assertIn("🔗", ph_row)
        self.assertNotIn("❓", ph_row)
        manual, yourself = md.split("Check manually:")[1].split("🔗 Check yourself")
        self.assertNotIn("producthunt.com", manual)          # not mixed with real failures
        self.assertIn("npm", manual)
        self.assertIn("https://www.producthunt.com/products/acmestudio", yourself)
