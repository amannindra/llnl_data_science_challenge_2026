"""Audit whether CT evidence actually covers edges promoted by the classifier."""

from __future__ import annotations

import json
from pathlib import Path

import tifffile

from .common import AuditReport, load_json, read_csv


RAW_TIFF = Path(
    "data/missing_struts/tif_stacks/"
    "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)


def _float_list(value: str) -> list[float]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON list")
    return [float(item) for item in parsed]


def run_coverage_audit(root: Path, repo_root: Path, report: AuditReport) -> dict:
    """Detect zero-support candidates and panel/evidence-boundary conflicts."""

    labels = read_csv(root / "review_tables/phase2c_labels.csv")[1]
    viewer = load_json(root / "viewer/viewer_data.json")
    endpoints = {edge["edge_id"]: edge for edge in viewer["edges"]}
    panel_rows = read_csv(
        root / "review_panels_phase2c_top120/ct_edge_panel_summary.csv"
    )[1]
    panel_index = read_csv(root / "review_tables/review_panel_index.csv")[1]

    raw_tiff = repo_root / RAW_TIFF
    with tifffile.TiffFile(raw_tiff) as tiff:
        tiff_shape_zyx = tuple(int(value) for value in tiff.series[0].shape)

    # The review artifacts consistently stop edge-aligned evidence at x=767,
    # even though the raw TIFF metadata reports 837 columns.  This is an
    # evidence-pipeline support boundary, not the raw TIFF's physical FOV.
    panel_x_max = max(int(row["tiff_x_max"]) for row in panel_index)
    graph_x_max = max(
        float(point[0])
        for edge in viewer["edges"]
        for point in (edge["u"], edge["v"])
    )
    edges_past_panel_support = [
        edge["edge_id"]
        for edge in viewer["edges"]
        if max(float(edge["u"][0]), float(edge["v"][0])) > panel_x_max
    ]

    candidate_labels = {
        "phase2c_auto_supported_possible_unintended_missing",
        "phase2c_auto_supported_possible_unintended_disconnected",
    }
    unsupported_candidates: list[dict] = []
    for row in labels:
        if row["phase2c_label"] not in candidate_labels:
            continue
        area_profile = _float_list(row["area_profile_voxels2"])
        edge = endpoints[row["edge_id"]]
        both_past_support = (
            float(edge["u"][0]) > panel_x_max
            and float(edge["v"][0]) > panel_x_max
        )
        no_endpoint_material = (
            row["node_u_registration_status"] == "no_local_material"
            and row["node_v_registration_status"] == "no_local_material"
        )
        all_zero_area = bool(area_profile) and all(value == 0.0 for value in area_profile)
        if both_past_support and no_endpoint_material and all_zero_area:
            unsupported_candidates.append(
                {
                    "edge_id": row["edge_id"],
                    "phase2b4_label": row["phase2b4_automated_review_label"],
                    "phase2c_label": row["phase2c_label"],
                    "phase2b4_clean_for_auto_support": row[
                        "phase2b4_clean_for_auto_support"
                    ],
                    "endpoint_u_x": float(edge["u"][0]),
                    "endpoint_v_x": float(edge["v"][0]),
                    "node_u_status": row["node_u_registration_status"],
                    "node_v_status": row["node_v_registration_status"],
                }
            )

    report.add(
        "coverage.auto_supported_without_ct_support",
        "fail" if unsupported_candidates else "pass",
        "Three auto-supported possible-missing edges have both endpoints beyond the evidence pipeline's x=767 support, no-local-material endpoint statuses, and all-zero area profiles. They must be coverage-blocked until the x-clipping/axis issue is fixed."
        if unsupported_candidates
        else "No auto-supported candidate relies entirely on out-of-support, all-zero CT evidence.",
        severity="critical" if unsupported_candidates else "info",
        path=root / "review_tables/phase2c_labels.csv",
        evidence={
            "raw_tiff_shape_zyx": list(tiff_shape_zyx),
            "raw_tiff_x_max_index": tiff_shape_zyx[2] - 1,
            "panel_evidence_x_max_index": panel_x_max,
            "viewer_graph_x_max": graph_x_max,
            "viewer_edges_with_any_endpoint_past_panel_support": len(
                edges_past_panel_support
            ),
            "unsupported_auto_candidates": unsupported_candidates,
        },
    )

    all_zero_panels: list[dict] = []
    for row in panel_rows:
        zero = all(
            float(row[column]) == 0.0
            for column in (
                "axial_max_median",
                "axial_p95_median",
                "axial_mean_median",
                "centerline_median",
            )
        )
        if zero:
            index_row = next(item for item in panel_index if item["edge_id"] == row["edge_id"])
            all_zero_panels.append(
                {
                    "rank": int(row["rank"]),
                    "edge_id": row["edge_id"],
                    "design_state": row["design_state"],
                    "x_bounds": [
                        int(index_row["tiff_x_min"]),
                        int(index_row["tiff_x_max"]),
                    ],
                    "endpoint_x": [
                        float(index_row["endpoint_u_x"]),
                        float(index_row["endpoint_v_x"]),
                    ],
                }
            )
    report.add(
        "coverage.review_panels_zero_edge_signal",
        "warn" if all_zero_panels else "pass",
        "Forty of the 120 review panels have all-zero edge-aligned slabs/traces because their requested edge lies beyond the evidence pipeline's x support; nearby context in a projection must not be mistaken for valid edge evidence."
        if all_zero_panels
        else "Every review panel contains nonzero edge-aligned evidence.",
        severity="high" if all_zero_panels else "info",
        path=root / "review_panels_phase2c_top120",
        evidence={
            "all_zero_panel_count": len(all_zero_panels),
            "all_zero_panels": all_zero_panels,
            "recommended_fix": "Add a valid-sample mask and OUT OF SUPPORT watermark; repair the unexplained x=767 clamp despite the TIFF's x=837 shape.",
        },
    )

    partial_promotions = []
    promoted = {row["edge_id"] for row in read_csv(root / "review_tables/newly_promoted_14_to_verify.csv")[1]}
    for row in panel_index:
        if row["edge_id"] not in promoted:
            continue
        endpoint_x = [float(row["endpoint_u_x"]), float(row["endpoint_v_x"])]
        if max(endpoint_x) > panel_x_max:
            partial_promotions.append(
                {
                    "rank": int(row["rank"]),
                    "edge_id": row["edge_id"],
                    "endpoint_x": endpoint_x,
                    "x_bounds": [int(row["tiff_x_min"]), int(row["tiff_x_max"])],
                }
            )
    report.add(
        "coverage.promotions_cross_support_boundary",
        "warn" if partial_promotions else "pass",
        "One newly promoted edge crosses the evidence x-support boundary and needs an explicit endpoint-coverage caution before review."
        if partial_promotions
        else "No newly promoted edge crosses the observed evidence support boundary.",
        severity="high" if partial_promotions else "info",
        evidence={"rows": partial_promotions},
    )

    metric_mismatches = []
    panel_by_edge = {row["edge_id"]: row for row in panel_rows}
    for row in panel_index:
        summary = panel_by_edge[row["edge_id"]]
        if (
            row["panel_metric_label"] != "CT anomaly score"
            or float(row["panel_metric_value"]) != float(summary["mean_delta_mm"])
        ):
            metric_mismatches.append(row["edge_id"])
    report.add(
        "coverage.panel_metric_units",
        "warn" if not metric_mismatches else "fail",
        "All 120 values named mean_delta_mm are actually the dimensionless quantity labeled CT anomaly score in the review index; the field name has misleading physical units."
        if not metric_mismatches
        else "Panel metric tables disagree in addition to the misleading unit label.",
        severity="medium" if not metric_mismatches else "high",
        evidence={
            "row_count": len(panel_rows),
            "cross_table_mismatches": metric_mismatches,
            "recommended_name": "ct_anomaly_score",
        },
    )

    return {
        "raw_tiff_shape_zyx": tiff_shape_zyx,
        "panel_x_max": panel_x_max,
        "graph_x_max": graph_x_max,
        "edges_past_panel_support": edges_past_panel_support,
        "unsupported_candidates": unsupported_candidates,
        "all_zero_panels": all_zero_panels,
        "partial_promotions": partial_promotions,
    }
