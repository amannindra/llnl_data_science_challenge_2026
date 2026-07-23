#!/usr/bin/env python3
"""Render every project PDF page and assemble readable contact sheets.

Requires Poppler's ``pdftoppm`` (already available in this environment).  All
temporary page images are removed automatically; persistent visual-review
artifacts are written only to ``Scripts/outputs``.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "outputs"
SOURCES = {
    "main_challenge_pages": ROOT / "DATA_SCIENCE_CHALLENGE_2026.pdf",
    "introduction_slides": ROOT / "presentation" / "DSSI_Challenge_2026_Introduction.pdf",
}
CELL_WIDTH = 300
CELL_HEIGHT = 440
COLUMNS = 4
PADDING = 16
LABEL_HEIGHT = 28


def render_pages(pdf: Path, temporary_directory: Path) -> list[Path]:
    """Render all pages at 110 dpi, returning sorted PNG paths."""
    prefix = temporary_directory / pdf.stem
    subprocess.run(
        ["pdftoppm", "-png", "-r", "110", str(pdf), str(prefix)],
        check=True,
    )
    return sorted(temporary_directory.glob(f"{pdf.stem}-*.png"))


def make_contact_sheet(label: str, pages: list[Path]) -> Path:
    font = ImageFont.load_default()
    rows = (len(pages) + COLUMNS - 1) // COLUMNS
    width = PADDING + COLUMNS * (CELL_WIDTH + PADDING)
    height = PADDING + rows * (LABEL_HEIGHT + CELL_HEIGHT + PADDING)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, page_path in enumerate(pages, start=1):
        row, column = divmod(index - 1, COLUMNS)
        x = PADDING + column * (CELL_WIDTH + PADDING)
        y = PADDING + row * (LABEL_HEIGHT + CELL_HEIGHT + PADDING)
        with Image.open(page_path) as source:
            page = ImageOps.contain(source.convert("RGB"), (CELL_WIDTH, CELL_HEIGHT))
        draw.text((x, y + 5), f"{label}: page {index}", fill="black", font=font)
        page_x = x + (CELL_WIDTH - page.width) // 2
        page_y = y + LABEL_HEIGHT + (CELL_HEIGHT - page.height) // 2
        sheet.paste(page, (page_x, page_y))

    destination = OUT / f"{label}_contact_sheet.png"
    sheet.save(destination)
    return destination


def main() -> None:
    if shutil.which("pdftoppm") is None:
        raise SystemExit("pdftoppm is required but was not found on PATH")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dssi_pdf_review_") as temporary:
        temp_path = Path(temporary)
        for label, pdf in SOURCES.items():
            pages = render_pages(pdf, temp_path)
            if not pages:
                raise RuntimeError(f"No pages rendered from {pdf}")
            print(f"{pdf.name}: {len(pages)} pages")
            print(f"Wrote {make_contact_sheet(label, pages)}")


if __name__ == "__main__":
    main()
