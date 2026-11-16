import json
import os
import struct
import tempfile
import unittest
import zlib

from _load import FIXTURES  # noqa: F401  (adds scripts dir to sys.path)
import brand

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#123"/></svg>'


def png(w, h, rows, filt=0, color_type=6):
    """Tiny PNG encoder for tests; rows are lists of pixel tuples."""
    raw = b"".join(bytes([filt]) + bytes(c for px in row for c in px) for row in rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class PageSizeTest(unittest.TestCase):
    def test_size_from_file_name(self):
        self.assertEqual(brand.page_size("youtube-banner-2560x1440.svg"), (2560, 1440))
        self.assertEqual(brand.page_size("play-feature-graphic-1024x500.svg"), (1024, 500))

    def test_name_without_size_is_none(self):
        self.assertIsNone(brand.page_size("draft.svg"))
        self.assertIsNone(brand.page_size("concepts-0x10.svg"))


class IcoTest(unittest.TestCase):
    def test_ico_embeds_pngs(self):
        a, b = b"\x89PNGaaaa", b"\x89PNGbbbbb"
        data = brand.ico_bytes([(16, a), (256, b)])
        self.assertEqual(struct.unpack("<HHH", data[:6]), (0, 1, 2))
        w, h, _, _, planes, bpp, size, offset = struct.unpack("<BBBBHHII", data[6:22])
        self.assertEqual((w, h, planes, bpp, size, offset), (16, 16, 1, 32, len(a), 6 + 2 * 16))
        self.assertEqual(data[offset:offset + size], a)
        w2, _, _, _, _, _, size2, offset2 = struct.unpack("<BBBBHHII", data[22:38])
        self.assertEqual(w2, 0)  # 256 is stored as 0
        self.assertEqual(data[offset2:offset2 + size2], b)


class StripAlphaTest(unittest.TestCase):
    def decode(self, data):
        w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
        idat, pos = b"", 8
        while pos < len(data):
            n, t = struct.unpack(">I4s", data[pos:pos + 8])
            if t == b"IDAT":
                idat += data[pos + 8:pos + 8 + n]
            pos += 12 + n
        raw = zlib.decompress(idat)
        return w, h, ctype, raw

    def test_rgba_becomes_rgb_on_background(self):
        rows = [[(255, 0, 0, 255), (0, 0, 255, 0)], [(0, 255, 0, 128), (10, 20, 30, 255)]]
        for filt in range(5):  # every PNG filter type must decode
            with self.subTest(filt=filt):
                w, h, ctype, raw = self.decode(brand.strip_alpha(png(2, 2, rows, filt), (255, 255, 255)))
                self.assertEqual((w, h, ctype), (2, 2, 2))
                if filt == 0:
                    self.assertEqual(raw, b"\x00" + bytes([255, 0, 0, 255, 255, 255])
                                     + b"\x00" + bytes([127, 255, 127, 10, 20, 30]))


class FilterRoundTripTest(unittest.TestCase):
    def test_unfilter_all_types(self):
        prev = bytes([10, 20, 30, 40, 50, 60, 70, 80])
        cur = bytes([200, 100, 50, 25, 12, 6, 3, 1])
        for ftype in range(5):
            with self.subTest(ftype=ftype):
                enc = brand._filter_row(ftype, cur, prev, 4)
                self.assertEqual(brand._unfilter_row(ftype, enc, prev, 4), cur)


class FontsTest(unittest.TestCase):
    def test_downloads_ttf_from_google_css(self):
        css = ("@font-face { src: url(https://fonts.gstatic.com/s/a/v1/AAA.ttf) format('truetype'); }\n"
               "@font-face { src: url(https://fonts.gstatic.com/s/b/v1/BBB.ttf) format('truetype'); }")
        seen = []

        def fetch(url):
            seen.append(url)
            return css.encode() if "googleapis" in url else b"TTF"
        with tempfile.TemporaryDirectory() as d:
            files = brand.download_fonts(d, ["Plus Jakarta Sans:wght@800", "Playfair Display"], fetch)
            self.assertEqual(sorted(os.listdir(os.path.join(d, "fonts"))), ["AAA.ttf", "BBB.ttf"])
        self.assertEqual(len(files), 2)
        self.assertIn("family=Plus+Jakarta+Sans:wght@800&family=Playfair+Display", seen[0])

    def test_no_ttf_raises(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(RuntimeError):
            brand.download_fonts(d, ["Nope"], lambda url: b"")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        with open(os.path.join(self.dir, "logo.svg"), "w") as f:
            f.write(SVG)
        os.mkdir(os.path.join(self.dir, "pages"))
        for name in ("facebook-cover-1640x624.svg", "notes.svg"):
            with open(os.path.join(self.dir, "pages", name), "w") as f:
                f.write(SVG)
        self.calls = []

        def render(path, w, h):
            self.calls.append((os.path.relpath(path, self.dir), w, h))
            return png(1, 1, [[(1, 2, 3, 255)]])
        self.render = render

    def files(self):
        return sorted(os.path.relpath(os.path.join(r, f), self.dir)
                      for r, _, fs in os.walk(self.dir) for f in fs if not r.endswith("pages"))

    def test_output_layout(self):
        skipped = brand.build(self.dir, "Seduh Pagi", "#13161d", self.render)
        self.assertEqual(self.files(), sorted([
            "logo.svg", "logo/logo-1080.png", "logo/logo-512.png",
            "favicon/favicon.svg", "favicon/favicon.ico", "favicon/favicon-16.png", "favicon/favicon-32.png",
            "favicon/apple-touch-icon.png", "favicon/icon-192.png", "favicon/icon-512.png",
            "favicon/site.webmanifest", "favicon/head.html",
            "social/facebook-cover-1640x624.png"]))
        self.assertEqual(skipped, ["notes.svg"])
        self.assertIn(("pages/facebook-cover-1640x624.svg", 1640, 624), self.calls)

    def test_app_icons_when_app_icon_svg_exists(self):
        with open(os.path.join(self.dir, "app-icon.svg"), "w") as f:
            f.write(SVG)
        brand.build(self.dir, "Seduh Pagi", "#13161d", self.render)
        self.assertIn("app/app-store-1024.png", self.files())
        self.assertIn("app/play-store-512.png", self.files())
        self.assertIn(("app-icon.svg", 180, 180), self.calls)  # apple-touch-icon uses the square icon
        with open(os.path.join(self.dir, "app", "app-store-1024.png"), "rb") as f:
            self.assertEqual(f.read()[25], 2)  # RGB, no alpha channel

    def test_manifest(self):
        brand.build(self.dir, "Seduh Pagi", "#13161d", self.render)
        with open(os.path.join(self.dir, "favicon", "site.webmanifest")) as f:
            m = json.load(f)
        self.assertEqual(m["name"], "Seduh Pagi")
        self.assertEqual(m["theme_color"], "#13161d")
        self.assertEqual([i["sizes"] for i in m["icons"]], ["192x192", "512x512"])

    def test_missing_logo_raises(self):
        os.remove(os.path.join(self.dir, "logo.svg"))
        with self.assertRaises(FileNotFoundError):
            brand.build(self.dir, "x", None, self.render)


if __name__ == "__main__":
    unittest.main()


CONCEPT = {"title": "Warm & homemade", "why": "Soft serif and cream, so it feels like a kitchen, not a chain store.",
           "name": "Seduh <Pagi>", "tagline": "Kopi susu, diseduh tiap pagi.",
           "display": {"family": "Fraunces", "weight": 800}, "text": {"family": "Nunito", "weight": 400},
           "colors": {"ink": "#2a1d17", "paper": "#f3e6d3", "accent": "#f2a541", "support": "#8c5a3c"}}


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        for cid in ("a-warm", "b-bold"):
            d = os.path.join(self.dir, "concepts", cid)
            os.makedirs(d)
            with open(os.path.join(d, "logo.svg"), "w") as f:
                f.write(SVG)
            with open(os.path.join(d, "concept.json"), "w") as f:
                json.dump(CONCEPT, f)
        with open(os.path.join(self.dir, "concepts", "a-warm", "illustration.svg"), "w") as f:
            f.write(SVG)
        self.calls = []

        def render(path, w, h):
            self.calls.append((os.path.relpath(path, self.dir), w, h))
            return png(1, 1, [[(1, 2, 3, 255)]])
        self.render = render

    def test_board_per_concept_and_overview(self):
        out = brand.build_boards(self.dir, self.render)
        rel = sorted(os.path.relpath(p, self.dir) for p in out)
        self.assertEqual(rel, ["concepts/a-warm.png", "concepts/all.png", "concepts/b-bold.png"])
        with open(os.path.join(self.dir, "concepts", "a-warm", "board.svg")) as f:
            svg = f.read()
        self.assertIn("Seduh &lt;Pagi&gt;", svg)           # user text is escaped
        self.assertIn('font-family="&#x27;Fraunces&#x27;"', svg)  # quoted, so "Baloo 2" is valid CSS
        self.assertIn("#f2a541", svg)
        self.assertIn('href="illustration.svg"', svg)
        self.assertIn('href="logo.svg"', svg)
        with open(os.path.join(self.dir, "concepts", "b-bold", "board.svg")) as f:
            self.assertNotIn("illustration.svg", f.read())
        with open(os.path.join(self.dir, "concepts", "all.svg")) as f:
            self.assertIn('href="a-warm.png"', f.read())  # tiles the rendered boards, not nested SVGs

    def test_missing_field_names_it(self):
        bad = dict(CONCEPT)
        del bad["colors"]
        with open(os.path.join(self.dir, "concepts", "b-bold", "concept.json"), "w") as f:
            json.dump(bad, f)
        with self.assertRaisesRegex(ValueError, "b-bold.*colors"):
            brand.build_boards(self.dir, self.render)

    def test_no_concepts_raises(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(FileNotFoundError):
            brand.build_boards(d, self.render)

    def test_wordmark_tracking_and_case(self):
        c = dict(CONCEPT, display={"family": "Jost", "weight": 500, "tracking": 0.2, "case": "upper"})
        svg = brand.board_svg("a", c, False)
        self.assertIn("SEDUH &lt;PAGI&gt;", svg)
        self.assertIn('letter-spacing="', svg)
        self.assertIn("Aa", svg)                     # type specimen

    def test_label_color_follows_luminance(self):
        self.assertEqual(brand.on_color("#111111"), "#ffffff")
        self.assertEqual(brand.on_color("#f3e6d3"), "#111111")

    def test_wrap(self):
        self.assertEqual(brand.wrap("aa bb cc dd", 5), ["aa bb", "cc dd"])
        self.assertEqual(brand.wrap("", 5), [])


class OverviewLayoutTest(unittest.TestCase):
    def test_odd_last_tile_is_centered(self):
        self.assertEqual([brand.tile_xy(i, 3) for i in range(3)], [(0, 0), (800, 0), (400, 500)])
        self.assertEqual(brand.tile_xy(3, 4), (800, 500))
        self.assertEqual(brand.tile_xy(0, 1), (400, 0))


class FlatLogoTest(unittest.TestCase):
    def test_small_icons_use_logo_flat_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("logo.svg", "logo-flat.svg"):
                with open(os.path.join(d, name), "w") as f:
                    f.write(SVG.replace("#123", "#456" if name == "logo-flat.svg" else "#123"))
            calls = []

            def render(path, w, h):
                calls.append((os.path.basename(path), w))
                return png(1, 1, [[(1, 2, 3, 255)]])
            brand.build(d, "x", None, render)
            by_size = {}
            for name, w in calls:
                by_size.setdefault(w, set()).add(name)
            for small in (16, 32, 48):
                self.assertEqual(by_size[small], {"logo-flat.svg"}, small)
            self.assertEqual(by_size[1080], {"logo.svg"})
            with open(os.path.join(d, "favicon", "favicon.svg")) as f:
                self.assertIn("#456", f.read())   # the SVG favicon is small too


WORDMARK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 150">'
            '<text x="0" y="120" font-family="Jost" fill="currentColor">kita</text><circle cx="580" cy="30" r="12" fill="#e4572e"/></svg>')


class WordmarkTest(unittest.TestCase):
    def test_drawn_wordmark_replaces_typed_name_and_takes_text_color(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "wordmark.svg"), "w") as f:
                f.write(WORDMARK)
            disp = {"family": "Jost", "_logotype": brand.load_logotype(os.path.join(d, "wordmark.svg"))}
        out = brand._wordmark(disp, "Kita", 100, "#fff", 500, 300)
        self.assertIn('fill="#fff"', out)          # currentColor becomes the spot's text color
        self.assertIn('fill="#e4572e"', out)       # fixed accent stays
        self.assertIn('x="260.0" y="205.0" width="480.0" height="120.0"', out)  # centred, 4:1 at 1.2 x size
        self.assertNotIn(">Kita<", out)
        self.assertEqual(brand._fit(disp, "Kita", 240, 100), 50)   # fits by the drawing's width, not char count

    def test_no_viewbox_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wordmark.svg")
            with open(path, "w") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
            with self.assertRaisesRegex(ValueError, "viewBox"):
                brand.load_logotype(path)
            self.assertIsNone(brand.load_logotype(os.path.join(d, "missing.svg")))
