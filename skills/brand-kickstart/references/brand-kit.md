# Brand kit: logo, illustration, favicons, app icons, banners and covers

Read this only after the user has picked a name and asks for a logo or for images. You draw everything as SVG. `scripts/brand.py` renders it to PNG with resvg: one 2 MB pip package, no browser and no image model. Read `styles.md` next to this file before you draw.

## Draw everything from scratch

- **No emoji, icon fonts, clip-art or stock icons** anywhere: not in the logo, the illustrations, the banners or the text. Draw every shape yourself as SVG `<path>`, `<circle>`, `<rect>` and so on.
- The renderer only uses the fonts in `brand/fonts/`, so an emoji in `<text>` would not render anyway.
- Do not copy or trace another brand's logo, mascot or illustration style.
- Every mark and illustration must come from **this brand's world**: what it sells, where it is, who it is for, or what its name means. A coffee brand called "Morning Brew" gets a cup and a sunrise, not a generic leaf.

## 1. Ask first

Before you draw, learn:
- The **vibe** in 2–3 words, e.g. "warm, homemade" or "dark, mysterious".
- **Colors**: the user's own, or pick from `styles.md`.
- **Which images**: pick from the table in step 6. Only make what they need. TikTok and Instagram have no profile banner. App icons are only for an app.
- **Output folder**, e.g. `brand/` in their project. Never write into the skill folder.

## 2. Folder layout

You write the files marked "you". `brand.py` writes the rest.

```
brand/
  concepts/<id>/logo.svg            you: one folder per style option
  concepts/<id>/illustration.svg    you: a spot illustration for that option
  concepts/<id>/mark.svg            you, optional: the mark with no background, for light merch
  concepts/<id>/logo-flat.svg       you, for a 2.5D or 3D logo: the flat small-size version
  concepts/<id>/wordmark.svg        you, for a text-based logo: the name drawn as the logo
  concepts/<id>/concept.json        you: name, fonts, colors and why
  concepts/<id>.png, all.png        brand.py board: the boards the user picks from
  logo.svg, illustration.svg,       brand.py pick: copied from the chosen concept
  mark.svg, wordmark.svg,
  brand.json, fonts/
  mockups/, palette.png, BRAND.md   brand.py pick: the logo in use, and the brand guide
  app-icon.svg                      you, only for an app: the square icon
  pages/<what>-<W>x<H>.svg          brand.py render writes the standard ones; you add or replace any
  logo/ favicon/ app/ social/       brand.py render (it also refreshes mockups/ and BRAND.md)
```

## 3. Style options for the user to pick

Make **3 style options** (2 if the brief is very narrow, 4 at most). Each one is a complete direction: a logo, an illustration, typefaces and a palette. Follow the variety rules in `styles.md`.

For each option, write `concepts/<id>/` with a short id like `a-warm-kitchen`:

- `logo.svg`: the mark (see step 4).
- `illustration.svg`: a spot illustration (see step 4).
- `concept.json`:

```json
{
  "title": "Warm kitchen",
  "why": "Soft serif, cream and a morning window: feels made at home, not by a chain.",
  "name": "Acme Studio",
  "tagline": "Small batch, every morning.",
  "display": {"family": "Fraunces", "weight": 800},
  "text": {"family": "Nunito", "weight": 400},
  "colors": {"ink": "#2a1d17", "paper": "#f3e6d3", "accent": "#f2a541", "support": "#8c5a3c"}
}
```

`display` and `text` may also have `"style": "italic"`. `display` may also have:
- `"tracking"`: letter-spacing in em, e.g. `0.22` for airy luxury caps or `-0.02` for a tight grotesk
- `"case": "upper"`

Wide tracking on capitals reads as premium. Never track lowercase text wider than `0.05`. Keep `why` to one sentence.

Then download every font the options use, and render the boards:

```bash
python3 <skill-dir>/scripts/brand.py fonts brand "Fraunces:wght@800" "Nunito:wght@400" "Shrikhand" "Rubik:wght@400"
python3 <skill-dir>/scripts/brand.py board brand
```

Each board shows the following:
- the logo with the wordmark, large
- a type specimen
- the profile picture as a circle at 128, 44 and 16 px
- the wordmark and tagline
- the palette
- a mini banner with the illustration

**Look at every board** before you show it. Then give the user the path to `concepts/all.png` and one line per option. Ask them to pick one, or to mix (e.g. "B's logo with A's colors"). Revise and run `board` again until they pick.

When they pick, run `pick` with the option's id, plus the handle and domain from the name check:

```bash
python3 <skill-dir>/scripts/brand.py pick brand a-warm-kitchen --handle acmestudio --domain acmestudio.com
```

It does the following:
- copies the option's SVGs to `brand/` and saves its settings as `brand.json`
- downloads the fonts
- draws `mockups/`: the logo on a website, a social profile, a tote bag, a business card, a T-shirt and a shop window, plus `mockups/all.png`
- writes `palette.png` and **`BRAND.md`**, the brand guide: logo rules, colors with contrast ratios, fonts with links, mockups and every file with where it goes

**Look at `mockups/all.png`** and show it to the user, so they see the logo in real places before you make the rest. If a mockup shows a problem, fix the SVG and run `pick` again. For example, the mark may disappear on the tote bag, or the wordmark may be too long for the sign.

To mix options ("B's mark with A's colors"), make a new concept folder that combines them, run `board`, then `pick` it.

## 4. Logo, illustration and app icon

- **`logo.svg`**: `viewBox="0 0 400 400"`, simple shapes, at most 3–4 colors and no text inside the mark.
  - Build it from one idea in the brief. Pick the mark type from `styles.md`.
  - **It must read at 16 px and 44 px**, and every platform crops it to a **circle**. Keep the mark inside the centre circle (radius about 150 of 400).
  - Give it a solid background shape (e.g. `<rect width="400" height="400" rx="90" fill="..."/>`), so it works on light and dark themes.
- **`illustration.svg`**: a small scene or object from the brand's world, e.g. a window at sunrise with a cup on the sill. Use `viewBox="0 0 380 270"` or another wide box.
  - Use only the palette's colors. Use the same corner radius and stroke weight as the logo, so they look like one family.
  - Use flat shapes in 3–6 layers. Do not use gradients unless the style calls for them. Do not draw outlines thinner than 6 units.
  - It is decoration for banners and covers. It is never a second logo.
- **`logo-flat.svg`**, required for a 2.5D or 3D logo: the same mark in 1–2 flat colors. Favicons and icons under 64 px use it. See "Rendering styles" in `styles.md`.
- **`wordmark.svg`**, for a text-based logo: the name drawn as a logo, wide and with no background. Wherever the name appears next to the logo, `brand.py` uses this drawing instead of typing the name. Follow "Text-based logos" in `styles.md`.
- **`mark.svg`**, optional: the same mark with **no background**, in colors that read on the paper color. The tote bag mockup and printing on light materials use it. Without it, they use `logo.svg` with its background square.
- **`app-icon.svg`**, only for an app: the same mark on a **square, full-bleed** background, with no rounded corners and no transparency. App Store and Play Store round the corners themselves. Keep the mark inside the centre 80%, since Android masks icons to different shapes.

## 5. Pages

`render` writes the standard banners and covers from `brand.json`:
- YouTube banner, Facebook cover, X header and GitHub social preview
- video cover and an Instagram highlight cover

Each one puts the logo, wordmark, tagline, handle and domain inside that platform's safe area, with the illustration fading in beside them. **You only write a page to add a size that is not in this list, such as the Play Store feature graphic, or to replace one.** A file with the same name in `pages/` always wins.

A custom page is one SVG sized exactly to the target, named `<what>-<W>x<H>.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="1640" height="624" viewBox="0 0 1640 624">
  <rect width="1640" height="624" fill="#2a1d17"/>
  <image href="../illustration.svg" x="1100" y="150" width="440" height="312"/>
  <image href="../logo.svg" x="300" y="202" width="220" height="220"/>
  <text x="560" y="320" font-family="Fraunces" font-weight="800" font-size="84" fill="#f3e6d3">Acme Studio</text>
</svg>
```

- Use the chosen option's fonts and colors. The values in this example only show the syntax.
- Place the logo and the illustration with `<image href="../logo.svg">` and `<image href="../illustration.svg">`. Do not paste the SVG inline, so a change updates every page.
- Put the name, tagline and logo inside the **safe area** from the table in step 6. The illustration and other decoration may go outside it.
- `<text>` does not wrap. Use one `<text>` per line.
- Quote a family name that has a word starting with a digit: `font-family="'Baloo 2'"`. Unquoted, the text does not render at all.
- For a custom page, use a banner layout from `styles.md` and the same colors and fonts as `brand.json`.

## 6. Sizes and safe areas

| Image | Made from | Size (px) | Safe area: keep name, tagline and logo inside |
|---|---|---|---|
| Profile picture (all platforms) | `logo.svg`, automatic | 1080 × 1080 | centre circle; platforms crop to a circle |
| Favicons, web app icons | `logo.svg`, automatic | 16–512 | the logo must still read at 16 px |
| App Store icon | `app-icon.svg`, automatic | 1024 × 1024 | square, no alpha (the script removes it); Apple rounds the corners |
| Play Store icon | `app-icon.svg`, automatic | 512 × 512 | square; Google rounds the corners |
| Play Store feature graphic | page | 1024 × 500 | centre; keep text away from the edges |
| YouTube banner | page | 2560 × 1440 | centre 1546 × 423 (x 507–2053, y 508–931); the rest only shows on TV or desktop |
| Facebook Page cover | page | 1640 × 624 | centre ~1110 px wide (x 265–1375); phones crop the sides |
| X header | page | 1500 × 500 | middle band; the profile picture covers the bottom-left corner |
| Instagram highlight cover | page | 1080 × 1920 | centre circle, ~800 px across |
| Video cover (TikTok, Reels, Shorts) | page | 1080 × 1920 | middle 1080 × 1350; the Instagram grid crops the rest |
| GitHub social preview | page | 1280 × 640 | 40 px border |
| Product Hunt thumbnail | page | 240 × 240 | must read at small size, like the profile picture |

Platforms change these. If the user reports a crop, trust what they see.

## 7. Render

```bash
python3 <skill-dir>/scripts/brand.py render brand
```

- It reads the name and the ink color from `brand.json`. The script uses the color in `site.webmanifest` and to fill the App Store icon.
- It also refreshes `mockups/` and `BRAND.md`, so the guide lists every new file.
- It needs `resvg-py`. If the script says so, **ask before installing**, then follow step 9 in SKILL.md.
- **Look at every PNG** before you show it. Check these:
  - Text shows in the chosen font. Missing text means its font is not in `fonts/`.
  - No text is cut.
  - Nothing important sits outside the safe area.

## 8. Hand over

- Point the user to **`BRAND.md`**. It has the logo, palette, fonts, mockups and a table of every file with where to upload it. Keep the folder together, since the guide links its images by relative path.
- Show `mockups/all.png` again next to the final banners.
- Tell the user they can change a color or the tagline in `brand.json` and run `render` again. Standard pages are redrawn; custom pages are kept.
