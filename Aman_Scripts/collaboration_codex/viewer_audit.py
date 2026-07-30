"""Static integrity checks for the dependency-free HTML defect viewer."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .common import AuditReport, load_json, read_csv


EMBEDDED_DATA = re.compile(
    r'<script id="viewer-data" type="application/json">(.*?)</script>', re.DOTALL
)


def extract_embedded_viewer_data(html_text: str) -> dict:
    match = EMBEDDED_DATA.search(html_text)
    if not match:
        raise ValueError("Viewer HTML has no embedded viewer-data JSON block")
    return json.loads(match.group(1))


def run_viewer_audit(root: Path, report: AuditReport) -> dict:
    viewer_dir = root / "viewer"
    html_path = viewer_dir / "index.html"
    html_text = html_path.read_text(encoding="utf-8")
    embedded = extract_embedded_viewer_data(html_text)
    external = load_json(viewer_dir / "viewer_data.json")
    legend = load_json(viewer_dir / "legend.json")
    manifest = load_json(viewer_dir / "run_manifest.json")

    report.add(
        "viewer.embedded_external_match",
        "pass" if embedded == external else "fail",
        "The self-contained HTML embeds the same data as viewer_data.json."
        if embedded == external
        else "Embedded viewer JSON differs from the external viewer_data.json.",
        severity="critical" if embedded != external else "info",
        path=html_path,
    )

    edges = external["edges"]
    metadata = external["metadata"]
    ids = [edge["edge_id"] for edge in edges]
    counts = Counter(edge["class_name"] for edge in edges)
    counts_ok = (
        len(edges) == 18468
        and len(ids) == len(set(ids))
        and dict(counts) == metadata["class_counts"] == manifest["class_counts"]
        and sum(counts.values()) == manifest["edge_count"] == metadata["edge_count"]
    )
    report.add(
        "viewer.edge_counts",
        "pass" if counts_ok else "fail",
        "Viewer edge IDs are unique and all class counts reconcile to 18,468."
        if counts_ok
        else "Viewer edge uniqueness/count metadata is inconsistent.",
        severity="critical" if not counts_ok else "info",
        path=viewer_dir / "viewer_data.json",
        evidence={"edge_count": len(edges), "unique_ids": len(set(ids)), "class_counts": dict(counts)},
    )

    label_ids = {
        row["edge_id"] for row in read_csv(root / "review_tables/phase2c_labels.csv")[1]
    }
    report.add(
        "viewer.edge_coverage",
        "pass" if set(ids) == label_ids else "fail",
        "Viewer edge IDs exactly cover the Phase 2C all-edge label table."
        if set(ids) == label_ids
        else "Viewer and Phase 2C edge sets differ.",
        severity="critical" if set(ids) != label_ids else "info",
        evidence={
            "missing_in_viewer": sorted(label_ids - set(ids))[:20],
            "extra_in_viewer": sorted(set(ids) - label_ids)[:20],
        },
    )

    bbox = metadata["bbox_xyz"]
    invalid: list[dict] = []
    style_mismatches: list[str] = []
    for edge in edges:
        for endpoint_name in ("u", "v"):
            point = edge[endpoint_name]
            if len(point) != 3 or any(not math.isfinite(float(value)) for value in point):
                invalid.append({"edge_id": edge["edge_id"], "endpoint": endpoint_name, "point": point})
                continue
            for axis, value in enumerate(point):
                if not bbox[0][axis] - 1e-9 <= value <= bbox[1][axis] + 1e-9:
                    invalid.append({"edge_id": edge["edge_id"], "endpoint": endpoint_name, "point": point})
                    break
        style = legend.get(edge["class_name"])
        if style is None or edge["color"] != style["color"] or float(edge["width"]) != float(style["width"]):
            style_mismatches.append(edge["edge_id"])
    report.add(
        "viewer.geometry_and_style",
        "pass" if not invalid and not style_mismatches else "fail",
        "All viewer endpoints are finite/in-bounds and class styles match the legend."
        if not invalid and not style_mismatches
        else "Invalid geometry or legend-style mismatches were found.",
        severity="high" if invalid or style_mismatches else "info",
        evidence={"invalid_geometry": invalid[:20], "style_mismatches": style_mismatches[:20]},
    )

    required_ui_tokens = [
        'id="canvas"',
        'id="search"',
        'id="reset"',
        "canvas.addEventListener('click'",
        "canvas.addEventListener('wheel'",
        "buildLegend();",
        "window.addEventListener('resize'",
    ]
    missing_ui = [token for token in required_ui_tokens if token not in html_text]
    report.add(
        "viewer.static_ui_features",
        "pass" if not missing_ui else "fail",
        "The HTML includes search, reset, rotate, zoom, click-selection, legend, and resize handlers."
        if not missing_ui
        else "Required viewer controls/handlers are missing.",
        severity="high" if missing_ui else "info",
        path=html_path,
        evidence={"missing_tokens": missing_ui, "html_size_bytes": html_path.stat().st_size},
    )
    return external

