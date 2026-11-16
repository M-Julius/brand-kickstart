"""pick -> brand.json, mockups, palette and BRAND.md (no network: fonts and rendering are faked)."""
import json
import os
import tempfile
import unittest

from _load import FIXTURES  # noqa: F401  (adds scripts dir to sys.path)
import brand
from test_brand import CONCEPT, SVG, png


def fake_fetch(url):
    if "googleapis" in url:
        return b"src: url(https://fonts.gstatic.com/s/x/v1/Font.ttf)"
    return b"TTF"


class KitBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        src = os.path.join(self.dir, "concepts", "a-warm")
        os.makedirs(src)
        for name in ("logo.svg", "illustration.svg"):
            with open(os.path.join(src, name), "w") as f:
                f.write(SVG)
        with open(os.path.join(src, "concept.json"), "w") as f:
            json.dump(CONCEPT, f)
        self.calls = []

        def render(path, w, h):
            self.calls.append((os.path.relpath(path, self.dir), w, h))
            return png(1, 1, [[(1, 2, 3, 255)]])
        self.render = render

    def read(self, rel):
        with open(os.path.join(self.dir, rel), encoding="utf-8") as f:
            return f.read()


class PickTest(KitBase):
    def test_pick_copies_writes_brand_json_and_fonts(self):
        brand.pick(self.dir, "a-warm", self.render, fake_fetch, handle="seduhpagi", domain="seduhpagi.id")
        for rel in ("logo.svg", "illustration.svg", "brand.json", "fonts/Font.ttf"):
            self.assertTrue(os.path.exists(os.path.join(self.dir, rel)), rel)
        data = json.loads(self.read("brand.json"))
        self.assertEqual((data["concept"], data["handle"], data["domain"]), ("a-warm", "seduhpagi", "seduhpagi.id"))
        self.assertEqual(data["colors"], CONCEPT["colors"])

    def test_unknown_concept_raises(self):
        with self.assertRaises(FileNotFoundError):
            brand.pick(self.dir, "z-nope", self.render, fake_fetch)

    def test_font_spec(self):
        self.assertEqual(brand.font_spec({"family": "Fraunces", "weight": 600}), "Fraunces:wght@600")
        self.assertEqual(brand.font_spec({"family": "Lora", "weight": 500, "style": "italic"}), "Lora:ital,wght@1,500")
        self.assertEqual(brand.font_spec({"family": "Anton"}), "Anton:wght@400")


class MockupTest(KitBase):
    def setUp(self):
        super().setUp()
        brand.pick(self.dir, "a-warm", self.render, fake_fetch, handle="seduhpagi")

    def test_six_mockups_and_overview(self):
        names = sorted(os.listdir(os.path.join(self.dir, "mockups")))
        for m in brand.MOCKUPS:
            self.assertIn(f"{m}.png", names)
            self.assertIn(f"{m}.svg", names)
        self.assertIn("all.png", names)
        tote = self.read("mockups/tote-bag.svg")
        self.assertIn("Seduh &lt;Pagi&gt;", tote)         # escaped
        self.assertIn(CONCEPT["colors"]["accent"], self.read("mockups/website.svg"))
        self.assertIn('href="../logo.svg"', tote)          # no mark.svg: falls back to the logo
        self.assertIn("@seduhpagi", self.read("mockups/social-profile.svg"))

    def test_mark_svg_preferred_for_merch(self):
        with open(os.path.join(self.dir, "mark.svg"), "w") as f:
            f.write(SVG)
        brand.build_mockups(self.dir, self.render)
        self.assertIn('href="../mark.svg"', self.read("mockups/tote-bag.svg"))


class BrandMdTest(KitBase):
    def setUp(self):
        super().setUp()
        brand.pick(self.dir, "a-warm", self.render, fake_fetch, handle="seduhpagi", domain="seduhpagi.id")
        self.md = self.read("BRAND.md")

    def test_sections(self):
        for text in ("# Seduh <Pagi>", CONCEPT["tagline"], "## Logo", "## Colors", "## Typography",
                     "## Mockups", "mockups/all.png", "palette.png", "#2a1d17",
                     "https://fonts.google.com/specimen/Fraunces", "@seduhpagi", "seduhpagi.id"):
            self.assertIn(text, self.md)

    def test_contrast_reported(self):
        ratio = brand.contrast_ratio(CONCEPT["colors"]["ink"], CONCEPT["colors"]["paper"])
        self.assertIn(f"{ratio:.1f}:1", self.md)
        self.assertAlmostEqual(brand.contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_files_section_lists_only_existing(self):
        self.assertNotIn("youtube-banner", self.md)
        os.makedirs(os.path.join(self.dir, "social"))
        open(os.path.join(self.dir, "social", "youtube-banner-2560x1440.png"), "wb").close()
        brand.write_brand_md(self.dir)
        md = self.read("BRAND.md")
        self.assertIn("social/youtube-banner-2560x1440.png", md)
        self.assertIn("YouTube", md)


class RenderDefaultsTest(KitBase):
    def test_render_reads_name_and_color_from_brand_json(self):
        brand.pick(self.dir, "a-warm", self.render, fake_fetch)
        self.assertEqual(brand.kit_defaults(self.dir), (CONCEPT["name"], CONCEPT["colors"]["ink"]))
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(brand.kit_defaults(empty), (None, None))


if __name__ == "__main__":
    unittest.main()


class DefaultPagesTest(KitBase):
    def setUp(self):
        super().setUp()
        brand.pick(self.dir, "a-warm", self.render, fake_fetch, handle="seduhpagi", domain="seduhpagi.id")

    def test_writes_standard_pages(self):
        written = brand.default_pages(self.dir)
        names = sorted(os.listdir(os.path.join(self.dir, "pages")))
        for want in ("youtube-banner-2560x1440.svg", "facebook-cover-1640x624.svg", "x-header-1500x500.svg",
                     "video-cover-1080x1920.svg", "ig-highlight-1080x1920.svg", "github-social-preview-1280x640.svg"):
            self.assertIn(want, names)
        self.assertEqual(len(written), len(names))
        yt = self.read("pages/youtube-banner-2560x1440.svg")
        self.assertIn("Seduh &lt;Pagi&gt;", yt)
        self.assertIn('href="../illustration.svg"', yt)
        self.assertIn("@seduhpagi", yt)

    def test_custom_page_wins(self):
        os.makedirs(os.path.join(self.dir, "pages"), exist_ok=True)
        with open(os.path.join(self.dir, "pages", "x-header-1500x500.svg"), "w") as f:
            f.write("<svg/>")
        written = brand.default_pages(self.dir)
        self.assertNotIn(os.path.join(self.dir, "pages", "x-header-1500x500.svg"), written)
        self.assertEqual(self.read("pages/x-header-1500x500.svg"), "<svg/>")

    def test_lockup_inside_youtube_safe_area(self):
        # every text and logo x position in the banner lockup sits inside x 507..2053
        import re
        brand.default_pages(self.dir)
        yt = self.read("pages/youtube-banner-2560x1440.svg")
        lock = yt[yt.index("<!--lockup-->"):yt.index("<!--/lockup-->")]
        xs = [float(x) for x in re.findall(r' x="([\d.]+)"', lock)]
        self.assertTrue(xs and all(507 <= x <= 2053 for x in xs), xs)


class AutoPagesRefreshTest(KitBase):
    def test_generated_pages_follow_brand_json(self):
        brand.pick(self.dir, "a-warm", self.render, fake_fetch)
        brand.default_pages(self.dir)
        path = os.path.join(self.dir, "brand.json")
        with open(path) as f:
            data = json.load(f)
        data["colors"]["ink"] = "#000001"
        with open(path, "w") as f:
            json.dump(data, f)
        self.assertEqual(len(brand.default_pages(self.dir)), len(brand.STANDARD_PAGES))
        self.assertIn("#000001", self.read("pages/x-header-1500x500.svg"))
