"""Scientific-validity checks against the paper and review design."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .common import AuditReport, load_json, read_csv


PAPER_SPECIMEN = {
    "name": "0.5% (#1)",
    "nominal_missing_percent": 0.50,
    "ct_missing_percent": 0.57,
    "ct_disconnected_percent": 4.97,
    "source": "2246722.pdf, Section 3.1.1, Table 3",
}


def run_scientific_audit(root: Path, repo_root: Path, report: AuditReport) -> dict:
    """Compare the packet's candidate taxonomy with the paper's reviewed labels."""

    summary = load_json(root / "review_tables/phase2c_summary.json")["summary"]
    total = int(summary["total_edge_count"])
    paper_missing = total * PAPER_SPECIMEN["ct_missing_percent"] / 100.0
    paper_nominal = total * PAPER_SPECIMEN["nominal_missing_percent"] / 100.0
    paper_unintended_excess = paper_missing - paper_nominal
    paper_disconnected = total * PAPER_SPECIMEN["ct_disconnected_percent"] / 100.0

    pipeline_designed = int(
        summary["by_phase2c_label"][
            "phase2c_auto_supported_designed_removed_absent_or_disconnected"
        ]
    )
    pipeline_unintended_missing = int(
        summary["phase2c_auto_supported_possible_unintended_missing_count"]
    )
    pipeline_disconnected = int(
        summary["phase2c_auto_supported_possible_unintended_disconnected_count"]
    )
    pipeline_total_missing_like = pipeline_designed + pipeline_unintended_missing

    comparison = {
        "denominator": total,
        "paper": {
            **PAPER_SPECIMEN,
            "approx_total_missing_count": paper_missing,
            "approx_nominal_designed_missing_count": paper_nominal,
            "approx_unintended_missing_excess_count": paper_unintended_excess,
            "approx_disconnected_count": paper_disconnected,
        },
        "phase2c": {
            "designed_removed_absent_or_disconnected": pipeline_designed,
            "possible_unintended_missing": pipeline_unintended_missing,
            "possible_unintended_disconnected": pipeline_disconnected,
            "designed_plus_possible_unintended_missing": pipeline_total_missing_like,
        },
        "ratios": {
            "pipeline_total_missing_like_vs_paper_total_missing": pipeline_total_missing_like
            / paper_missing,
            "pipeline_unintended_missing_vs_paper_excess_missing": pipeline_unintended_missing
            / paper_unintended_excess,
            "paper_disconnected_vs_pipeline_possible_disconnected": paper_disconnected
            / pipeline_disconnected,
        },
    }
    report.add(
        "science.paper_external_consistency",
        "warn",
        "The Phase 2C candidate taxonomy does not reproduce the paper's manually reviewed defect distribution: it flags far more missing-like edges and far fewer disconnected edges. Treat it as triage, not validated paper-equivalent classification.",
        severity="high",
        path=repo_root / "2246722.pdf",
        evidence=comparison,
    )

    human_rows = read_csv(
        root / "final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv"
    )[1]
    baseline_rows = read_csv(
        root / "final_report_baseline/tables/auto_supported_unintended_candidates.csv"
    )[1]
    human_ranks = sorted(int(row["rank"]) for row in human_rows)
    human_labels = Counter(row["normalized_human_ct_label"] for row in human_rows)
    report.add(
        "science.human_review_sampling",
        "warn",
        "The human evidence covers only ranks 1-40 of the 214 auto-supported candidates, with no random sampling and no present-like controls; it supports top-ranked precision directionally but cannot establish full-list precision, recall, or calibration.",
        severity="high",
        evidence={
            "reviewed_rows": len(human_rows),
            "candidate_rows": len(baseline_rows),
            "coverage_fraction": len(human_rows) / len(baseline_rows),
            "ranks": [min(human_ranks), max(human_ranks)],
            "labels": dict(human_labels),
            "present_like_control_rows": 0,
            "selection": "top-ranked consecutive candidates, not a probability sample",
        },
    )

    promoted_rows = read_csv(root / "review_tables/newly_promoted_14_to_verify.csv")[1]
    template_rows = read_csv(root / "review_tables/human_verification_template.csv")[1]
    promoted_human_fields = [
        row
        for row in template_rows
        if row["edge_id"] in {item["edge_id"] for item in promoted_rows}
        and any(
            row.get(column, "").strip()
            for column in (
                "human_ct_label",
                "reviewer_confidence",
                "reviewer_initials",
                "review_date",
            )
        )
    ]
    report.add(
        "science.phase2c_promotions_unreviewed",
        "warn" if not promoted_human_fields else "pass",
        "All 14 Phase 2C promotions remain unreviewed, so 228 must not replace the spot-check-supported 214 baseline yet."
        if not promoted_human_fields
        else "The 14 Phase 2C promotions contain saved human review evidence.",
        severity="high" if not promoted_human_fields else "info",
        evidence={
            "promoted_count": len(promoted_rows),
            "promoted_rows_with_human_fields": len(promoted_human_fields),
        },
    )

    labels = read_csv(root / "review_tables/phase2c_labels.csv")[1]
    candidates = [
        row
        for row in labels
        if row["phase2c_label"]
        in {
            "phase2c_auto_supported_possible_unintended_missing",
            "phase2c_auto_supported_possible_unintended_disconnected",
        }
    ]
    all_boundary = Counter(row["boundary_bin"] for row in labels)
    candidate_boundary = Counter(row["boundary_bin"] for row in candidates)
    boundary_or_near_all = (
        all_boundary.get("boundary", 0) + all_boundary.get("near_boundary", 0)
    ) / len(labels)
    boundary_or_near_candidates = (
        candidate_boundary.get("boundary", 0)
        + candidate_boundary.get("near_boundary", 0)
    ) / len(candidates)
    report.add(
        "science.spatial_candidate_profile",
        "warn" if boundary_or_near_candidates > boundary_or_near_all + 0.10 else "pass",
        "Possible unintended candidates are disproportionately boundary/near-boundary cases, increasing the risk of skin, crop, and registration artifacts."
        if boundary_or_near_candidates > boundary_or_near_all + 0.10
        else "Candidate boundary composition is not strongly inflated relative to all edges.",
        severity="medium" if boundary_or_near_candidates > boundary_or_near_all + 0.10 else "info",
        evidence={
            "all_edge_boundary_bins": dict(all_boundary),
            "candidate_boundary_bins": dict(candidate_boundary),
            "all_boundary_or_near_fraction": boundary_or_near_all,
            "candidate_boundary_or_near_fraction": boundary_or_near_candidates,
        },
    )
    return comparison

