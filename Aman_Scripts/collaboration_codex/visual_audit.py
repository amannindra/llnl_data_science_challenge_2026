"""Sequential PNG verification and compact contact-sheet generation."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

from .common import AuditReport, load_json, read_csv, sha256_file


PANEL_NAME = re.compile(r"^rank_(\d{3})_(E_N\d{6}_N\d{6})_ct_panel\.png$")


def inspect_images(root: Path, report: AuditReport) -> list[dict]:
    records: list[dict] = []
    errors: list[dict] = []
    for path in sorted(root.rglob("*.png")):
        relative = path.relative_to(root).as_posix()
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                thumb = image.convert("L")
                thumb.thumbnail((256, 256))
                stats = ImageStat.Stat(thumb)
                extrema = thumb.getextrema()
                records.append(
                    {
                        "path": relative,
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                        "format": image.format,
                        "mode": image.mode,
                        "width": image.width,
                        "height": image.height,
                        "thumbnail_mean_luma": round(float(stats.mean[0]), 6),
                        "thumbnail_min_luma": int(extrema[0]),
                        "thumbnail_max_luma": int(extrema[1]),
                    }
                )
        except Exception as exc:
            errors.append({"path": relative, "error": str(exc)})

    expected_png_count = 121
    report.add(
        "images.decode_all",
        "pass" if not errors and len(records) == expected_png_count else "fail",
        f"All {expected_png_count} PNG artifacts decode completely and were inspected sequentially."
        if not errors and len(records) == expected_png_count
        else "One or more PNG artifacts are missing or fail decoding.",
        severity="critical" if errors or len(records) != expected_png_count else "info",
        evidence={"decoded": len(records), "expected": expected_png_count, "errors": errors},
    )

    hashes: dict[str, list[str]] = {}
    for record in records:
        hashes.setdefault(record["sha256"], []).append(record["path"])
    duplicate_groups = [paths for paths in hashes.values() if len(paths) > 1]
    report.add(
        "images.exact_duplicates",
        "warn" if duplicate_groups else "pass",
        "Exact duplicate image bytes were found." if duplicate_groups else "No exact duplicate PNGs were found.",
        severity="medium" if duplicate_groups else "info",
        evidence={"duplicate_groups": duplicate_groups},
    )

    panel_records = [record for record in records if record["path"].startswith("review_panels_phase2c_top120/")]
    wrong_dimensions = [
        record for record in panel_records if (record["width"], record["height"]) != (2790, 1655)
    ]
    report.add(
        "images.panel_dimensions",
        "pass" if len(panel_records) == 120 and not wrong_dimensions else "fail",
        "All 120 review panels share the expected 2790×1655 layout."
        if len(panel_records) == 120 and not wrong_dimensions
        else "The review-panel count or dimensions are inconsistent.",
        severity="high" if len(panel_records) != 120 or wrong_dimensions else "info",
        evidence={"panel_count": len(panel_records), "wrong_dimensions": wrong_dimensions[:20]},
    )
    return records


def audit_panel_mapping(root: Path, records: list[dict], report: AuditReport) -> None:
    panel_paths = {
        Path(record["path"]).name: record
        for record in records
        if record["path"].startswith("review_panels_phase2c_top120/rank_")
    }
    summary_rows = read_csv(root / "review_panels_phase2c_top120/ct_edge_panel_summary.csv")[1]
    index_rows = read_csv(root / "review_tables/review_panel_index.csv")[1]
    mismatches: list[dict] = []
    seen_ranks: set[int] = set()
    for row in summary_rows:
        rank = int(row["rank"])
        expected_name = Path(row["output_path"]).name
        match = PANEL_NAME.fullmatch(expected_name)
        seen_ranks.add(rank)
        if (
            expected_name not in panel_paths
            or match is None
            or int(match.group(1)) != rank
            or match.group(2) != row["edge_id"]
        ):
            mismatches.append({"rank": rank, "edge_id": row["edge_id"], "expected_name": expected_name})
    summary_pairs = {(int(row["rank"]), row["edge_id"]) for row in summary_rows}
    index_pairs = {(int(row["rank"]), row["edge_id"]) for row in index_rows}
    mapping_ok = (
        len(summary_rows) == len(index_rows) == len(panel_paths) == 120
        and seen_ranks == set(range(1, 121))
        and summary_pairs == index_pairs
        and not mismatches
    )
    report.add(
        "images.panel_index_mapping",
        "pass" if mapping_ok else "fail",
        "Ranks 001–120, edge IDs, filenames, summary rows, and review index agree exactly."
        if mapping_ok
        else "Panel filenames and their CSV indexes do not reconcile.",
        severity="critical" if not mapping_ok else "info",
        evidence={
            "summary_rows": len(summary_rows),
            "index_rows": len(index_rows),
            "panel_files": len(panel_paths),
            "mismatches": mismatches[:20],
            "summary_only": sorted(summary_pairs - index_pairs)[:20],
            "index_only": sorted(index_pairs - summary_pairs)[:20],
        },
    )


def create_contact_sheets(
    root: Path,
    output_dir: Path,
    *,
    panels_per_sheet: int = 20,
    thumbnail_width: int = 330,
) -> list[Path]:
    """Create small review montages while opening only one source panel at a time."""

    output_dir.mkdir(parents=True, exist_ok=True)
    panels = sorted((root / "review_panels_phase2c_top120").glob("rank_*_ct_panel.png"))
    if not panels:
        raise ValueError("No Phase 2C review panels found")
    columns = 4
    rows = math.ceil(panels_per_sheet / columns)
    thumb_height = round(thumbnail_width * 1655 / 2790)
    label_height = 28
    margin = 16
    font = ImageFont.load_default()
    outputs: list[Path] = []
    for page_index, start in enumerate(range(0, len(panels), panels_per_sheet), start=1):
        batch = panels[start : start + panels_per_sheet]
        sheet = Image.new(
            "RGB",
            (
                margin * 2 + columns * thumbnail_width,
                margin * 2 + rows * (thumb_height + label_height),
            ),
            "white",
        )
        draw = ImageDraw.Draw(sheet)
        for position, path in enumerate(batch):
            row, column = divmod(position, columns)
            x = margin + column * thumbnail_width
            y = margin + row * (thumb_height + label_height)
            with Image.open(path) as image:
                thumb = image.convert("RGB")
                thumb.thumbnail((thumbnail_width, thumb_height))
                sheet.paste(thumb, (x, y + label_height))
            match = PANEL_NAME.fullmatch(path.name)
            label = f"rank {match.group(1)} - {match.group(2)}" if match else path.stem
            draw.text((x + 4, y + 7), label, fill="black", font=font)
        output_path = output_dir / f"phase2c_panels_{start + 1:03d}_{start + len(batch):03d}.jpg"
        sheet.save(output_path, format="JPEG", quality=88, optimize=True)
        outputs.append(output_path)
    return outputs


def write_image_inventory(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError("Cannot write an empty image inventory")
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def run_visual_audit(root: Path, report: AuditReport) -> list[dict]:
    records = inspect_images(root, report)
    audit_panel_mapping(root, records, report)
    summary = load_json(root / "final_report_baseline/final_ct_defect_summary.json")
    automated = summary["automated_review"]
    largest = int(automated["auto_supported_present_like"])
    smallest_headline_defect = min(
        int(automated["auto_supported_possible_unintended_missing"]),
        int(automated["auto_supported_possible_unintended_disconnected"]),
    )
    ratio = largest / smallest_headline_defect
    report.add(
        "images.baseline_chart_scale",
        "warn" if ratio > 100 else "pass",
        "The baseline bar chart uses one linear scale even though present-like exceeds the smallest headline defect class by more than 1,000×; small categories are visually unreadable."
        if ratio > 100
        else "The baseline bar-chart scale keeps all headline categories visually legible.",
        severity="medium" if ratio > 100 else "info",
        path=root / "final_report_baseline/figures/automated_review_label_counts.png",
        evidence={
            "auto_supported_present_like": largest,
            "smallest_headline_defect_count": smallest_headline_defect,
            "ratio": ratio,
            "recommended_fix": "Use a broken/log axis or a separate defect-only panel with direct value labels.",
        },
    )
    return records
