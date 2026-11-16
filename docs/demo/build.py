"""Rebuild the README demos: python docs/demo/build.py

Needs resvg-py, internet for fonts, and the `usvg` CLI (brew install resvg, or cargo install usvg).
The README shows docs/demo/preview/*.svg: standalone SVGs with text turned into paths and every linked
image inlined, because GitHub shows an SVG without our fonts or the files it links to. PNGs are not committed.
"""
import base64
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIEW = HERE / "preview"
sys.path.insert(0, str(HERE.parents[1] / "skills" / "brand-kickstart" / "scripts"))
import brand  # noqa: E402

# demos that also go through pick + render: folder -> (concept id, handle, domain)
KITS = {"seduh-pagi": ("a-morning-ritual", "seduhpagi", "seduhpagi.id")}
# fonts a drawn wordmark.svg uses beyond its concept's display and text faces
EXTRA_FONTS = {"gallery": ["Libre Caslon Text:ital,wght@1,400"]}
_ids = itertools.count()
DATA_SVG = re.compile(r'<image\b([^>]*?)xlink:href="data:image/svg\+xml;base64,\s*([^"]+)"([^>]*)/>')


def _inline(svg):
    """Turn every <image> holding a base64 SVG into a nested <svg>, with its ids made unique."""
    def nest(m):
        doc = base64.b64decode(m.group(2)).decode()
        prefix = f"n{next(_ids)}-"
        doc = re.sub(r'\bid="', f'id="{prefix}', doc)
        doc = re.sub(r"url\(#", f"url(#{prefix}", doc)
        doc = re.sub(r'href="#', f'href="#{prefix}', doc)
        root, inner = re.search(r"<svg\b([^>]*)>(.*)</svg>", doc, re.S).groups()
        w, h = (re.search(rf'\b{k}="([\d.]+)"', root).group(1) for k in ("width", "height"))
        box = (m.group(1) + m.group(3)).strip()
        return f'<svg {box} viewBox="0 0 {w} {h}" preserveAspectRatio="none">{_inline(inner)}</svg>'
    return DATA_SVG.sub(nest, svg)


def standalone(src, out, fonts):
    """src SVG -> out SVG with no <text>, no fonts and no linked files."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["usvg", "--resources-dir", str(src.parent), "--skip-system-fonts", "--use-fonts-dir", str(fonts),
                    "--coordinates-precision", "2", "--transforms-precision", "4", "--indent", "none",
                    "--attrs-indent", "none", str(src), str(out)], check=True)
    svg = _inline(out.read_text())
    assert "<text" not in svg and "data:image/png" not in svg, out  # GitHub would drop these
    out.write_text(svg)
    return out


def overview(tiles, cols, tw, th, out, fonts):
    """Tile standalone SVGs into one, the way brand.py tiles the PNGs."""
    rows = -(-len(tiles) // cols)
    src = out.with_suffix(".src.svg")
    # boards use brand.py's grid (short last row centred); mockups fill a plain 3-column grid
    xy = [brand.tile_xy(i, len(tiles)) if cols == 2 else (i % cols * tw, i // cols * th) for i in range(len(tiles))]
    body = "".join(f'<image href="{t.relative_to(out.parent)}" x="{x}" y="{y}" width="{tw}" height="{th}"/>'
                   for t, (x, y) in zip(tiles, xy))
    src.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols * tw}" height="{rows * th}">'
                   f'<rect width="100%" height="100%" fill="#f4f4f2"/>{body}</svg>')
    standalone(src, out, fonts)
    src.unlink()
    return out


def previews(folder, fonts):
    """The standalone SVGs the README and the sample BRAND.md show."""
    tmp = PREVIEW / "tiles"
    boards = [standalone(b, tmp / f"{folder.name}-{b.parent.name}.svg", fonts)
              for b in sorted(folder.glob("concepts/*/board.svg"))]
    out = [overview(boards, 2, brand.BOARD_W // 2, brand.BOARD_H // 2, PREVIEW / f"{folder.name}-concepts.svg", fonts)]
    if folder.name in KITS:
        mocks = [standalone(folder / "mockups" / f"{k}.svg", tmp / f"{folder.name}-mock-{k}.svg", fonts)
                 for k in brand.MOCKUPS]
        out.append(overview(mocks, 3, brand.MOCK_W * 2 // 3, brand.MOCK_H * 2 // 3,
                            PREVIEW / f"{folder.name}-mockups.svg", fonts))
        for page in sorted((folder / "pages").glob("*.svg")):
            out.append(standalone(page, PREVIEW / f"{folder.name}-{page.name}", fonts))
        out.append(standalone(folder / "logo.svg", PREVIEW / f"{folder.name}-logo.svg", fonts))
        out.append(standalone(folder / "palette.svg", PREVIEW / f"{folder.name}-palette.svg", fonts))
        # the sample guide on GitHub shows the previews; a real kit's BRAND.md keeps its PNGs
        md = folder / "BRAND.md"
        text = md.read_text()
        for png, svg in (("logo/logo-512.png", "logo"), ("palette.png", "palette"), ("mockups/all.png", "mockups")):
            text = text.replace(f"]({png})", f"](../preview/{folder.name}-{svg}.svg)").replace(
                f'src="{png}"', f'src="../preview/{folder.name}-{svg}.svg"')
        md.write_text(text)
    shutil.rmtree(tmp)
    return out


if __name__ == "__main__":
    if not shutil.which("usvg"):
        sys.exit("usvg is missing: brew install resvg (or cargo install usvg)")
    for folder in sorted(p for p in HERE.iterdir() if (p / "concepts").is_dir()):
        concepts = [json.loads(f.read_text()) for f in sorted(folder.glob("concepts/*/concept.json"))]
        brand.download_fonts(str(folder), sorted({brand.font_spec(c[k]) for c in concepts for k in ("display", "text")}
                                                  | set(EXTRA_FONTS.get(folder.name, []))))
        render = brand.resvg_render(str(folder / "fonts"))
        for png in brand.build_boards(str(folder), render):
            print(png)
        if folder.name in KITS:
            cid, handle, domain = KITS[folder.name]
            brand.pick(str(folder), cid, render, handle=handle, domain=domain)
            brand.default_pages(str(folder))
            brand.build(str(folder), *brand.kit_defaults(str(folder)), render)
            brand.finish(str(folder), render)
            print(folder / "BRAND.md")
        for svg in previews(folder, folder / "fonts"):
            print(svg)
