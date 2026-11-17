# Style reference: fonts, palettes, marks and layouts

Use this together with `brand-kit.md`. It is a menu, not a house style. Pick what fits the brief, and make each concept look like a different brand.

## Variety rules

- Show **3 style options** that differ on at least **two** of these: mark type, typeface category and palette. Three versions of "icon + bold sans + orange" is one option, not three.
- Do not default to the examples in `brand-kit.md`. The fonts there are only there to show the syntax.
- Match the brief before taste. A kids' snack brand gets rounded type, a law firm gets a serif, a dev tool can go mono.
- Give each option a one-line `why` in its `concept.json`, e.g. "Rounded type and a cream palette, so it feels homemade."

## Typefaces by vibe

Every spec below is checked against Google Fonts. Pass it to `brand.py fonts` exactly as written. Pair one **display** face (name, headings) with one **text** face (tagline, small text). Specs without weights have a single weight.

| Vibe | Display | Text | Notes |
|---|---|---|---|
| Warm, homemade, food | `Fraunces:wght@600;800` | `Nunito:wght@400;700` | soft serif with character |
| Warm, homemade (alt) | `Young Serif` | `Figtree:wght@400;700` | heavier, friendlier serif |
| Friendly, kids, snacks | `Baloo 2:wght@600;800` | `Quicksand:wght@500;700` | round and chunky |
| Friendly (alt) | `Fredoka:wght@500;700` | `Nunito:wght@400;700` | rounded geometric |
| Rounded, soft, wellness | `Varela Round` | `Quicksand:wght@500;700` | calm, no sharp corners |
| Elegant, beauty, fashion | `Cormorant Garamond:ital,wght@0,600;1,600` | `Montserrat:wght@400;600` | high-contrast serif with a clean sans |
| Luxury, high fashion | `Bodoni Moda:wght@600;800` | `Jost:wght@400;500` | Didone; use large sizes only |
| Thin luxe wordmark | `Italiana` | `Jost:wght@400;500` | single weight; wide letter-spacing |
| Classic, heritage | `EB Garamond:ital,wght@0,500;1,500` | `Libre Baskerville:wght@400;700` | bookish, trustworthy |
| Editorial, media, podcast | `DM Serif Display:ital@0;1` | `DM Sans:wght@400;700` | magazine headline feel |
| Editorial (alt) | `Instrument Serif:ital@0;1` | `Inter:wght@400;700` | narrow modern serif |
| News, essays | `Newsreader:ital,wght@0,400;1,600` | `Work Sans:wght@400;700` | reads well small |
| Accent italic | `Playfair Display:ital,wght@1,700` | `Plus Jakarta Sans:wght@600;800` | one italic accent word in a sans name |
| Modern startup, SaaS | `Sora:wght@600;800` | `Inter:wght@400;700` | geometric, confident |
| Modern (alt) | `Manrope:wght@400;700` | `Manrope:wght@400;700` | one family, two weights |
| Quirky tech | `Space Grotesk:wght@500;700` | `IBM Plex Mono:wght@400;600` | quirky grotesk with mono details |
| Developer tool | `Geist:wght@500;800` | `Geist Mono:wght@400` | crisp; the mono suits CLI brands |
| Developer (alt) | `JetBrains Mono:wght@500;800` | `Inter:wght@400;700` | a mono wordmark |
| Retro computing | `Space Mono:wght@400;700` | `Space Mono:wght@400;700` | typewriter-terminal look |
| Bold, streetwear, sport | `Anton` | `Archivo:wght@400;600` | tall condensed; all caps |
| Bold (alt) | `Bebas Neue` | `Oswald:wght@500;700` | poster caps |
| Heavy and loud | `Archivo Black` | `Archivo:wght@400;600` | wide black weight |
| Expressive, Gen Z | `Unbounded:wght@600;900` | `DM Sans:wght@400;700` | wide, rounded and loud |
| Art, creative studio | `Syne:wght@600;800` | `Work Sans:wght@400;700` | odd widths that stand out |
| Contemporary grotesk | `Bricolage Grotesque:wght@500;800` | `Figtree:wght@400;700` | ink-trap details |
| Sport, energy | `Barlow Condensed:wght@600;800` | `Rubik:wght@400;700` | condensed, fast |
| Futuristic, gaming | `Orbitron:wght@600;900` | `Chakra Petch:wght@500;700` | sci-fi |
| Futuristic (alt) | `Michroma` | `Lexend:wght@400;700` | wide tech caps |
| Retro diner, 70s | `Shrikhand` | `Rubik:wght@400;700` | fat italic script |
| Retro poster | `Abril Fatface` | `Lora:ital,wght@0,500;1,500` | fat Didone |
| Retro sign | `Righteous` | `Poppins:wght@400;700` | 60s–70s signage |
| Arcade, toy | `Bungee` | `Rubik:wght@400;700` | blocky signage |
| Handmade, craft | `Caveat:wght@500;700` | `Nunito:wght@400;700` | handwriting; keep it short |
| Casual script | `Pacifico` | `Poppins:wght@400;700` | surf or café script |
| Notebook, education | `Patrick Hand` | `Lexend:wght@400;700` | friendly handwriting; Lexend is very legible |
| Handwritten (alt) | `Kalam:wght@400;700` | `Josefin Sans:wght@400;700` | marker style |
| Mystery, history | `Cinzel:wght@600;800` | `EB Garamond:ital,wght@0,500;1,500` | Roman inscription caps |
| Horror, Halloween | `Creepster` | `Special Elite` | use sparingly; Special Elite is a typewriter |
| Vintage document | `Gloock` | `Special Elite` | stamped, archival |
| Minimal geometric | `Josefin Sans:wght@400;700` | `Josefin Sans:wght@400;700` | 1920s geometric |
| Clean, neutral | `Poppins:wght@400;700` | `Poppins:wght@400;700` | safe for any audience |
| Japanese names | `Noto Sans JP:wght@400;700` | `Noto Sans JP:wght@400;700` | covers kana and kanji |
| Arabic script | `Noto Naskh Arabic:wght@400;700` | `Noto Naskh Arabic:wght@400;700` | for Arabic text in the brand |

Other Google Fonts work too. If `brand.py fonts` returns "no TTF files", the family name is wrong.

## Palettes by mood

Each palette has **ink** (dark), **paper** (light), an **accent** and a **support** color. Text on a background needs a contrast of at least 4.5:1. Ink on paper always passes. Accent text on ink usually passes. Check any other pair.

| Mood | Ink | Paper | Accent | Support |
|---|---|---|---|---|
| Coffee, bakery | `#2a1d17` | `#f3e6d3` | `#f2a541` | `#8c5a3c` |
| Fresh, healthy | `#123524` | `#f1f7ee` | `#5cb85c` | `#f4d35e` |
| Ocean, travel | `#0b2545` | `#eef4f8` | `#13a8c4` | `#f4a259` |
| Night, mystery | `#13161d` | `#f5efe4` | `#ff7a3d` | `#5cffa0` |
| Luxury black-gold | `#0e0e0e` | `#f7f3ea` | `#c9a14a` | `#7a6a4f` |
| Blush, beauty | `#3b2730` | `#fbf1ef` | `#e58fa3` | `#b6a39e` |
| Lavender calm | `#2e2a47` | `#f4f1fb` | `#9b87f5` | `#f7c59f` |
| Kids, candy | `#2b2d42` | `#fffaf0` | `#ff5d8f` | `#3ec1d3` |
| Tech blue | `#0b1020` | `#f5f7fb` | `#3b82f6` | `#22d3ee` |
| Terminal | `#0d1117` | `#e6edf3` | `#3fb950` | `#d29922` |
| Earthy, craft | `#2f2a24` | `#f2ece1` | `#c4683b` | `#7d8b5a` |
| Sport, energy | `#111111` | `#f4f4f4` | `#e4ff1a` | `#ff3b30` |
| Retro 70s | `#3d2817` | `#f6e7c8` | `#e2711d` | `#c9a227` |
| Monochrome | `#111111` | `#fafafa` | `#111111` | `#9a9a9a` |
| Spice, warm red | `#2b0f0e` | `#fbefe6` | `#d1342f` | `#f2b134` |
| Forest, outdoor | `#1d2b1f` | `#eef0e6` | `#c8553d` | `#588157` |

Change one value to fit the brief rather than inventing all four.

## Mark types

| Type | What it is | When it fits | SVG tips |
|---|---|---|---|
| Symbol | one object from the product (cup, leaf, bolt) | food, retail, local business | 2–4 shapes; no outlines thinner than 12 of 400 |
| Monogram | 1–2 initials as a drawn shape | long names, fashion, firms | draw letters as `<path>`; do not use `<text>` in the mark |
| Negative space | a letter or object hidden in the gap between shapes | clever and memorable | test at 32 px, because the gap disappears first |
| Abstract geometric | circles, arcs or blocks with no literal meaning | tech, finance, studios | use an 8-unit grid; keep it to 2 colors |
| Mascot or character | a simple face or creature | kids, games, communities, creators | big eyes and a simple outline; the face must read at 44 px |
| Emblem or badge | the mark inside a circle or shield with a border | cafés, craft, heritage, sports | do not put tiny text on the ring, since it is unreadable as an avatar |
| Wordmark only | the name itself is the logo, with one drawn twist; the avatar is the first letter | short names, media, fashion, SaaS | write `wordmark.svg`; see "Text-based logos" below |
| Glyph in motion | a glyph (`@`, `#`, a letter) whose stroke flows on into an arrow or a trail | launches, growth, tools that "take you somewhere" | see "Glyph in motion" below |
| Punctuation or glyph | `,` `;` `{}` `#` used as the mark | names that suggest a symbol | use the glyph's shape as a path, not a `<text>` |

## Glyph in motion

One stroke that changes meaning halfway: the glyph is drawn, then the same line keeps going and becomes an arrow. The logo of the brand-kickstart repo is this: an `@` whose ring sweeps into a launch arrow.

- **End the glyph where its direction already points the way the arrow goes.** For a ring drawn clockwise, end it at the top (it is heading right there), not at the upper right (it is heading down there). A tail that starts against the ring's direction reads as a kink.
- **Join with one cubic curve whose first control point lies on the ring's tangent and whose last lies on the arrow's line**, e.g. ring end `(195,100)` heading right, arrow tip `(334,74)` heading up-right: `M195 100 C235 98 305 103 334 74`. Same stroke width and round caps as the ring, so the join has no seam.
- **Color: the tail starts in the ring's color and ends in the accent.** Use `gradientUnits="userSpaceOnUse"` from the join point to the tip, with the accent arriving at about 75–80%. A hard color switch at the join looks like two shapes.
- Draw the arrowhead as its own short path (`M292 72 H336 V116`) in the accent.
- Keep the tip inside the centre circle, radius 150 of 400 with the stroke cap included. Shrink the whole group with one `transform` rather than shortening the arrow, because a stubby arrow reads as a blob.
- In 3D: a glow under the arrowhead needs a filter region of about `x="-150%" width="400%"`. A tighter one clips the blur into a visible square.
- Echo it in the wordmark: replace one character of the name, such as a hyphen, a dot or a space, with the same arrow as a `<path>` in the accent (`brand↗kickstart`).

## Text-based logos

When the name is the logo, write **`wordmark.svg`** next to `logo.svg`. `brand.py` then uses the drawing everywhere the name appears as a logo: the board, the mockups and the banners. It also exports `logo/wordmark-dark.png` and `logo/wordmark-light.png`.

| Kind | What it is | Examples of the idea | Fits |
|---|---|---|---|
| Wordmark | the whole name, set in the display font, plus one custom detail | a dot on the i in the accent, a cut through one letter, a joined pair of letters, an underline swoosh | short names (up to about 8 letters), media, SaaS, fashion |
| Lettermark | 2–4 initials as a tight unit | stacked, overlapped or boxed initials | long names, firms, institutions |
| Combination | a small symbol that replaces one letter of the name | the o as a coffee cup, the A as a mountain | when one letter suggests the product |

A plain name in a nice font is not a logo. Change **one** thing and keep the rest quiet.

Rules for `wordmark.svg`:
- A wide `viewBox` that fits the drawing tightly, e.g. `0 0 600 150`. Size it so `y` 0 is about the cap top and the bottom edge is the descender line.
- `fill="currentColor"` on the parts that take the text color. `brand.py` swaps it for paper on dark backgrounds and ink on light ones. Give the twist a fixed palette color, usually the accent.
- No background shape. It sits on ink, paper and photos.
- `<text>` with the display font is fine. The name must use the same case and tracking as `concept.json`, and the font must be in `fonts/`. Draw the twist with `<path>` or `<circle>` on top of the text.
- Start every `id` with `wm-`, because the drawing is pasted into pages that have their own ids.
- Keep it to one line.
- A wordmark can be 2.5D or 3D too, with the same recipes as a mark (see "Rendering styles" below):
  - **2.5D text:** repeat the `<text>` 10–14 times, offset by 1 unit down and right each time, in a darker accent. Then put the face on top in `currentColor`. Add a thin accent stroke on the face if the edge gets lost.
  - **3D text:** fill the text with a vertical gradient (`id="wm-face"`). Put a white-to-clear gradient copy on top, clipped to the upper third, for the gloss, and a blurred dark copy below for the shadow. Do not stroke text with tight tracking, because the strokes cross where letters overlap.
  - The avatar in `logo.svg` gets the same treatment, plus a `logo-flat.svg`.

`logo.svg` is still required, because every platform needs a square avatar. For a text logo, make it the first letter, the initials, or the twist alone, drawn as `<path>` on the background square. Do not use `<text>` there: `favicon.svg` is copied as it is, and a browser does not have the brand font.

## Rendering styles: flat, 2.5D, 3D

A mark can be drawn in three ways. Treat the rendering style as one more axis of variety: a set of 3 options can be one flat, one 2.5D and one 3D. A text-based option counts as an axis too: one of the 3 can be a wordmark.

| Style | Looks like | Fits | Avoid for |
|---|---|---|---|
| Flat | solid shapes, no light | almost everything; the safest at small sizes | brands that want to feel tactile or premium-tech |
| 2.5D | isometric or extruded, flat faces in 3 tones, long shadows | toys, logistics, games, education, building or construction, dev tools | luxury, editorial |
| 3D | gradients, highlights, soft shadows, glass, clay or chrome | apps, AI and tech, beauty and skincare, drinks, gaming | heritage, legal, anything printed in one color |

### 2.5D recipe

- **Isometric grid:** the axes run at 30° (x step 95, y step 55 per 110 units of edge). A cube centred at (200, 200) with edge 110 has these faces:
  - top `200,90 295,145 200,200 105,145`
  - left `105,145 200,200 200,310 105,255`
  - right `200,200 295,145 295,255 200,310`
- **Three tones of one color,** with the light fixed from the top-left: top = lightest, left = base, right = darkest. Keep the same three tones on every face of the mark.
- **Extrusion:** copy a flat shape, offset it down and right by 8–20 units in a darker tone, and join the corners. Or use a long shadow: a 45° polygon at 15–25% black.
- Details sit *on* a face and follow its angle, e.g. tape on a box, or a window on a wall.

### 3D recipe

```svg
<radialGradient id="body" cx=".35" cy=".3" r=".8">        <!-- light from the top-left -->
  <stop offset="0" stop-color="#c9f1ea"/><stop offset=".45" stop-color="#7fd1c3"/><stop offset="1" stop-color="#2f7f86"/>
</radialGradient>
<filter id="soft"><feGaussianBlur stdDeviation="6"/></filter>
```

Build it in this order:
1. The body, filled with the radial gradient.
2. A **rim light** on the edge away from the light: a thin white stroke at 20–30% opacity.
3. A soft **highlight** blob: a white ellipse at 50–70% opacity, blurred.
4. A small sharp **specular** dot.
5. A **contact shadow** under the object: a black ellipse, blurred, at 30–45%.

- Use one light direction for the whole set: logo, illustration and app icon.
- At most 2–3 gradients. More looks like a 2009 web button.
- **Always add `logo-flat.svg`:** the same mark in 1–2 flat colors. `brand.py` uses it for the favicon and every icon under 64 px, because gradients and highlights turn to mush at 16 px.

The 2.5D and 3D marks still follow the logo rules: they must fit inside the centre circle, read at 44 px, and use no text.

## Banner layouts

Rotate these so the pages do not all look the same:

1. **Logo left, wordmark right**: logo and name in one row in the safe area. This is the safest layout.
2. **Centered stack**: logo above, name and tagline below. Suits tall covers and highlights.
3. **Oversized crop**: the mark scaled up past the edge as a background, with the name small on top.
4. **Pattern**: the mark repeated as a faint tile at about 6–10% opacity, with the name on a solid band.
5. **Split block**: half ink and half accent, with the name across the seam.
6. **Scene**: a few flat shapes from the brand's world (a counter, a skyline or a desk), with the name in the safe area.

Keep one layout family per brand across platforms, but you can change the composition per size.
