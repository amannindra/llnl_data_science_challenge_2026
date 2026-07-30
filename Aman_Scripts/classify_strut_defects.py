#!/usr/bin/env python3
"""Classify all STL-expected struts from an existing metrology JSON report."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from Components.defect_classification import classify_defect_subtype


FIELDS = [
    "strut_id", "edge_id", "junction0", "junction1", "defect_type",
    "classification_status", "classification_confidence",
    "classification_reason", "measurement_valid", "comparison_applicable",
    "has_error", "review_required", "observed_axial_fraction",
    "longest_unsupported_gap_voxels", "connected_support",
    "median_signed_radial_deviation_voxels", "p90_absolute_radial_deviation_voxels",
    "expected_radius_median_voxels", "registration_uncertainty_voxels",
    "failed_checks",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="Aman_Scripts/outputs/simple_strut_metrology/strut_metrology.json",
    )
    parser.add_argument(
        "--output-dir",
        default="Aman_Scripts/outputs/strut_defect_classification",
    )
    parser.add_argument("--anchors-per-group", type=int, default=5)
    return parser.parse_args()


def _value(record: dict[str, Any], name: str) -> Any:
    value = record.get(name)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _severity(row: dict[str, Any]) -> tuple[int, float, int]:
    status_rank = {"confirmed": 0, "review": 1, "accepted": 2, "excluded": 3}
    coverage = row.get("observed_axial_fraction")
    try:
        distance = abs(float(coverage) - 0.5)
    except (TypeError, ValueError):
        distance = 0.0
    return (status_rank.get(row["classification_status"], 9), distance, row["strut_id"])


def main() -> None:
    args = parse_args()
    if args.anchors_per_group < 1:
        raise SystemExit("--anchors-per-group must be positive")
    source = Path(args.input).resolve()
    output = Path(args.output_dir).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    struts = payload.get("struts")
    if not isinstance(struts, list) or not struts:
        raise SystemExit("input JSON does not contain a non-empty struts list")

    rows: list[dict[str, Any]] = []
    for record in struts:
        result = classify_defect_subtype(record)
        row = {"strut_id": int(record["id"]), "edge_id": record.get("edge_id")}
        row.update({
            "junction0": record.get("junction0"),
            "junction1": record.get("junction1"),
            **result,
        })
        for name in FIELDS:
            if name not in row:
                row[name] = _value(record, name)
        rows.append(row)
    rows.sort(key=lambda row: row["strut_id"])

    output.mkdir(parents=True, exist_ok=True)
    with (output / "strut_defect_classification.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (row["defect_type"], row["classification_status"]), []
        ).append(row)
    anchors: list[dict[str, Any]] = []
    for group, members in sorted(groups.items()):
        if group[1] in {"excluded", "accepted"}:
            continue
        anchors.extend(sorted(members, key=_severity)[: args.anchors_per_group])
    anchors.sort(key=_severity)
    with (output / "anchor_review_queue.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(anchors)

    counts = Counter(
        f"{row['classification_status']}:{row['defect_type']}" for row in rows
    )
    summary = {
        "input": str(source),
        "strut_count": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "anchor_review_count": len(anchors),
        "criteria": {
            "missing": "axial_coverage and unsupported_gap failed, with observed coverage < 0.35",
            "broken": "continuous support failed or a large unsupported gap remained, excluding missing criterion",
            "thin": "p90 radial deviation exceeded effective tolerance and signed deviation was negative",
            "thick": "p90 radial deviation exceeded effective tolerance and signed deviation was positive",
            "bent_or_misaligned": "centerline displacement failed; human review is required because registration can cause the same signal",
            "uncertain": "invalid, incomplete, conflicting, or near-threshold evidence",
            "healthy": "existing metrology decision was clearly inside declared tolerances",
        },
        "limitations": [
            "subtypes are evidence classifications, not manually confirmed ground truth",
            "missing versus broken uses a policy boundary at 35 percent axial support",
            "thin/thick depends on calibrated expected radius and registration uncertainty",
            "bent and registration offset cannot be separated automatically from this report alone",
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "methodology.md").write_text(
        "# Automated strut defect classification\n\n"
        "The classifier joins each expected STL/JSON strut to the existing raw-TIFF metrology record by `strut_id`. "
        "It preserves non-applicable CAD omissions and invalid measurements as exclusions or review cases. "
        "A confirmed subtype requires a declared metrology tolerance failure; ambiguous centerline offsets are "
        "reported as `bent_or_misaligned` review cases, not confirmed bends.\n\n"
        "The 35% axial-support boundary is a screening policy for separating a mostly absent strut from a broken "
        "one. It must be checked against human anchor labels before being treated as a validated scientific rule.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
