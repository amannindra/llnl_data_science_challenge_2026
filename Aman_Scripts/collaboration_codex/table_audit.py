"""Cross-file reconciliation for Phase 2B.4, Phase 2C, and review queues."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .common import AuditReport, load_json, read_csv


EDGE_ID = re.compile(r"^E_(N\d{6})_(N\d{6})$")


def _rows(root: Path, relative: str) -> list[dict[str, str]]:
    return read_csv(root / relative)[1]


def _ids(rows: Iterable[dict[str, str]]) -> list[str]:
    return [row["edge_id"] for row in rows]


def _count_check(
    report: AuditReport,
    check_id: str,
    actual: int,
    expected: int,
    description: str,
    path: Path,
) -> None:
    report.add(
        check_id,
        "pass" if actual == expected else "fail",
        f"{description}: {actual} (expected {expected}).",
        severity="critical" if actual != expected else "info",
        path=path,
        evidence={"actual": actual, "expected": expected},
    )


def _unique_check(report: AuditReport, check_id: str, rows: list[dict[str, str]], path: Path) -> None:
    ids = _ids(rows)
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    report.add(
        check_id,
        "pass" if not duplicates else "fail",
        "Edge IDs are unique at the expected one-row-per-strut grain."
        if not duplicates
        else "Duplicate edge IDs violate the one-row-per-strut grain.",
        severity="critical" if duplicates else "info",
        path=path,
        evidence={"duplicate_count": len(duplicates), "examples": duplicates[:20]},
    )


def audit_phase2c(root: Path, report: AuditReport) -> dict[str, list[dict[str, str]]]:
    paths = {
        "labels": "review_tables/phase2c_labels.csv",
        "candidates": "review_tables/phase2c_auto_supported_unintended_candidates.csv",
        "remaining": "review_tables/phase2c_remaining_review_queue.csv",
        "new": "review_tables/newly_promoted_14_to_verify.csv",
        "remaining_verify": "review_tables/remaining_review_required_677_to_verify.csv",
        "low": "review_tables/low_priority_uncertain_2654_audit_table.csv",
        "template": "review_tables/human_verification_template.csv",
    }
    tables = {key: _rows(root, value) for key, value in paths.items()}
    expected_counts = {
        "labels": 18468,
        "candidates": 228,
        "remaining": 677,
        "new": 14,
        "remaining_verify": 677,
        "low": 2654,
        "template": 3345,
    }
    for key, expected in expected_counts.items():
        _count_check(
            report,
            f"phase2c.{key}.row_count",
            len(tables[key]),
            expected,
            f"{key} row count",
            root / paths[key],
        )
        _unique_check(report, f"phase2c.{key}.unique_edges", tables[key], root / paths[key])

    label_ids = set(_ids(tables["labels"]))
    candidate_ids = set(_ids(tables["candidates"]))
    remaining_ids = set(_ids(tables["remaining"]))
    low_ids = set(_ids(tables["low"]))
    new_ids = set(_ids(tables["new"]))
    template_ids = set(_ids(tables["template"]))
    remaining_verify_ids = set(_ids(tables["remaining_verify"]))

    union = new_ids | remaining_verify_ids | low_ids
    disjoint = not (new_ids & remaining_verify_ids or new_ids & low_ids or remaining_verify_ids & low_ids)
    report.add(
        "phase2c.verification_template_union",
        "pass" if disjoint and union == template_ids else "fail",
        "The human template is the disjoint union of 14 promoted, 677 remaining, and 2,654 low-priority rows."
        if disjoint and union == template_ids
        else "The verification template does not exactly reconcile to its three source queues.",
        severity="critical" if not disjoint or union != template_ids else "info",
        evidence={
            "union_count": len(union),
            "template_count": len(template_ids),
            "overlap_detected": not disjoint,
            "missing_from_template": sorted(union - template_ids)[:20],
            "extra_in_template": sorted(template_ids - union)[:20],
        },
    )

    relationships_ok = (
        candidate_ids <= label_ids
        and remaining_ids <= label_ids
        and low_ids <= label_ids
        and new_ids <= candidate_ids
        and remaining_verify_ids == remaining_ids
    )
    report.add(
        "phase2c.queue_set_relationships",
        "pass" if relationships_ok else "fail",
        "Candidate/review/audit queues are exact subsets of the all-edge table, and the two 677-row exports agree."
        if relationships_ok
        else "One or more Phase 2C queue/set relationships are broken.",
        severity="critical" if not relationships_ok else "info",
        evidence={
            "candidate_not_in_labels": sorted(candidate_ids - label_ids)[:20],
            "remaining_not_in_labels": sorted(remaining_ids - label_ids)[:20],
            "low_not_in_labels": sorted(low_ids - label_ids)[:20],
            "new_not_in_candidates": sorted(new_ids - candidate_ids)[:20],
            "remaining_export_symmetric_difference": sorted(remaining_verify_ids ^ remaining_ids)[:20],
        },
    )

    by_label = Counter(row["phase2c_label"] for row in tables["labels"])
    expected_labels = {
        "phase2c_auto_supported_designed_removed_absent_or_disconnected": 89,
        "phase2c_auto_supported_possible_unintended_missing": 215,
        "phase2c_auto_supported_possible_unintended_disconnected": 13,
        "phase2c_still_review_required": 672,
        "phase2c_still_review_required_design_intent_conflict": 5,
        "phase2c_low_priority_uncertain_not_defect_like": 2654,
        "phase2c_auto_supported_present_like": 14820,
    }
    report.add(
        "phase2c.label_distribution",
        "pass" if dict(by_label) == expected_labels else "fail",
        "The seven Phase 2C label categories reconcile exactly to 18,468 struts."
        if dict(by_label) == expected_labels
        else "Phase 2C label counts differ from the documented distribution.",
        severity="critical" if dict(by_label) != expected_labels else "info",
        evidence={"actual": dict(by_label), "expected": expected_labels, "sum": sum(by_label.values())},
    )

    summary = load_json(root / "review_tables/phase2c_summary.json")["summary"]
    summary_ok = (
        summary["total_edge_count"] == len(tables["labels"])
        and summary["by_phase2c_label"] == expected_labels
        and summary["phase2c_auto_supported_possible_unintended_combined_count"] == len(tables["candidates"])
        and summary["phase2c_remaining_review_required_count"] == len(tables["remaining"])
        and summary["phase2c_low_priority_not_reported_as_defect_count"] == len(tables["low"])
    )
    report.add(
        "phase2c.summary_reconciliation",
        "pass" if summary_ok else "fail",
        "Phase 2C JSON summary matches the exported tables." if summary_ok else "Phase 2C summary and tables disagree.",
        severity="critical" if not summary_ok else "info",
        path=root / "review_tables/phase2c_summary.json",
    )

    malformed: list[str] = []
    node_mismatch: list[str] = []
    for row in tables["labels"]:
        match = EDGE_ID.fullmatch(row["edge_id"])
        if not match:
            malformed.append(row["edge_id"])
        elif (match.group(1), match.group(2)) != (row["node_u"], row["node_v"]):
            node_mismatch.append(row["edge_id"])
    report.add(
        "phase2c.edge_id_integrity",
        "pass" if not malformed and not node_mismatch else "fail",
        "Every canonical edge ID is well formed and agrees with node_u/node_v."
        if not malformed and not node_mismatch
        else "Malformed edge IDs or endpoint mismatches were found.",
        severity="critical" if malformed or node_mismatch else "info",
        evidence={"malformed": malformed[:20], "node_mismatch": node_mismatch[:20]},
    )

    required_numeric = [
        "ct_missing_material_anomaly_score",
        "occupied_axial_fraction",
        "longest_low_area_gap_fraction",
        "area_mean_voxels2",
        "threshold_stability_occupied_fraction_range",
        "local_registration_stability_voxels",
    ]
    invalid_numeric: list[dict[str, str]] = []
    out_of_range: list[dict[str, str]] = []
    for row in tables["labels"]:
        for column in required_numeric:
            try:
                value = float(row[column])
                if not math.isfinite(value):
                    raise ValueError("not finite")
                if column in {
                    "occupied_axial_fraction",
                    "longest_low_area_gap_fraction",
                    "threshold_stability_occupied_fraction_range",
                } and not 0.0 <= value <= 1.0:
                    out_of_range.append({"edge_id": row["edge_id"], "column": column, "value": row[column]})
            except (TypeError, ValueError):
                invalid_numeric.append({"edge_id": row["edge_id"], "column": column, "value": row.get(column, "")})
    report.add(
        "phase2c.required_numeric_domains",
        "pass" if not invalid_numeric and not out_of_range else "fail",
        "Core classifier metrics are finite and fraction-valued metrics stay in [0, 1]."
        if not invalid_numeric and not out_of_range
        else "Invalid or out-of-range core classifier metrics were found.",
        severity="high" if invalid_numeric or out_of_range else "info",
        evidence={"invalid": invalid_numeric[:20], "out_of_range": out_of_range[:20]},
    )

    human_columns = [
        "human_ct_label",
        "human_design_label_if_relevant",
        "reviewer_confidence",
        "reviewer_initials",
        "review_date",
        "reviewer_notes",
        "recommended_action",
    ]
    filled = [
        {"edge_id": row["edge_id"], "columns": [column for column in human_columns if row.get(column, "").strip()]}
        for row in tables["template"]
        if any(row.get(column, "").strip() for column in human_columns)
    ]
    report.add(
        "phase2c.human_template_blank",
        "pass" if not filled else "fail",
        "Human-verification fields remain blank; no labels were invented by the transfer process."
        if not filled
        else "The supposedly blank human template already contains reviewer entries.",
        severity="high" if filled else "info",
        path=root / paths["template"],
        evidence={"filled_rows": filled[:20]},
    )

    return tables


def audit_phase2b4_baseline(root: Path, report: AuditReport) -> dict[str, list[dict[str, str]]]:
    base = root / "final_report_baseline"
    paths = {
        "candidates": base / "tables/auto_supported_unintended_candidates.csv",
        "manual": base / "tables/manual_review_queue.csv",
        "human": base / "tables/human_spotcheck_labels_rank001_040.csv",
        "human_counts": base / "tables/human_spotcheck_label_counts.csv",
        "headline": base / "tables/headline_numbers.csv",
        "panels": base / "tables/spotcheck_panel_index.csv",
    }
    tables = {key: read_csv(path)[1] for key, path in paths.items()}
    expected = {"candidates": 214, "manual": 920, "human": 40}
    for key, count in expected.items():
        _count_check(report, f"phase2b4.{key}.row_count", len(tables[key]), count, f"{key} row count", paths[key])
        _unique_check(report, f"phase2b4.{key}.unique_edges", tables[key], paths[key])

    summary = load_json(base / "final_ct_defect_summary.json")
    automated = summary["automated_review"]
    human = summary["human_spotcheck"]
    headline = tables["headline"][0]
    candidate_counts = Counter(row["phase2b4_automated_review_label"] for row in tables["candidates"])
    human_counts = Counter(row["normalized_human_ct_label"] for row in tables["human"])
    fraction = len(tables["candidates"]) / int(headline["total_expected_struts"])
    baseline_ok = (
        candidate_counts["auto_supported_possible_unintended_missing"] == 202
        and candidate_counts["auto_supported_possible_unintended_disconnected"] == 12
        and automated["auto_supported_possible_unintended_combined"] == 214
        and len(tables["manual"]) == automated["blocked_manual_review"] == 920
        and human_counts == Counter({"material_absent": 29, "material_disconnected": 7, "ambiguous": 4})
        and human["present_like_contradiction_count"] == 0
        and math.isclose(fraction, automated["draft_auto_supported_possible_unintended_fraction"], rel_tol=0, abs_tol=1e-15)
    )
    report.add(
        "phase2b4.baseline_reconciliation",
        "pass" if baseline_ok else "fail",
        "The conservative 214-candidate baseline, 920 blocked rows, 40 human labels, and 1.158761% fraction reconcile."
        if baseline_ok
        else "The conservative final-report package contains inconsistent counts or fractions.",
        severity="critical" if not baseline_ok else "info",
        path=base / "final_ct_defect_summary.json",
        evidence={
            "candidate_counts": dict(candidate_counts),
            "human_counts": dict(human_counts),
            "computed_fraction": fraction,
        },
    )
    return tables


def run_table_audit(root: Path, report: AuditReport) -> dict[str, object]:
    phase2c = audit_phase2c(root, report)
    baseline = audit_phase2b4_baseline(root, report)
    baseline_ids = set(_ids(baseline["candidates"]))
    phase2c_ids = set(_ids(phase2c["candidates"]))
    new_ids = set(_ids(phase2c["new"]))
    exact_promotion = baseline_ids <= phase2c_ids and phase2c_ids - baseline_ids == new_ids
    report.add(
        "phase2c.promotion_delta",
        "pass" if exact_promotion else "fail",
        "Phase 2C's 228 candidates are exactly the 214 baseline candidates plus the 14 newly promoted rows."
        if exact_promotion
        else "The Phase 2C candidate delta is not exactly the documented 14 promoted rows.",
        severity="critical" if not exact_promotion else "info",
        evidence={
            "baseline_count": len(baseline_ids),
            "phase2c_count": len(phase2c_ids),
            "new_count": len(new_ids),
            "unexpected_added": sorted((phase2c_ids - baseline_ids) - new_ids)[:20],
            "missing_promotions": sorted(new_ids - (phase2c_ids - baseline_ids))[:20],
        },
    )
    return {"phase2c": phase2c, "baseline": baseline}

