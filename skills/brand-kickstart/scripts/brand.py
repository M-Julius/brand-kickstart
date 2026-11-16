#!/usr/bin/env python3
"""Render a brand folder to PNGs with resvg (pip install resvg-py, 2 MB, no browser).

Input (written by the agent):
  <dir>/logo.svg                   the mark, viewBox 0 0 400 400, may have rounded corners
  <dir>/app-icon.svg               optional: square, full-bleed, no rounded corners (app stores round it)
  <dir>/pages/<name>-<W>x<H>.svg   one SVG per banner or cover, exactly W x H
  <dir>/fonts/*.ttf                fonts the pages use (get them with the `fonts` command)
  <dir>/concepts/<id>/logo.svg, concept.json, illustration.svg (optional)   style options to pick from
  <dir>/wordmark.svg               optional: the name drawn as a logo; currentColor marks the parts that take the text color

Output:
  <dir>/logo/     logo-1080.png (profile picture), logo-512.png
  <dir>/favicon/  favicon.svg, favicon.ico, favicon-16/32.png, apple-touch-icon.png, icon-192/512.png,
                  site.webmanifest, head.html (tags to paste into <head>)
  <dir>/app/      app-store-1024.png (no alpha), play-store-512.png      (only with app-icon.svg)
  <dir>/social/   <name>-<W>x<H>.png for every page
  <dir>/concepts/ <id>.png (one board per style option), all.png (every option side by side)
  <dir>/brand.json, BRAND.md, palette.png, mockups/   written by `pick` for the chosen option

Usage:
  python3 brand.py fonts <dir> "Plus Jakarta Sans:wght@800" "Playfair Display:ital,wght@1,700"
  python3 brand.py board <dir>
  python3 brand.py pick <dir> <concept-id> [--handle name] [--domain name.com]
  python3 brand.py render <dir> [--name "Display Name"] [--color "#13161d"]
"""
import argparse
import html
import json
import os
import re
import shutil
import struct
import sys
import urllib.parse
import urllib.request
import zlib

LOGO_SIZES = {"logo/logo-1080.png": 1080, "logo/logo-512.png": 512}
ICONS = {"favicon/favicon-16.png": 16, "favicon/favicon-32.png": 32,
         "favicon/icon-192.png": 192, "favicon/icon-512.png": 512}
ICO_SIZES = [16, 32, 48]
HEAD = """<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
"""
INSTALL_HINT = ("Rendering needs resvg-py (2 MB): python3 -m pip install resvg-py\n"
                "or: python3 -m venv ~/.venvs/brand-kickstart && ~/.venvs/brand-kickstart/bin/pip install resvg-py")


def page_size(filename):
    m = re.search(r"-(\d+)x(\d+)\.svg$", filename)
    if not m or not all(int(v) > 0 for v in m.groups()):
        return None
    return int(m[1]), int(m[2])


def ico_bytes(pngs):
    """ICO file holding PNG images (supported by every current browser and OS)."""
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset, entries, body = 6 + 16 * len(pngs), b"", b""
    for size, data in pngs:
        s = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    return head + entries + body


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _unfilter_row(ftype, row, prev, bpp):
    if ftype == 0:
        return bytes(row)
    if ftype == 2:
        return bytes((x + p) & 255 for x, p in zip(row, prev))
    out = bytearray(row)
    for i in range(len(out)):
        a = out[i - bpp] if i >= bpp else 0
        c = prev[i - bpp] if i >= bpp else 0
        out[i] = (out[i] + (a if ftype == 1 else (a + prev[i]) // 2 if ftype == 3 else _paeth(a, prev[i], c))) & 255
    return bytes(out)


def _filter_row(ftype, row, prev, bpp):
    """Inverse of _unfilter_row; only used by tests."""
    out = bytearray(len(row))
    for i in range(len(row)):
        a = row[i - bpp] if i >= bpp else 0
        c = prev[i - bpp] if i >= bpp else 0
        pred = [0, a, prev[i], (a + prev[i]) // 2, _paeth(a, prev[i], c)][ftype]
        out[i] = (row[i] - pred) & 255
    return bytes(out)


def strip_alpha(png, background):
    """RGBA PNG (8-bit, as resvg writes it) -> RGB PNG over `background`. App Store rejects alpha channels."""
    w, h = struct.unpack(">II", png[16:24])
    idat, pos = b"", 8
    while pos < len(png):
        n, t = struct.unpack(">I4s", png[pos:pos + 8])
        if t == b"IDAT":
            idat += png[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw, stride, prev, out = zlib.decompress(idat), w * 4, bytes(w * 4), bytearray()
    for y in range(h):
        start = y * (stride + 1)
        prev = _unfilter_row(raw[start], raw[start + 1:start + 1 + stride], prev, 4)
        out.append(0)
        for i in range(0, stride, 4):
            a = prev[i + 3]
            out += bytes((prev[i + k] * a + background[k] * (255 - a) + 127) // 255 for k in range(3))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(out), 9)) + chunk(b"IEND", b""))


def _hex(color):
    c = (color or "#ffffff").lstrip("#")
    c = "".join(ch * 2 for ch in c) if len(c) == 3 else c
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _fetch(url):
    # a plain client gets TTF links from Google Fonts (browsers get WOFF2, which resvg cannot read)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "brand.py"}), timeout=20) as r:
        return r.read()


def download_fonts(directory, families, fetch=_fetch):
    query = "&".join("family=" + urllib.parse.quote(f.replace(" ", "+"), safe="+:@,;.") for f in families)
    css = fetch("https://fonts.googleapis.com/css2?" + query).decode("utf-8", "replace")
    urls = re.findall(r"url\((https://[^)]+\.ttf)\)", css)
    if not urls:
        raise RuntimeError("Google Fonts returned no TTF files; check the family names on fonts.google.com")
    os.makedirs(os.path.join(directory, "fonts"), exist_ok=True)
    files = []
    for url in urls:
        path = os.path.join(directory, "fonts", url.rsplit("/", 1)[1])
        with open(path, "wb") as f:
            f.write(fetch(url))
        files.append(path)
    return files


def resvg_render(font_dir):
    import resvg_py

    def render(path, w, h):
        dirs = [font_dir] if os.path.isdir(font_dir) else []
        # no system fonts: text only renders in the fonts we downloaded, so no emoji or fallback font sneaks in
        return bytes(resvg_py.svg_to_bytes(svg_path=path, width=w, height=h, font_dirs=dirs, skip_system_fonts=True,
                                           resources_dir=os.path.dirname(os.path.abspath(path))))
    return render


def _write(directory, rel, data):
    path = os.path.join(directory, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def build(directory, name, color, render):
    """Render everything; returns page files skipped because their name has no <W>x<H>."""
    logo = os.path.join(directory, "logo.svg")
    if not os.path.exists(logo):
        raise FileNotFoundError(f"{logo} is missing; write the logo first")
    app = os.path.join(directory, "app-icon.svg")
    app = app if os.path.exists(app) else None
    # a detailed (2.5D/3D) logo turns to mush at favicon size; logo-flat.svg is its simplified small version
    flat = os.path.join(directory, "logo-flat.svg")
    small = flat if os.path.exists(flat) else logo

    for rel, size in {**LOGO_SIZES, **ICONS}.items():
        _write(directory, rel, render(small if size < 64 else logo, size, size))
    # iOS fills transparent corners with black, so prefer the full-bleed square icon when there is one
    _write(directory, "favicon/apple-touch-icon.png", render(app or logo, 180, 180))
    _write(directory, "favicon/favicon.ico", ico_bytes([(s, render(small, s, s)) for s in ICO_SIZES]))
    shutil.copyfile(small, os.path.join(directory, "favicon", "favicon.svg"))
    if app:
        _write(directory, "app/app-store-1024.png", strip_alpha(render(app, 1024, 1024), _hex(color)))
        _write(directory, "app/play-store-512.png", render(app, 512, 512))

    manifest = {"name": name, "short_name": name, "display": "standalone",
                "icons": [{"src": f"/icon-{s}.png", "sizes": f"{s}x{s}", "type": "image/png"} for s in (192, 512)]}
    if color:
        manifest["theme_color"] = manifest["background_color"] = color
    _write(directory, "favicon/site.webmanifest", json.dumps(manifest, indent=2).encode())
    _write(directory, "favicon/head.html", HEAD.encode())

    skipped, pages = [], os.path.join(directory, "pages")
    for page in sorted(os.listdir(pages)) if os.path.isdir(pages) else []:
        if not page.endswith(".svg"):
            continue
        size = page_size(page)
        if not size:
            skipped.append(page)
            continue
        _write(directory, os.path.join("social", page[:-4] + ".png"), render(os.path.join(pages, page), *size))
    return skipped


BOARD_W, BOARD_H = 1600, 1000
REQUIRED = ("title", "why", "name", "tagline", "display", "text", "colors")
COLOR_KEYS = ("ink", "paper", "accent", "support")


def wrap(text, width):
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def _esc(value):
    return html.escape(str(value), quote=True)


def on_color(hex_color):
    """Black or white label, whichever reads on this background."""
    r, g, b = (v / 255 for v in _hex(hex_color))
    return "#111111" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else "#ffffff"


def _font(f, size, fill, extra=""):
    # quoted: an unquoted family with a word starting in a digit ("Baloo 2") is invalid CSS and renders nothing
    return (f'font-family="{_esc(repr(str(f["family"])))}" font-weight="{_esc(f.get("weight", 400))}" '
            f'font-style="{_esc(f.get("style", "normal"))}" font-size="{size}" fill="{fill}"{extra}')


def load_logotype(path):
    """wordmark.svg as (viewBox width, height, inner markup), or None when the brand has no drawn wordmark."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    m = re.search(r"<svg\b[^>]*?viewBox=\"\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*\"[^>]*>(.*)</svg>", svg, re.S)
    if not m:
        raise ValueError(f"{path} needs a viewBox on its <svg>")
    return float(m.group(1)), float(m.group(2)), m.group(3)


def _wordmark(d, name, size, fill, x, y, anchor="middle"):
    """Display name with the concept's tracking (em) and case, or the drawn wordmark.svg in its place."""
    if d.get("_logotype"):
        # the drawn wordmark fills the box a line of `size` text would: cap top (y - 0.95 size) to descender
        vw, vh, inner = d["_logotype"]
        h = size * 1.2
        w = h * vw / vh
        left = x - w / 2 if anchor == "middle" else x
        return (f'<svg x="{left:.1f}" y="{y - size * 0.95:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'viewBox="0 0 {vw:g} {vh:g}" overflow="visible">{inner.replace("currentColor", fill)}</svg>')
    text = name.upper() if d.get("case") == "upper" else name
    track = float(d.get("tracking", 0))
    spacing = f' letter-spacing="{track * size:.1f}"' if track else ""
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}"{spacing} {_font(d, size, fill)}>{_esc(text)}</text>'


def _fit(d, name, width, largest):
    """Rough font size that fits `name` into `width` px (no font metrics in the stdlib)."""
    if d.get("_logotype"):
        vw, vh, _ = d["_logotype"]
        return int(min(largest, width / (1.2 * vw / vh)))
    per_char = (0.68 if d.get("case") == "upper" else 0.58) + float(d.get("tracking", 0))
    return int(min(largest, width / max(len(name) * per_char, 1)))


def board_svg(cid, c, has_illustration, has_flat=False):
    """One style option as a brand identity sheet, 1600 x 1000."""
    col = {k: _esc(c["colors"][k]) for k in COLOR_KEYS}
    ink, paper, accent, support = (col[k] for k in COLOR_KEYS)
    d, t, name = c["display"], c["text"], c["name"]
    label = lambda x, y, s, fill, extra="": f'<text x="{x}" y="{y}" letter-spacing="2.4" {_font(t, 13, fill, extra)}>{_esc(s.upper())}</text>'  # noqa: E731
    rule = lambda y: f'<path d="M1024 {y} H1536" stroke="{ink}" stroke-opacity=".14" stroke-width="1.5"/>'  # noqa: E731
    why = "".join(f'<tspan x="1024" dy="{0 if i == 0 else 30}">{_esc(line)}</tspan>'
                  for i, line in enumerate(wrap(c["why"], 46)[:3]))
    stripes = "".join(
        f'<rect x="{1024 + i * 128}" y="560" width="128" height="120" fill="{col[k]}"/>'
        f'<text x="{1040 + i * 128}" y="584" letter-spacing="1.6" {_font(t, 11, on_color(c["colors"][k]), " opacity=\".7\"")}>{k.upper()}</text>'
        f'<text x="{1040 + i * 128}" y="664" {_font(t, 15, on_color(c["colors"][k]))}>{col[k]}</text>'
        for i, k in enumerate(COLOR_KEYS))
    avatars = "".join(
        f'<clipPath id="c{s}"><circle cx="{x + s / 2}" cy="{752 + s / 2}" r="{s / 2}"/></clipPath>'
        f'<image href="{"logo-flat.svg" if has_flat and s < 64 else "logo.svg"}" x="{x}" y="752" width="{s}" height="{s}" clip-path="url(#c{s})"/>'
        f'<text x="{x}" y="878" {_font(t, 13, support)}>{s}px</text>'
        for x, s in ((1024, 96), (1148, 44), (1220, 16)))
    art = ('<clipPath id="banner"><rect x="1280" y="752" width="256" height="96" rx="10"/></clipPath>'
           f'<rect x="1280" y="752" width="256" height="96" rx="10" fill="{ink}"/>'
           '<image href="illustration.svg" x="1280" y="752" width="256" height="96" '
           'preserveAspectRatio="xMidYMid slice" clip-path="url(#banner)"/>'
           f'<text x="1280" y="878" {_font(t, 13, support)}>Illustration</text>' if has_illustration else "")
    spec_d = f'{d["family"]} {d.get("weight", 400)}{" italic" if d.get("style") == "italic" else ""}'
    spec_t = f'{t["family"]} {t.get("weight", 400)}'
    hero_size = _fit(d, name, 760, 88)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_W}" height="{BOARD_H}" viewBox="0 0 {BOARD_W} {BOARD_H}">
<rect width="{BOARD_W}" height="{BOARD_H}" fill="{paper}"/>
<rect width="960" height="{BOARD_H}" fill="{ink}"/>
{label(64, 88, cid, paper, ' opacity=".55"')}
<image href="logo.svg" x="340" y="200" width="280" height="280"/>
{_wordmark(d, name, hero_size, paper, 480, 610)}
<text x="480" y="{610 + 56}" text-anchor="middle" {_font(t, 22, accent)}>{_esc(c["tagline"])}</text>
<path d="M64 936 H896" stroke="{paper}" stroke-opacity=".12" stroke-width="1.5"/>
{label(64, 966, spec_d + "  /  " + spec_t, paper, ' opacity=".45"')}
{label(1024, 88, "Style option", accent)}
<text x="1024" y="146" {_font(d, 46, ink)}>{_esc(c["title"])}</text>
<text x="1024" y="196" {_font(t, 20, ink, ' opacity=".78"')}>{why}</text>
{rule(300)}
{label(1024, 340, "Type", support)}
<text x="1024" y="462" {_font(d, 96, ink)}>Aa</text>
<text x="1250" y="410" {_font(d, 24, ink)}>{_esc(d["family"])}</text>
<text x="1250" y="436" {_font(t, 15, support)}>Display, {_esc(d.get("weight", 400))}</text>
<text x="1250" y="476" {_font(t, 20, ink)}>{_esc(t["family"])}</text>
<text x="1250" y="500" {_font(t, 15, support)}>Text, {_esc(t.get("weight", 400))}</text>
{rule(526)}
{label(1024, 548, "Palette", support)}{stripes}<rect x="1024" y="560" width="512" height="120" fill="none" stroke="{ink}" stroke-opacity=".14" stroke-width="1.5"/>
{label(1024, 734, "In use", support)}{avatars}{art}
</svg>"""


def tile_xy(i, count, cols=2):
    """Position of board i in the overview grid; a short last row is centered."""
    row, col = divmod(i, cols)
    w, h = BOARD_W // cols, BOARD_H // cols
    in_row = min(cols, count - row * cols)
    return (BOARD_W - in_row * w) // 2 + col * w, row * h


def build_boards(directory, render):
    """Render concepts/<id>/ into concepts/<id>.png and concepts/all.png; returns the PNG paths."""
    cdir = os.path.join(directory, "concepts")
    ids = sorted(i for i in os.listdir(cdir) if os.path.exists(os.path.join(cdir, i, "concept.json"))) \
        if os.path.isdir(cdir) else []
    if not ids:
        raise FileNotFoundError(f"no {cdir}/<id>/concept.json found; write the concepts first")
    out = []
    for cid in ids:
        folder = os.path.join(cdir, cid)
        with open(os.path.join(folder, "concept.json")) as f:
            c = json.load(f)
        missing = [k for k in REQUIRED if k not in c]
        missing += [f"colors.{k}" for k in COLOR_KEYS if k not in c.get("colors", {}) and "colors" in c]
        if missing:
            raise ValueError(f"{cid}/concept.json is missing: {', '.join(missing)}")
        if not os.path.exists(os.path.join(folder, "logo.svg")):
            raise FileNotFoundError(f"{cid}/logo.svg is missing")
        c["display"]["_logotype"] = load_logotype(os.path.join(folder, "wordmark.svg"))
        board = os.path.join(folder, "board.svg")
        with open(board, "w") as f:
            f.write(board_svg(cid, c, os.path.exists(os.path.join(folder, "illustration.svg")),
                              os.path.exists(os.path.join(folder, "logo-flat.svg"))))
        out.append(os.path.join(cdir, f"{cid}.png"))
        _write(directory, os.path.relpath(out[-1], directory), render(board, BOARD_W, BOARD_H))
    h = BOARD_H // 2
    rows = -(-len(ids) // 2)
    # tile the rendered PNGs: resvg does not draw images or text nested two SVGs deep
    tiles = "".join('<image href="{}.png" x="{}" y="{}" width="{}" height="{}"/>'.format(
        _esc(cid), *tile_xy(i, len(ids)), BOARD_W // 2, h) for i, cid in enumerate(ids))
    overview = os.path.join(cdir, "all.svg")
    with open(overview, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_W}" height="{rows * h}">'
                f'<rect width="100%" height="100%" fill="#f4f4f2"/>{tiles}</svg>')
    out.append(os.path.join(cdir, "all.png"))
    _write(directory, os.path.relpath(out[-1], directory), render(overview, BOARD_W, rows * h))
    return sorted(out)


def font_spec(font):
    """Google Fonts spec for a concept font, e.g. {"family": "Lora", "weight": 500} -> "Lora:wght@500"."""
    weight = font.get("weight", 400)
    if font.get("style") == "italic":
        return f'{font["family"]}:ital,wght@1,{weight}'
    return f'{font["family"]}:wght@{weight}'


def _brand(directory):
    with open(os.path.join(directory, "brand.json"), encoding="utf-8") as f:
        c = json.load(f)
    c["display"]["_logotype"] = load_logotype(os.path.join(directory, "wordmark.svg"))
    handle = c.get("handle") or re.sub(r"[^a-z0-9]", "", c["name"].lower())
    return c, handle, c.get("domain") or f"{handle}.com"


def kit_defaults(directory):
    """(name, ink color) from brand.json, so `render` needs no flags after `pick`."""
    if not os.path.exists(os.path.join(directory, "brand.json")):
        return None, None
    c = _brand(directory)[0]
    return c["name"], c["colors"]["ink"]


def pick(directory, cid, render, fetch=_fetch, handle=None, domain=None):
    """Make concept <cid> the brand: copy its files, write brand.json, get fonts, mockups and BRAND.md."""
    src = os.path.join(directory, "concepts", cid)
    if not os.path.exists(os.path.join(src, "concept.json")):
        raise FileNotFoundError(f"{src}/concept.json is missing; run `board` and pick one of its ids")
    for name in ("logo.svg", "logo-flat.svg", "illustration.svg", "mark.svg", "wordmark.svg"):
        if os.path.exists(os.path.join(src, name)):
            shutil.copyfile(os.path.join(src, name), os.path.join(directory, name))
    with open(os.path.join(src, "concept.json"), encoding="utf-8") as f:
        c = json.load(f)
    c["concept"] = cid
    if handle:
        c["handle"] = handle
    if domain:
        c["domain"] = domain
    _write(directory, "brand.json", json.dumps(c, indent=2, ensure_ascii=False).encode())
    download_fonts(directory, sorted({font_spec(c["display"]), font_spec(c["text"])}), fetch)
    return finish(directory, render)


def finish(directory, render):
    """Mockups, palette and BRAND.md for the picked brand."""
    out = build_mockups(directory, render)
    out.append(build_palette(directory, render))
    out += build_wordmarks(directory, render)
    write_brand_md(directory)
    return out


MOCKUPS = ("website", "social-profile", "tote-bag", "business-card", "t-shirt", "storefront")
MOCK_W, MOCK_H = 1200, 900
# Studio light, soft shadows, paper and fabric grain, fold shading: what makes a flat drawing read as an object.
FX = """<defs>
<radialGradient id="studio" cx=".5" cy=".36" r=".8"><stop offset="0" stop-color="#f5f2ed"/><stop offset="1" stop-color="#d3cdc3"/></radialGradient>
<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".10"/></linearGradient>
<filter id="b10" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="10"/></filter>
<filter id="b24" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="24"/></filter>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.14"/></feComponentTransfer></filter>
<filter id="canvas" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.55 0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.22"/></feComponentTransfer></filter>
<linearGradient id="sides" x1="0" x2="1"><stop offset="0" stop-color="#000" stop-opacity=".30"/><stop offset=".2" stop-color="#000" stop-opacity="0"/><stop offset=".8" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".30"/></linearGradient>
<linearGradient id="light" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".12"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".16"/></linearGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".16"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".10"/></linearGradient>
<linearGradient id="metal" x1="0" x2="1"><stop offset="0" stop-color="#3b3b3d"/><stop offset=".5" stop-color="#121214"/><stop offset="1" stop-color="#2e2e30"/></linearGradient>
<linearGradient id="alu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e4e4e6"/><stop offset="1" stop-color="#a7a7ad"/></linearGradient>
<linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".45" stop-color="#fff" stop-opacity=".04"/><stop offset="1" stop-color="#fff" stop-opacity=".12"/></linearGradient>
<radialGradient id="glow" cx=".5" cy="0" r="1"><stop offset="0" stop-color="#ffe7b0" stop-opacity=".55"/><stop offset="1" stop-color="#ffe7b0" stop-opacity="0"/></radialGradient>
<pattern id="brick" width="84" height="56" patternUnits="userSpaceOnUse"><path d="M0 28 H84 M0 56 H84 M42 0 V28 M0 28 V56 M84 28 V56" stroke="#000" stroke-opacity=".22" stroke-width="2.5"/></pattern>
</defs>"""


def _mockup_svgs(directory):
    c, handle, domain = _brand(directory)
    col = {k: _esc(c["colors"][k]) for k in COLOR_KEYS}
    ink, paper, accent, support = (col[k] for k in COLOR_KEYS)
    d, t, name, tag = c["display"], c["text"], c["name"], _esc(c["tagline"])
    # light surfaces get mark.svg (no background) when there is one; on ink, logo.svg's own ink square blends in
    light = "../mark.svg" if os.path.exists(os.path.join(directory, "mark.svg")) else "../logo.svg"
    mark = "../logo.svg"
    art = os.path.exists(os.path.join(directory, "illustration.svg"))
    on_accent = on_color(c["colors"]["accent"])
    img = lambda href, x, y, w, h, extra="": f'<image href="{href}" x="{x}" y="{y}" width="{w}" height="{h}"{extra}/>'  # noqa: E731
    text = lambda x, y, s, size, fill, anchor="start", f=t: (  # noqa: E731
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" {_font(f, size, fill)}>{_esc(s)}</text>')
    studio = f'<rect width="{MOCK_W}" height="{MOCK_H}" fill="url(#studio)"/>'
    floor = f'<rect y="640" width="{MOCK_W}" height="260" fill="url(#floor)"/>'
    full = '<rect width="1200" height="900"'

    # ---- website on a laptop, on an oak desk with a plant and a branded mug.
    # The page is drawn at 1020 x 645 and scaled into the 714 x 452 screen.
    star = "M0 -9 L2.6 -2.8 L9 -2.8 L3.8 1.2 L5.6 7.6 L0 3.8 L-5.6 7.6 L-3.8 1.2 L-9 -2.8 L-2.6 -2.8 Z"
    stars = "".join(f'<path d="{star}" transform="translate({x} 0)" fill="{accent}"/>' for x in (0, 22, 44, 66, 88))
    lines_ = wrap(c["tagline"], 18)[:2]
    headline = "".join(f'<tspan x="50" dy="{0 if i == 0 else 54}">{_esc(line)}</tspan>' for i, line in enumerate(lines_))
    sub_y = 196 + 54 * (len(lines_) - 1) + 44
    btn_y = sub_y + 58
    hero_art = img("../illustration.svg", 575, 120, 360, 256) if art else img(mark, 655, 140, 200, 200)
    products = ""
    for i, fill in enumerate((ink, accent, support)):
        x = 50 + i * 312
        products += (f'<rect x="{x}" y="470" width="296" height="150" rx="14" fill="#ffffff"/>'
                     f'<rect x="{x}" y="470" width="296" height="96" rx="14" fill="{fill}"/><rect x="{x}" y="540" width="296" height="26" fill="{fill}"/>'
                     + (img(mark, x + 112, 482, 72, 72) if i != 1 or not art else img("../illustration.svg", x + 78, 474, 140, 100))
                     + f'<rect x="{x + 18}" y="582" width="120" height="11" rx="5" fill="{ink}" fill-opacity=".7"/>'
                     f'<rect x="{x + 18}" y="602" width="70" height="9" rx="4" fill="{ink}" fill-opacity=".3"/>'
                     f'<rect x="{x + 222}" y="584" width="56" height="24" rx="12" fill="{accent}"/>')
    page = f"""<rect width="1020" height="645" fill="{paper}"/>
<rect width="1020" height="38" fill="#e3dfd8"/><circle cx="22" cy="19" r="6" fill="#c3beb5"/><circle cx="42" cy="19" r="6" fill="#c3beb5"/><circle cx="62" cy="19" r="6" fill="#c3beb5"/>
<rect x="300" y="8" width="420" height="22" rx="11" fill="#f6f4f0"/>{text(510, 24, domain, 12, "#77736b", "middle")}
{img("../logo.svg", 50, 54, 40, 40)}{_wordmark(d, name, 24, ink, 102, 82, "start")}
{text(640, 80, "Menu", 15, ink, "middle")}{text(720, 80, "About", 15, ink, "middle")}{text(800, 80, "Visit", 15, ink, "middle")}
<rect x="852" y="56" width="118" height="38" rx="19" fill="{accent}"/>{text(911, 80, "Get started", 14, on_accent, "middle")}
<text x="50" y="146" letter-spacing="2.4" {_font(t, 12, support)}>{_esc(name.upper())}</text>
<text x="50" y="196" {_font(d, 48, ink)}>{headline}</text>
<rect x="50" y="{sub_y - 12}" width="380" height="11" rx="5" fill="{ink}" fill-opacity=".22"/><rect x="50" y="{sub_y + 10}" width="300" height="11" rx="5" fill="{ink}" fill-opacity=".22"/>
<rect x="50" y="{btn_y}" width="160" height="48" rx="24" fill="{accent}"/>{text(130, btn_y + 30, "Get started", 16, on_accent, "middle")}
<rect x="224" y="{btn_y}" width="150" height="48" rx="24" fill="none" stroke="{ink}" stroke-opacity=".35" stroke-width="2"/>{text(299, btn_y + 30, "Learn more", 16, ink, "middle")}
<rect x="555" y="110" width="415" height="300" rx="22" fill="{ink}"/>{hero_art}
<rect x="508" y="338" width="230" height="84" rx="14" fill="#000" opacity=".18" filter="url(#b10)"/>
<rect x="500" y="330" width="230" height="84" rx="14" fill="#ffffff"/>
<clipPath id="rv"><circle cx="536" cy="372" r="20"/></clipPath>{img("../logo.svg", 516, 352, 40, 40, ' clip-path="url(#rv)"')}
<g transform="translate(572 362)">{stars}</g>{text(568, 396, "4.9 from 1,200 reviews", 13, "#555555")}
{products}"""
    oak = """<filter id="wood" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.0035 0.11" numOctaves="4" seed="7"/><feColorMatrix type="matrix" values="0 0 0 0 0.30  0 0 0 0 0.18  0 0 0 0 0.09  0 0 0 1.6 -0.62"/></filter>"""
    leaves = "".join(f'<path d="M0 0 C-14 -30 -10 -70 0 -96 C10 -70 14 -30 0 0 Z" transform="translate(148 548) rotate({r})" fill="{f}"/>'
                     for r, f in ((-38, "#3f5a3a"), (-16, "#567a4c"), (6, "#4a6a42"), (28, "#3f5a3a"), (46, "#567a4c")))
    website = f"""{FX}<defs>{oak}</defs>
<rect width="1200" height="600" fill="url(#studio)"/>
<rect y="596" width="1200" height="304" fill="#c9b08e"/><rect y="596" width="1200" height="304" filter="url(#wood)"/>
<rect y="596" width="1200" height="304" fill="url(#floor)"/><rect y="596" width="1200" height="3" fill="#fff" opacity=".35"/>
<ellipse cx="600" cy="652" rx="430" ry="16" fill="#000" opacity=".45" filter="url(#b10)"/>
<rect x="236" y="120" width="728" height="486" rx="22" fill="#1c1c1e"/>
<rect x="237" y="121" width="726" height="484" rx="21" fill="none" stroke="#4a4a4e" stroke-width="2"/>
<circle cx="600" cy="132" r="3.5" fill="#3a3a3e"/>
<clipPath id="scr"><rect x="243" y="142" width="714" height="452" rx="3"/></clipPath>
<g clip-path="url(#scr)"><g transform="translate(243 142) scale(0.7)">{page}</g>
<path d="M243 142 L560 142 L330 594 L243 594 Z" fill="#fff" opacity=".05"/></g>
<path d="M186 604 H1014 L990 640 Q985 648 972 648 H228 Q215 648 210 640 Z" fill="url(#alu)"/>
<path d="M186 604 H1014" stroke="#f4f4f6" stroke-width="2"/><rect x="540" y="604" width="120" height="7" rx="3" fill="#8d8d93"/>
<ellipse cx="150" cy="660" rx="70" ry="12" fill="#000" opacity=".4" filter="url(#b10)"/>
{leaves}
<path d="M98 548 H202 L190 652 Q150 664 110 652 Z" fill="{paper}"/><path d="M98 548 H202 L190 652 Q150 664 110 652 Z" fill="url(#sides)"/>
<ellipse cx="150" cy="548" rx="52" ry="9" fill="#5a4636"/>
<ellipse cx="1060" cy="668" rx="76" ry="12" fill="#000" opacity=".4" filter="url(#b10)"/>
<path d="M1100 586 C1150 586 1150 640 1098 640" fill="none" stroke="{ink}" stroke-width="13"/>
<path d="M996 566 H1104 V650 Q1050 668 996 650 Z" fill="{ink}"/>
<clipPath id="mug"><path d="M996 566 H1104 V650 Q1050 668 996 650 Z"/></clipPath>
<g clip-path="url(#mug)">{img(mark, 1018, 584, 64, 64)}<rect x="990" y="560" width="120" height="110" fill="url(#sides)"/></g>
<ellipse cx="1050" cy="566" rx="54" ry="9" fill="#3a2a1d"/><ellipse cx="1050" cy="566" rx="54" ry="9" fill="none" stroke="#fff" stroke-opacity=".2" stroke-width="2"/>
<g filter="url(#b10)" opacity=".5"><path d="M1036 548 C1022 520 1050 506 1036 476 M1064 548 C1050 520 1078 506 1064 476" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round"/></g>"""

    # ---- social profile on a phone
    tiles = []
    fills = [ink, accent, paper, support, ink, accent, paper, support, ink]
    for i in range(9):
        x, y = 406 + (i % 3) * 130, 404 + (i // 3) * 130
        tiles.append(f'<rect x="{x}" y="{y}" width="128" height="128" fill="{fills[i]}"/>')
        if i in (0, 8):
            tiles.append(img(mark, x + 24, y + 24, 80, 80))
        elif i == 4 and art:
            tiles.append(img("../illustration.svg", x + 4, y + 20, 120, 85))
    profile = f"""{FX}{studio}{floor}
<ellipse cx="600" cy="866" rx="210" ry="18" fill="#000" opacity=".45" filter="url(#b24)"/>
<rect x="404" y="44" width="420" height="840" rx="62" fill="#000" opacity=".25" filter="url(#b24)"/>
<rect x="386" y="22" width="428" height="848" rx="64" fill="url(#metal)"/>
<rect x="382" y="180" width="5" height="60" rx="2" fill="#2a2a2c"/><rect x="382" y="260" width="5" height="60" rx="2" fill="#2a2a2c"/><rect x="813" y="220" width="5" height="90" rx="2" fill="#2a2a2c"/>
<rect x="398" y="34" width="404" height="824" rx="54" fill="#050505"/>
<clipPath id="ph"><rect x="406" y="42" width="388" height="808" rx="48"/></clipPath>
<g clip-path="url(#ph)"><rect x="406" y="42" width="388" height="808" fill="#ffffff"/>
{text(440, 78, "9:41", 15, "#111111")}<rect x="738" y="66" width="26" height="12" rx="3" fill="none" stroke="#111" stroke-width="1.5"/><rect x="741" y="69" width="18" height="6" rx="1" fill="#111"/>
<rect x="545" y="56" width="110" height="32" rx="16" fill="#000"/>
{text(600, 126, "@" + handle, 18, "#111111", "middle")}
<clipPath id="av"><circle cx="472" cy="196" r="46"/></clipPath>{img("../logo.svg", 426, 150, 92, 92, ' clip-path="url(#av)"')}
{text(584, 190, "128", 18, "#111111", "middle")}{text(664, 190, "8.4K", 18, "#111111", "middle")}{text(744, 190, "212", 18, "#111111", "middle")}
{text(584, 210, "posts", 12, "#666666", "middle")}{text(664, 210, "followers", 12, "#666666", "middle")}{text(744, 210, "following", 12, "#666666", "middle")}
{_wordmark(d, name, 19, "#111111", 426, 278, "start")}
<text x="426" y="302" {_font(t, 14, "#333333")}>{tag}</text>
<rect x="426" y="326" width="348" height="40" rx="10" fill="{accent}"/>{text(600, 352, "Follow", 15, on_accent, "middle")}
{"".join(tiles)}
<path d="M406 42 L700 42 L406 520 Z" fill="#fff" opacity=".07"/></g>"""

    # ---- T-shirt on a hanger
    tee = ("M528 170 C496 182 458 190 420 202 L316 286 Q340 350 370 404 L446 368 C440 500 432 640 434 768 "
           "Q600 784 766 768 C768 640 760 500 754 368 L830 404 Q860 350 884 286 L780 202 C742 190 704 182 672 170 "
           "C650 200 550 200 528 170 Z")
    tshirt = f"""{FX}{studio}
<path d="M600 170 V138 C600 114 630 110 634 130" fill="none" stroke="#9a9a9e" stroke-width="6" stroke-linecap="round"/>
<path d="{tee}" transform="translate(16 30)" fill="#000" opacity=".30" filter="url(#b24)"/>
<path d="M412 212 Q600 158 788 212" fill="none" stroke="#8c6a46" stroke-width="16" stroke-linecap="round"/>
<path d="{tee}" fill="{ink}"/>
<clipPath id="tee"><path d="{tee}"/></clipPath>
<g clip-path="url(#tee)">
{img(mark, 545, 268, 110, 110, ' opacity=".96"')}{_wordmark(d, name, _fit(d, name, 230, 30), paper, 600, 424)}
<g filter="url(#b10)" fill="none" stroke-linecap="round">
<path d="M505 400 C522 520 498 640 515 780" stroke="#000" stroke-opacity=".30" stroke-width="26"/>
<path d="M694 420 C680 540 704 660 688 780" stroke="#000" stroke-opacity=".26" stroke-width="22"/>
<path d="M446 368 C474 388 500 394 524 394 M754 368 C726 388 700 394 676 394" stroke="#000" stroke-opacity=".35" stroke-width="12"/>
<path d="M340 336 C375 336 405 326 432 310 M860 336 C825 336 795 326 768 310" stroke="#000" stroke-opacity=".30" stroke-width="10"/>
<path d="M545 460 C556 580 542 680 552 770" stroke="#fff" stroke-opacity=".10" stroke-width="30"/>
<path d="M650 470 C640 590 656 690 646 770" stroke="#fff" stroke-opacity=".08" stroke-width="24"/>
<path d="M430 232 C520 262 680 262 770 232" stroke="#fff" stroke-opacity=".08" stroke-width="30"/>
</g>
{full} fill="url(#sides)" opacity=".9"/>{full} fill="url(#light)"/>{full} filter="url(#canvas)"/></g>
<path d="M528 170 C560 158 640 158 672 170 C650 186 550 186 528 170 Z" fill="#000" opacity=".45"/>
<path d="M528 170 C550 202 650 202 672 170" fill="none" stroke="#000" stroke-opacity=".28" stroke-width="16"/>
<path d="M531 176 C553 205 647 205 669 176" fill="none" stroke="#fff" stroke-opacity=".10" stroke-width="2"/>
<path d="M438 752 Q600 768 762 752" fill="none" stroke="#fff" stroke-opacity=".14" stroke-width="2" stroke-dasharray="7 6"/>
<path d="M376 388 L443 356 M824 388 L757 356" fill="none" stroke="#fff" stroke-opacity=".14" stroke-width="2" stroke-dasharray="7 6"/>"""

    # ---- tote bag hanging on a wall peg
    bag = "M378 300 H822 L842 812 Q600 830 358 812 Z"
    straps = "M470 304 C468 200 556 124 596 116 M730 304 C732 200 644 124 604 116"
    tote = f"""{FX}{studio}
<path d="{bag}" transform="translate(20 26)" fill="#000" opacity=".22" filter="url(#b24)"/>
<path d="{straps}" transform="translate(10 14)" fill="none" stroke="#000" stroke-opacity=".18" stroke-width="28" filter="url(#b10)"/>
<path d="{straps}" fill="none" stroke="{support}" stroke-width="28" stroke-linecap="round"/>
<path d="M462 304 C460 196 552 116 594 108 M738 304 C740 196 648 116 606 108" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-dasharray="6 6"/>
<path d="M478 304 C476 204 560 132 598 124 M722 304 C724 204 640 132 602 124" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-dasharray="6 6"/>
<circle cx="600" cy="112" r="20" fill="#7b5c3d"/><circle cx="594" cy="106" r="7" fill="#fff" opacity=".25"/>
<path d="{bag}" fill="{paper}"/>
<clipPath id="bag"><path d="{bag}"/></clipPath>
<g clip-path="url(#bag)">
<g style="mix-blend-mode:multiply">{img(light, 470, 400, 260, 260)}</g>
{_wordmark(d, name, _fit(d, name, 360, 46), ink, 600, 720)}
{text(600, 756, c["tagline"], 17, support, "middle")}
<rect x="340" y="300" width="520" height="34" fill="#000" opacity=".06"/>
<path d="M378 328 H822" stroke="#000" stroke-opacity=".25" stroke-width="2" stroke-dasharray="6 6"/>
<g filter="url(#b10)" fill="none" stroke-linecap="round">
<path d="M470 336 C480 420 470 470 452 520" stroke="#000" stroke-opacity=".12" stroke-width="20"/>
<path d="M730 336 C722 420 734 470 752 520" stroke="#000" stroke-opacity=".12" stroke-width="20"/>
<path d="M420 640 C520 690 700 700 790 660" stroke="#000" stroke-opacity=".08" stroke-width="26"/>
<path d="M600 340 C590 420 610 480 600 560" stroke="#fff" stroke-opacity=".16" stroke-width="40"/>
</g>
{full} fill="url(#sides)" opacity=".55"/>{full} fill="url(#light)"/>{full} filter="url(#canvas)"/></g>
<rect x="455" y="300" width="32" height="34" fill="none" stroke="#000" stroke-opacity=".25" stroke-width="2" stroke-dasharray="4 4"/>
<rect x="713" y="300" width="32" height="34" fill="none" stroke="#000" stroke-opacity=".25" stroke-width="2" stroke-dasharray="4 4"/>"""

    # ---- two business cards lying on a desk
    def card(fill, body, clip_id):
        return (f'<rect x="4" y="12" width="520" height="300" rx="14" fill="#000" opacity=".35" filter="url(#b10)"/>'
                f'<rect x="0" y="4" width="520" height="300" rx="14" fill="#000" opacity=".25"/>'
                f'<rect width="520" height="300" rx="14" fill="{fill}"/>'
                f'<clipPath id="{clip_id}"><rect width="520" height="300" rx="14"/></clipPath>'
                f'<g clip-path="url(#{clip_id})">{body}<rect width="520" height="300" fill="url(#sheen)"/>'
                f'<rect width="520" height="300" filter="url(#grain)"/></g>')
    back = card(ink, img(mark, 185, 75, 150, 150), "cb")
    front = card(paper, f"""{_wordmark(d, name, _fit(d, name, 420, 40), ink, 44, 110, "start")}
<text x="44" y="142" {_font(t, 16, support)}>{tag}</text><rect x="44" y="168" width="56" height="4" fill="{accent}"/>
{text(44, 228, "@" + handle, 17, ink)}{text(44, 258, domain, 17, support)}""", "cf")
    business = f"""{FX}{studio}{full} filter="url(#grain)"/>
<g transform="translate(180 250) rotate(-9) skewX(6) scale(1 .9)">{back}</g>
<g transform="translate(470 360) rotate(6) skewX(-4) scale(1 .9)">{front}</g>"""

    # ---- shop window, close up: blurred warm interior, a logo sticker and gold lettering on the glass
    bokeh = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#bokeh)" opacity="{o}"/>'
                    for x, y, r, o in ((170, 150, 60, .9), (330, 110, 36, .7), (520, 170, 80, .55), (760, 120, 46, .8),
                                       (930, 180, 70, .6), (1060, 110, 40, .7), (260, 300, 30, .5), (880, 330, 34, .45),
                                       (640, 90, 28, .6), (1010, 420, 50, .35), (120, 470, 44, .4)))
    jars = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" opacity=".85"/>'
                   for x, y, w, h, f in ((120, 330, 70, 110, support), (205, 350, 60, 90, accent), (280, 320, 80, 120, paper),
                                         (850, 336, 64, 104, accent), (930, 316, 84, 124, support), (1030, 346, 56, 94, paper)))
    storefront = f"""{FX}<defs>
<radialGradient id="room" cx=".5" cy=".3" r=".9"><stop offset="0" stop-color="#7a5a3c"/><stop offset=".55" stop-color="#3a2a1d"/><stop offset="1" stop-color="#140e09"/></radialGradient>
<radialGradient id="bokeh"><stop offset="0" stop-color="#ffdca6" stop-opacity=".9"/><stop offset=".7" stop-color="#ffcf8a" stop-opacity=".35"/><stop offset="1" stop-color="#ffcf8a" stop-opacity="0"/></radialGradient>
<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6dfa0"/><stop offset=".5" stop-color="{accent}"/><stop offset="1" stop-color="#8a6326"/></linearGradient>
<linearGradient id="refl" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".14"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="dof" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="9"/></filter>
</defs>
<rect width="1200" height="900" fill="url(#room)"/>
<g filter="url(#dof)">
<rect x="80" y="440" width="1040" height="18" fill="#000" opacity=".4"/>{jars}
<rect x="60" y="520" width="1080" height="400" fill="{support}" opacity=".7"/>
<rect x="60" y="520" width="1080" height="20" fill="#fff" opacity=".12"/>
<path d="M300 0 V70 M600 0 V50 M900 0 V80" stroke="#000" stroke-width="4" opacity=".6"/>
<path d="M270 70 H330 L318 100 H282 Z M570 50 H630 L618 80 H582 Z M870 80 H930 L918 110 H882 Z" fill="#2a1d14"/>
<ellipse cx="300" cy="104" rx="40" ry="16" fill="#ffd28a"/><ellipse cx="600" cy="84" rx="40" ry="16" fill="#ffd28a"/><ellipse cx="900" cy="114" rx="40" ry="16" fill="#ffd28a"/>
</g>
<g filter="url(#b10)">{bokeh}</g>
<path d="M-100 900 L420 0 L620 0 L100 900 Z" fill="url(#refl)"/>
<path d="M560 900 L960 0 L1010 0 L610 900 Z" fill="url(#refl)" opacity=".7"/>
<path d="M0 0 L1200 0 L1200 140 Q600 220 0 120 Z" fill="#fff" opacity=".05"/>
<circle cx="606" cy="318" r="128" fill="#000" opacity=".35" filter="url(#b10)"/>
<circle cx="600" cy="310" r="128" fill="{paper}"/>
<clipPath id="stk"><circle cx="600" cy="310" r="116"/></clipPath>{img("../logo.svg", 484, 194, 232, 232, ' clip-path="url(#stk)"')}
<circle cx="600" cy="310" r="128" fill="url(#sheen)"/>
{_wordmark(d, name, _fit(d, name, 720, 78), "url(#gold)", 600, 548)}
<text x="600" y="596" text-anchor="middle" {_font(t, 22, paper, ' opacity=".85"')}>{tag}</text>
<text x="600" y="652" text-anchor="middle" letter-spacing="5" {_font(t, 16, paper, ' opacity=".7"')}>OPEN DAILY  ·  07.00 – 22.00</text>
<rect x="0" y="0" width="34" height="900" fill="#1a1a1a"/><rect x="34" y="0" width="6" height="900" fill="#fff" opacity=".12"/>
<rect x="1166" y="0" width="34" height="900" fill="#1a1a1a"/><rect x="1160" y="0" width="6" height="900" fill="#000" opacity=".4"/>
<rect x="0" y="790" width="1200" height="110" fill="#8f877c"/><rect x="0" y="790" width="1200" height="110" filter="url(#grain)"/>
<rect x="0" y="790" width="1200" height="8" fill="#fff" opacity=".35"/><rect x="0" y="798" width="1200" height="30" fill="#000" opacity=".18" filter="url(#b10)"/>
{full} filter="url(#grain)" opacity=".6"/>"""

    svgs = {"website": website, "social-profile": profile, "tote-bag": tote, "business-card": business,
            "t-shirt": tshirt, "storefront": storefront}
    return {k: f'<svg xmlns="http://www.w3.org/2000/svg" width="{MOCK_W}" height="{MOCK_H}" '
               f'viewBox="0 0 {MOCK_W} {MOCK_H}">{v}</svg>\n' for k, v in svgs.items()}


PAGE_FX = """<defs>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.10"/></feComponentTransfer></filter>
<radialGradient id="glow"><stop offset="0" stop-color="{accent}" stop-opacity=".38"/><stop offset=".6" stop-color="{accent}" stop-opacity=".08"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>
<radialGradient id="vignette" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient>
<linearGradient id="fadeL" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".35" stop-color="#fff" stop-opacity="1"/></linearGradient>
<linearGradient id="fadeB" x1="0" y1="0" x2="0" y2="1"><stop offset=".55" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".18"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>"""

AUTO = "<!--brand-kickstart:auto-->"  # pages without this marker were written by hand and are never overwritten
# name -> (width, height, safe area x, y, w, h): the part every device shows
STANDARD_PAGES = {
    "youtube-banner": (2560, 1440, 507, 508, 1546, 423),
    "facebook-cover": (1640, 624, 265, 70, 1110, 484),
    "x-header": (1500, 500, 300, 60, 1050, 340),
    "github-social-preview": (1280, 640, 80, 80, 1120, 480),
    "video-cover": (1080, 1920, 0, 285, 1080, 1350),
    "ig-highlight": (1080, 1920, 140, 560, 800, 800),
}


def _page(W, H, body, accent):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{AUTO}'
            f'{PAGE_FX.replace("{accent}", accent)}{body}'
            f'<rect width="{W}" height="{H}" fill="url(#vignette)"/><rect width="{W}" height="{H}" filter="url(#grain)"/></svg>\n')


def _wide_banner(c, handle, domain, W, H, sx, sy, sw, sh, art, mark):
    """Lockup on the left of the safe area, the illustration fading in on the right."""
    ink, paper, accent = (_esc(c["colors"][k]) for k in ("ink", "paper", "accent"))
    d, t, name = c["display"], c["text"], c["name"]
    s = int(min(sh * 0.42, 260))                    # logo size
    x0 = sx + int(sw * 0.03)
    tx = x0 + int(s * 1.2)                          # text column
    text_end = sx + int(sw * 0.64)
    size = _fit(d, name, text_end - tx, int(s * 0.8))
    cy = sy + sh // 2
    # the illustration gets the room right of the text column; it may run past the safe area, it is decoration
    room = W - text_end - int(sw * 0.02)
    art_w = int(min(room, sh * 1.25 * 380 / 270))
    art_h = int(art_w * 270 / 380)
    ax = text_end + int(sw * 0.02) + max(0, (room - art_w) // 3)
    ay = cy - art_h // 2
    art_layer = (f'<mask id="fade"><rect x="{ax}" y="{ay}" width="{art_w}" height="{art_h}" fill="url(#fadeL)"/></mask>'
                 f'<image href="../illustration.svg" x="{ax}" y="{ay}" width="{art_w}" height="{art_h}" mask="url(#fade)"/>'
                 if art else
                 f'<image href="{mark}" x="{sx + sw - int(sh * 1.1)}" y="{cy - int(sh * 0.55)}" width="{int(sh * 1.1)}" '
                 f'height="{int(sh * 1.1)}" opacity=".12"/>')
    meta = f"@{handle} · {domain}"
    return f"""<rect width="{W}" height="{H}" fill="{ink}"/>
<circle cx="{ax + art_w // 2}" cy="{cy}" r="{sh * 1.4:.0f}" fill="url(#glow)"/>
{art_layer}
<!--lockup-->
<rect x="{x0 + 6}" y="{cy - s // 2 + 10}" width="{s}" height="{s}" rx="{s * 0.24:.0f}" fill="#000" opacity=".35"/>
<image href="../logo.svg" x="{x0}" y="{cy - s // 2}" width="{s}" height="{s}"/>
{_wordmark(d, name, size, paper, tx, cy - int(size * 0.08), "start")}
<rect x="{tx}" y="{cy + int(size * 0.24)}" width="{int(size * 0.9)}" height="{max(3, size // 22)}" fill="{accent}"/>
<text x="{tx}" y="{cy + int(size * 0.24) + int(size * 0.56)}" {_font(t, max(16, int(size * 0.36)), paper, ' opacity=".9"')}>{_esc(c["tagline"])}</text>
<text x="{tx}" y="{cy + int(size * 0.24) + int(size * 1.02)}" letter-spacing="{max(1, size // 40)}" {_font(t, max(13, int(size * 0.22)), paper, ' opacity=".6"')}>{_esc(meta)}</text>
<!--/lockup-->"""


def default_pages(directory):
    """Write the standard banners and covers from brand.json; a page the agent already wrote is kept."""
    c, handle, domain = _brand(directory)
    accent, ink, paper = (_esc(c["colors"][k]) for k in ("accent", "ink", "paper"))
    d, t, name = c["display"], c["text"], c["name"]
    art = os.path.exists(os.path.join(directory, "illustration.svg"))
    mark = "../logo.svg"
    os.makedirs(os.path.join(directory, "pages"), exist_ok=True)
    written = []
    for key, (W, H, sx, sy, sw, sh) in STANDARD_PAGES.items():
        path = os.path.join(directory, "pages", f"{key}-{W}x{H}.svg")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if AUTO not in f.read():
                    continue  # the agent wrote this one
        if key == "video-cover":
            size = _fit(d, name, 860, 120)
            body = f"""<rect width="{W}" height="{H}" fill="{ink}"/>
<circle cx="540" cy="700" r="760" fill="url(#glow)"/>
{f'<mask id="fade"><rect x="60" y="300" width="960" height="682" fill="url(#fadeB)"/></mask><image href="../illustration.svg" x="60" y="300" width="960" height="682" mask="url(#fade)"/>' if art else ''}
<rect x="430" y="1000" width="220" height="220" rx="52" fill="#000" opacity=".35" transform="translate(6 12)"/>
<image href="../logo.svg" x="430" y="1000" width="220" height="220"/>
{_wordmark(d, name, size, paper, 540, 1330)}
<rect x="490" y="1366" width="100" height="5" fill="{accent}"/>
<text x="540" y="1426" text-anchor="middle" {_font(t, 38, paper, ' opacity=".9"')}>{_esc(c["tagline"])}</text>
<text x="540" y="1560" text-anchor="middle" letter-spacing="6" {_font(t, 26, paper, ' opacity=".55"')}>{_esc(("@" + handle).upper())}</text>"""
        elif key == "ig-highlight":
            body = f"""<rect width="{W}" height="{H}" fill="{ink}"/>
<circle cx="540" cy="960" r="560" fill="url(#glow)"/>
<circle cx="540" cy="960" r="400" fill="none" stroke="{accent}" stroke-opacity=".35" stroke-width="6"/>
<image href="../logo.svg" x="320" y="740" width="440" height="440"/>"""
        else:
            body = _wide_banner(c, handle, domain, W, H, sx, sy, sw, sh, art, mark)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_page(W, H, body, accent))
        written.append(path)
    return written


def build_wordmarks(directory, render):
    """logo/wordmark-dark.png (ink, for light backgrounds) and -light.png (paper), when there is a wordmark.svg."""
    c = _brand(directory)[0]
    logotype = c["display"]["_logotype"]
    if not logotype:
        return []
    vw, vh, inner = logotype
    w, h = 1600, int(1600 * vh / vw)
    out = []
    for key, color in (("dark", "ink"), ("light", "paper")):
        svg = os.path.join(directory, "logo", f"wordmark-{key}.svg")
        _write(directory, os.path.relpath(svg, directory),
               f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {vw:g} {vh:g}">'
               f'{inner.replace("currentColor", _esc(c["colors"][color]))}</svg>'.encode())
        out.append(svg[:-4] + ".png")
        _write(directory, os.path.relpath(out[-1], directory), render(svg, w, h))
    return out


def build_mockups(directory, render):
    """The picked logo on a website, a profile, a tote bag, a card, a shirt and a shop window."""
    folder = os.path.join(directory, "mockups")
    os.makedirs(folder, exist_ok=True)
    out = []
    for key, svg in _mockup_svgs(directory).items():
        path = os.path.join(folder, f"{key}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        out.append(os.path.join(folder, f"{key}.png"))
        _write(directory, f"mockups/{key}.png", render(path, MOCK_W, MOCK_H))
    tw, th = MOCK_W * 2 // 3, MOCK_H * 2 // 3
    tiles = "".join(f'<image href="{k}.png" x="{i % 3 * tw}" y="{i // 3 * th}" width="{tw}" height="{th}"/>'
                    for i, k in enumerate(MOCKUPS))
    overview = os.path.join(folder, "all.svg")
    with open(overview, "w", encoding="utf-8") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{3 * tw}" height="{2 * th}">{tiles}</svg>')
    out.append(os.path.join(folder, "all.png"))
    _write(directory, "mockups/all.png", render(overview, 3 * tw, 2 * th))
    return out


def build_palette(directory, render):
    c = _brand(directory)[0]
    t = c["text"]
    cells = "".join(
        f'<rect x="{i * 300}" y="0" width="300" height="240" fill="{_esc(c["colors"][k])}"/>'
        f'<text x="{i * 300 + 24}" y="44" letter-spacing="2" {_font(t, 15, on_color(c["colors"][k]))}>{k.upper()}</text>'
        f'<text x="{i * 300 + 24}" y="210" {_font(t, 26, on_color(c["colors"][k]))}>{_esc(c["colors"][k])}</text>'
        for i, k in enumerate(COLOR_KEYS))
    path = os.path.join(directory, "palette.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="240">{cells}</svg>')
    _write(directory, "palette.png", render(path, 1200, 240))
    return os.path.join(directory, "palette.png")


def _luminance(hex_color):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _hex(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """WCAG contrast ratio, 1 to 21. Text needs 4.5 or more."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


UPLOADS = [  # file name prefix -> where it goes
    ("logo/logo-1080", "Profile picture on every platform"),
    ("logo/logo-512", "Website header, documents, email signature"),
    ("logo/wordmark-dark", "Wordmark on light backgrounds: website header, documents, print"),
    ("logo/wordmark-light", "Wordmark on dark backgrounds"),
    ("favicon/", "Copy to the website root, then paste `favicon/head.html` into `<head>`"),
    ("app/app-store", "App Store Connect: app icon"),
    ("app/play-store", "Play Console: Store listing, app icon"),
    ("social/youtube-banner", "YouTube Studio: Customization, Branding, Banner image"),
    ("social/facebook-cover", "Facebook Page: Edit cover photo"),
    ("social/x-header", "X: Edit profile, Header"),
    ("social/play-feature-graphic", "Play Console: Store listing, Feature graphic"),
    ("social/github-social-preview", "GitHub repo: Settings, Social preview"),
    ("social/video-cover", "Cover for TikTok, Reels and Shorts"),
    ("social/ig-highlight", "Instagram: Highlight, Edit cover"),
]


def write_brand_md(directory):
    """BRAND.md: the one page to hand a designer, a printer or a new teammate."""
    c, handle, domain = _brand(directory)
    col = c["colors"]
    files = sorted(os.path.relpath(os.path.join(r, f), directory).replace(os.sep, "/")
                   for sub in ("logo", "favicon", "app", "social") for r, _, fs in os.walk(os.path.join(directory, sub))
                   for f in fs)
    logo_img = "logo/logo-512.png" if "logo/logo-512.png" in files else "logo.svg"
    use = {"ink": "Text and dark backgrounds", "paper": "Light backgrounds",
           "accent": "Buttons, links and highlights; keep it to about 10% of a layout",
           "support": "Secondary text, lines and details"}
    rows = "\n".join(f"| {k.title()} | `{col[k]}` | {', '.join(str(v) for v in _hex(col[k]))} | {use[k]} |"
                     for k in COLOR_KEYS)
    pairs = [("ink", "paper"), ("accent", "ink"), ("accent", "paper"), ("support", "paper")]
    contrast = "\n".join(f"- {a.title()} on {b}: {contrast_ratio(col[a], col[b]):.1f}:1"
                         f"{'' if contrast_ratio(col[a], col[b]) >= 4.5 else ' (too low for body text; large text or decoration only)'}"
                         for a, b in pairs)
    fonts = "\n".join(f"| {role} | {f['family']} | {f.get('weight', 400)}{' italic' if f.get('style') == 'italic' else ''} "
                      f"| https://fonts.google.com/specimen/{f['family'].replace(' ', '+')} |"
                      for role, f in (("Display", c["display"]), ("Text", c["text"])))
    wordmark = ("all capitals, " if c["display"].get("case") == "upper" else "") + (
        f"letter-spacing {c['display']['tracking']}em" if c["display"].get("tracking") else "default letter-spacing")
    file_rows, favicons = [], [f for f in files if f.startswith("favicon/")]
    for rel in [f for f in files if not f.startswith("favicon/")] + (["favicon/"] if favicons else []):
        dest = next((d for prefix, d in UPLOADS if rel.startswith(prefix)), "")
        label = f"`favicon/` ({len(favicons)} files)" if rel == "favicon/" else f"`{rel}`"
        file_rows.append(f"| {label} | {dest} |")
    files_md = ("| File | Where it goes |\n|---|---|\n" + "\n".join(file_rows)) if file_rows else \
        "Run `brand.py render` to add the profile picture, favicons, app icons and banners."
    extra = "\n".join(x for x in (
        f"- `mark.svg`: the mark without its background, for merch and print" if os.path.exists(os.path.join(directory, "mark.svg")) else "",
        f"- `wordmark.svg`: the drawn wordmark; use it wherever the name appears as a logo, never retype the name" if os.path.exists(os.path.join(directory, "wordmark.svg")) else "",
        f"- `illustration.svg`: the brand illustration for banners and covers" if os.path.exists(os.path.join(directory, "illustration.svg")) else "",
    ) if x)
    md = f"""# {c['name']}

> {c['tagline']}

<img src="{logo_img}" alt="{c['name']} logo" width="160">

**Handle:** @{handle} · **Domain:** {domain} · **Style:** {c['title']} (`{c.get('concept', '')}`)

{c['why']}

## Logo

- `logo.svg`: the master file. Every PNG is rendered from it.
{extra}
- **Clear space:** keep empty space around the logo of at least a quarter of its width.
- **Minimum size:** 16 px on screen (it is drawn to read at favicon size), 15 mm in print.
- **Backgrounds:** use it on ink or paper. On photos, put it on a solid ink or paper block.
- **Do not:** stretch it, recolor it outside the palette, add shadows or outlines, or rotate it.

## Colors

![Palette](palette.png)

| Role | Hex | RGB | Use |
|---|---|---|---|
{rows}

Contrast (WCAG; body text needs 4.5:1 or more):
{contrast}

## Typography

| Role | Font | Weight | Get it |
|---|---|---|---|
{fonts}

Wordmark: {c['display']['family']}, {wordmark}. Write the name as **{c['name']}**.

## Mockups

![The logo in use](mockups/all.png)

Website, social profile, tote bag, business card, T-shirt and shop window. The sources are in `mockups/`.

## Files

{files_md}

---
Generated by brand-kickstart. Change `brand.json` or the SVG files, then run `brand.py render` again.
"""
    with open(os.path.join(directory, "BRAND.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return os.path.join(directory, "BRAND.md")



def main(argv=None):
    p = argparse.ArgumentParser(description="Logo, favicons, app icons and social images from a brand folder.")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fonts", help="download Google Fonts as TTF into <dir>/fonts")
    f.add_argument("dir")
    f.add_argument("families", nargs="+", help='e.g. "Plus Jakarta Sans:wght@800"')
    b = sub.add_parser("board", help="render style options in <dir>/concepts for the user to pick")
    b.add_argument("dir")
    k = sub.add_parser("pick", help="make one concept the brand: brand.json, fonts, mockups, BRAND.md")
    k.add_argument("dir")
    k.add_argument("concept", help="concept id, e.g. a-warm-kitchen")
    k.add_argument("--handle", help="the handle the user secured, e.g. seduhpagi")
    k.add_argument("--domain", help="the domain, e.g. seduhpagi.id")
    r = sub.add_parser("render", help="render every PNG")
    r.add_argument("dir")
    r.add_argument("--name", help="display name for site.webmanifest (default: from brand.json)")
    r.add_argument("--color", help="brand background color, e.g. #13161d (manifest, App Store icon fill)")
    a = p.parse_args(argv)

    if a.cmd == "fonts":
        try:
            for path in download_fonts(a.dir, a.families):
                print(path)
        except (OSError, RuntimeError) as e:
            print(e, file=sys.stderr)
            return 1
        return 0

    try:
        render = resvg_render(os.path.join(a.dir, "fonts"))
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        return 2
    if a.cmd == "pick":
        try:
            for path in pick(a.dir, a.concept, render, handle=a.handle, domain=a.domain):
                print(path)
            print(os.path.join(a.dir, "BRAND.md"))
        except (RuntimeError, OSError, ValueError) as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    if a.cmd == "board":
        try:
            for path in build_boards(a.dir, render):
                print(path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    name, color = kit_defaults(a.dir)
    name, color = a.name or name, a.color or color
    if not name:
        print("No brand.json yet: run `pick` first, or pass --name", file=sys.stderr)
        return 1
    try:
        if os.path.exists(os.path.join(a.dir, "brand.json")):
            default_pages(a.dir)  # standard banners; pages/ files the agent wrote are kept
        skipped = build(a.dir, name, color, render)
        if os.path.exists(os.path.join(a.dir, "brand.json")):
            finish(a.dir, render)  # refresh mockups and BRAND.md, which now lists the new files
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    for page in skipped:
        print(f"skipped pages/{page}: name it <what>-<W>x<H>.svg to render it", file=sys.stderr)
    for sub_dir in ("logo", "favicon", "app", "social", "mockups"):
        folder = os.path.join(a.dir, sub_dir)
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            print(os.path.join(folder, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
