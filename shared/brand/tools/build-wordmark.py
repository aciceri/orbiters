#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["fonttools>=4.60", "uharfbuzz>=0.56"]
# ///
"""Draw the wordmark, as outlines, from the face the brand decided on.

The word «rebase» is set once here and committed as `wordmark.svg` and `lockup.svg`
next to this script, so nothing downstream loads a second webfont: the two surfaces
that draw the brand use the paths, and `--font-sans` (Outfit) stays the only family
the product ships. That also removes the one FOUT nobody can accept, on the string a
visitor uses to tell whether they are on the right site.

The face is Space Grotesk 700 (SIL OFL 1.1, Florian Karsten), picked on 2026-09-14
(`docs/design/DECISIONS.md`). The source is the variable font from google/fonts, which
this script fetches and checksums rather than committing: the artefacts are the SVGs,
and a font nobody serves has no business in the dependency graph. Run it only when the
face, the weight or the tracking changes.

    ./shared/brand/tools/build-wordmark.py

Kerning comes from the font's own GPOS through HarfBuzz, not from an average
letter-spacing: at display size the `re` and `se` pairs are what a hand-spaced wordmark
would be judged on.
"""

from __future__ import annotations

import hashlib
import urllib.request
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf"
FONT_SHA256 = "acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72"

WORD = "rebase"
WEIGHT = 700
# -0.035em. A wordmark is read as one shape, so it is set tighter than the same face
# would be in a paragraph; past about -0.05em the `rb` pair starts to touch.
TRACKING = -0.035

BRAND = Path(__file__).resolve().parent.parent
PALETTE = BRAND / "palette.css"


def source_font() -> bytes:
    """The variable TTF, fetched and checksummed, cached outside the repository."""
    cache = Path(gettempdir()) / f"SpaceGrotesk-{FONT_SHA256[:12]}.ttf"
    if cache.is_file() and hashlib.sha256(cache.read_bytes()).hexdigest() == FONT_SHA256:
        return cache.read_bytes()
    with urllib.request.urlopen(FONT_URL) as response:  # noqa: S310 - literal https URL
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != FONT_SHA256:
        raise SystemExit(f"{FONT_URL} is not the font this wordmark was drawn from: {digest}")
    cache.write_bytes(data)
    return data


def palette(token: str) -> str:
    """One colour, read from the single source rather than spelled out here."""
    for line in PALETTE.read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition(":")
        if name == token:
            return value.strip().rstrip(";")
    raise SystemExit(f"{token} is not in {PALETTE.name}")


Placed = list[tuple[str, float, float]]
Box = tuple[float, float, float, float]


def shape(font_bytes: bytes) -> Placed:
    """Every glyph of the word with the pen origin it is drawn from."""
    face = hb.Face(font_bytes)
    hb_font = hb.Font(face)
    hb_font.set_variations({"wght": WEIGHT})
    buf = hb.Buffer()
    buf.add_str(WORD)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    upem = face.upem
    tracking = TRACKING * upem
    order = hb_font.glyph_to_string
    placed: Placed = []
    pen_x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        placed.append((order(info.codepoint), pen_x + pos.x_offset, pos.y_offset))
        pen_x += pos.x_advance + tracking
    return placed


def word_path(font: TTFont, placed: Placed) -> tuple[str, Box]:
    """The whole word as one `d`, in SVG coordinates, plus its tight bounding box."""
    glyphs = font.getGlyphSet()
    parts: list[str] = []
    bounds = BoundsPen(glyphs)
    for name, x, y in placed:
        pen = SVGPathPen(glyphs, ntos=lambda v: f"{round(v, 1):g}")
        # SVG's y grows downwards, the font's upwards: flip, and put the baseline at
        # y=0 so a consumer can align the word without reading this file.
        transform = (1, 0, 0, -1, x, -y)
        glyphs[name].draw(TransformPen(pen, transform))
        glyphs[name].draw(TransformPen(bounds, transform))
        if commands := pen.getCommands():
            parts.append(commands)
    if bounds.bounds is None:
        raise SystemExit(f"«{WORD}» drew nothing: the font has no outline for it")
    return " ".join(parts), bounds.bounds


def main() -> None:
    font_bytes = source_font()
    placed = shape(font_bytes)
    font = instantiateVariableFont(TTFont(BytesIO(font_bytes)), {"wght": WEIGHT})
    d, (x_min, y_min, x_max, y_max) = word_path(font, placed)
    ink = palette("--color-prussian-blue")
    paper = palette("--color-paper")
    gold = palette("--color-royal-gold")
    watermelon = palette("--color-watermelon")

    width = round(x_max - x_min, 1)
    height = round(y_max - y_min, 1)
    baseline = round(-y_min, 1)

    # The lockup: the mark standing on the baseline, cap height tall, then the word.
    # The tile and the gap are measured off the type rather than chosen, so the pair
    # holds at any size and a consumer only has to set one width.
    cap = font["OS/2"].sCapHeight
    tile = round(cap / 2, 1)
    gap = round(tile * 0.75, 1)
    mark_top = round(-cap - y_min, 1)
    word_x = round(cap + gap - x_min, 1)
    lockup_width = round(cap + gap + width, 1)

    def word(colour: str, x: float) -> str:
        return f'  <path transform="translate({x:g} {baseline:g})" fill="{colour}" d="{d}"/>\n'

    def svg(box_width: float, body: str, note: str) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box_width:g} {height:g}" '
            f'role="img" aria-label="{WORD}">\n'
            f"  <!-- {note}\n"
            f"       Generated by tools/build-wordmark.py; edit that, never this file. -->\n"
            f"  <title>{WORD}</title>\n"
            f"{body}"
            "</svg>\n"
        )

    def mark(ink_tile: str) -> str:
        # BRAND_TILES order: ink, royal gold, watermelon, ink. On a dark ground the
        # two ink tiles are the ground, which is the mark's own rule (mark.ts), so the
        # paper variant repaints them rather than inventing a fifth colour.
        tiles = [(0, 0, ink_tile), (tile, 0, gold), (0, tile, watermelon), (tile, tile, ink_tile)]
        rects = "\n".join(
            f'    <rect x="{tx:g}" y="{round(mark_top + ty, 1):g}" '
            f'width="{tile:g}" height="{tile:g}" fill="{fill}"/>'
            for tx, ty, fill in tiles
        )
        return f"  <g>\n{rects}\n  </g>\n"

    word_note = f"«{WORD}» in Space Grotesk {WEIGHT} at {TRACKING:g}em, as outlines."
    lockup_note = (
        f"The mark and the word, one file: the four tiles at cap height, then\n"
        f"       «{WORD}» in Space Grotesk {WEIGHT}. The tile order is BRAND_TILES in\n"
        f"       mark.ts and the colours are palette.css; both are asserted by\n"
        f"       projects/website/src/landing-style.test.ts."
    )
    on_dark = " The paper cut, for a dark ground."
    written = {
        "wordmark.svg": svg(width, word(ink, -x_min), word_note),
        "wordmark-paper.svg": svg(width, word(paper, -x_min), word_note + on_dark),
        "lockup.svg": svg(lockup_width, mark(ink) + word(ink, word_x), lockup_note),
        "lockup-paper.svg": svg(
            lockup_width, mark(paper) + word(paper, word_x), lockup_note + on_dark
        ),
    }
    for name, content in written.items():
        (BRAND / name).write_text(content, encoding="utf-8")
    print(f"wordmark {width:g}x{height:g}, lockup {lockup_width:g}x{height:g}, tile {tile:g}")


if __name__ == "__main__":
    main()
