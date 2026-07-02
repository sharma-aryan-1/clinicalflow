"""Render an animated terminal GIF of a `make all` pipeline run into docs/.

The transcript is the real, reproducible log output the pipeline emits for the
fixed Synthea seed (1234) — row counts, QA result, cohort stats. It's a rendered
recreation (not a screen capture) so it stays small and legible.

Usage:  python scripts/make_terminal_gif.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parents[1] / "docs"
DOCS.mkdir(exist_ok=True)
OUT = DOCS / "pipeline_run.gif"

# Palette (GitHub-dark-ish)
BG = (13, 17, 23)
BAR = (32, 37, 43)
WHITE = (230, 237, 243)
GRAY = (139, 148, 158)
GREEN = (63, 185, 80)
BLUE = (121, 192, 255)
CYAN = (86, 214, 214)

FONT_PATH = "C:/Windows/Fonts/consola.ttf"
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
SIZE = 16
PAD = 18
BAR_H = 30
LINE_H = 22


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:  # pragma: no cover
        return ImageFont.load_default()


FONT = _font(FONT_PATH, SIZE)
BFONT = _font(FONT_BOLD, SIZE)


def lbl(name: str) -> str:
    return f"  {name:<13}"


# Each line = (list of (text, color) segments, reveal-duration-ms)
LINES: list[tuple[list[tuple[str, tuple]], int]] = [
    ([("$ ", GREEN), ("make all", WHITE)], 700),
    ([("[ingest] ", CYAN), ("Ingesting 3450 FHIR bundles -> clinicalflow.duckdb", GRAY)], 500),
    ([("  ... processed 1150/3450 bundles", GRAY)], 300),
    ([("  ... processed 2300/3450 bundles", GRAY)], 300),
    ([("  ... processed 3450/3450 bundles", GRAY)], 300),
    ([("Row counts:", WHITE)], 200),
    ([(lbl("patients"), GRAY), ("3450", BLUE)], 130),
    ([(lbl("encounters"), GRAY), ("205566", BLUE)], 130),
    ([(lbl("conditions"), GRAY), ("129716", BLUE)], 130),
    ([(lbl("observations"), GRAY), ("2674521", BLUE)], 130),
    ([(lbl("medications"), GRAY), ("180891", BLUE)], 130),
    ([(lbl("procedures"), GRAY), ("579074", BLUE)], 130),
    ([("Ingestion complete.", GREEN)], 500),
    ([("[qa] ", CYAN), ("Running data-quality checks (error budget = 1%)", GRAY)], 400),
    ([("  [PASS] ", GREEN), ("Referential integrity   observations -> patients", GRAY)], 200),
    ([("  [PASS] ", GREEN), ("Value-range             Systolic BP (8480-6)", GRAY)], 200),
    ([("QA complete: ", WHITE), ("28 checks, 0 failed.", GREEN)], 600),
    ([("[cohort] ", CYAN), ("Built cv_cohort: ", GRAY), ("1215", BLUE),
      (" CV patients", GRAY)], 400),
    ([("Cohort: ", WHITE), ("1215/3450", BLUE), (" (35.2%); BP>=140/90: ", GRAY),
      ("266", BLUE)], 400),
    ([("Wrote reports -> data_quality_report.md, cohort_summary.md", GRAY)], 300),
    ([("[OK] ", GREEN), ("pipeline complete", WHITE)], 2600),
]


def _text_width(segments) -> int:
    return sum(int(FONT.getlength(t)) for t, _ in segments)


CONTENT_W = max(_text_width(segs) for segs, _ in LINES)
W = CONTENT_W + 2 * PAD
H = BAR_H + PAD + len(LINES) * LINE_H + PAD


def _base() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, BAR_H], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 16 + i * 20
        d.ellipse([cx, BAR_H // 2 - 6, cx + 12, BAR_H // 2 + 6], fill=c)
    d.text((W // 2, BAR_H // 2), "clinicalflow — make all", font=FONT,
           fill=GRAY, anchor="mm")
    return img


def _frame(n_lines: int, cursor: bool) -> Image.Image:
    img = _base()
    d = ImageDraw.Draw(img)
    y = BAR_H + PAD
    for segs, _ in LINES[:n_lines]:
        x = PAD
        for text, color in segs:
            d.text((x, y), text, font=FONT, fill=color)
            x += int(FONT.getlength(text))
        y += LINE_H
    if cursor and n_lines:
        last = LINES[n_lines - 1][0]
        x = PAD + _text_width(last) + 4
        cy = BAR_H + PAD + (n_lines - 1) * LINE_H
        d.rectangle([x, cy + 2, x + 9, cy + SIZE + 2], fill=WHITE)
    return img


def main() -> None:
    frames, durations = [], []
    for i in range(1, len(LINES) + 1):
        frames.append(_frame(i, cursor=True))
        durations.append(LINES[i - 1][1])
    # steady final frame without cursor
    frames.append(_frame(len(LINES), cursor=False))
    durations.append(1500)

    frames[0].save(
        OUT, save_all=True, append_images=frames[1:], duration=durations,
        loop=0, optimize=True, disposal=2,
    )
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.2f} MB, {len(frames)} frames, {W}x{H})")


if __name__ == "__main__":
    main()
