#!/usr/bin/env python3
"""Generate, inspect, and strictly validate all synthetic evidence images."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from Aman_Scripts.Components.strut_comparison import compare_strut_local
from Aman_Scripts.StrutComparisonVisualTests.render_cases import (
    analyze_png,
    build_contact_sheet,
    render_case,
)
from Aman_Scripts.StrutComparisonVisualTests.synthetic_cases import (
    build_visual_cases,
    public_case_spec,
)


DEFAULT_OUTPUT = REPOSITORY / "Aman_Scripts" / "outputs" / "strut_visual_tests"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        raise ValueError("manifest cannot contain NaN or infinity")
    return value


def _selected_metrics(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "comparison_applicable", "comparison_valid", "has_error", "review_required",
        "confidence", "decision_reason", "realized_axial_fraction",
        "longest_unrealized_gap_voxels", "bridge_connected_26",
        "perturbation_agreement", "valid_perturbation_trial_fraction",
        "stl_to_ct_near_fraction", "ct_crop_coverage", "axial_bin_count",
        "minimum_material_samples_per_bin", "realized_profile",
        "absolute_threshold_has_error", "absolute_threshold_decision_reason",
        "contrast_method", "contrast_review_authorized", "contrast_decision_reason",
        "contrast_valid_shift_count", "contrast_pass_shift_count",
        "contrast_required_pass_count", "contrast_shift_agreement",
        "contrast_shift_trials", "contrast_parameters",
        "local_contrast_realized_fraction", "local_contrast_profile",
        "support_intensity_profile", "local_background_median_profile",
        "local_background_noise_profile", "adaptive_lower_threshold_profile",
        "local_contrast_fraction_profile", "annulus_valid_profile",
        "annulus_contamination_fraction_profile",
        "contrast_low_path_connected_26", "contrast_annulus_valid_fraction",
        "contrast_longest_unsupported_gap_voxels",
    )
    return _json_safe({key: result.get(key) for key in keys})


def _validate_manifest(manifest: dict[str, Any], output_directory: Path) -> None:
    """Reject incomplete, non-deterministic, or visually empty evidence."""

    required_top = {
        "schema_version", "case_count", "outcome_match_count", "outcome_mismatch_count",
        "all_expected_outcomes_match", "all_images_pass_visual_checks", "cases",
        "contact_sheet",
    }
    if not required_top <= manifest.keys():
        raise AssertionError(f"manifest top-level keys missing: {required_top - manifest.keys()}")
    if manifest["case_count"] < 12 or manifest["case_count"] != len(manifest["cases"]):
        raise AssertionError("visual suite must contain at least 12 uniquely recorded cases")
    case_ids = [case["case_id"] for case in manifest["cases"]]
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        raise AssertionError("case IDs must be unique and sorted")
    for case in manifest["cases"]:
        required_case = {
            "case_id", "description", "physical_has_error", "expected_has_error",
            "actual_has_error", "outcome_matches_expectation", "input", "metrics", "image",
        }
        if not required_case <= case.keys():
            raise AssertionError(f"incomplete case record: {case.get('case_id')}")
        image_path = output_directory / case["image"]["filename"]
        if not image_path.is_file() or not case["image"]["visual_checks_pass"]:
            raise AssertionError(f"visual evidence failed QA: {image_path}")
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if digest != case["image"]["sha256"]:
            raise AssertionError(f"image digest mismatch: {image_path}")
    json.dumps(manifest, sort_keys=True, allow_nan=False)


def generate_visual_evidence(output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Run every comparison, create PNGs, and return the validated manifest."""

    output_directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    case_paths: list[Path] = []
    for case in build_visual_cases():
        result = dict(compare_strut_local(
            case.volume_zyx,
            case.endpoint0_xyz,
            case.endpoint1_xyz,
            case.surface_xyz,
            thresholds=case.thresholds,
            central_threshold=case.thresholds[len(case.thresholds) // 2],
            distance_tolerance_voxels=case.distance_tolerance_voxels,
            endpoint_exclusion_fraction=0.10,
            axial_step_voxels=1.0,
            minimum_supported_bin_fraction=0.20,
            minimum_gap_voxels=3,
            minimum_realized_fraction=0.80,
            minimum_perturbation_agreement=0.80,
            expected_present_override=True,
            expected_radius_voxels=case.expected_radius_voxels,
        ))
        image_path = render_case(case, result, output_directory / f"{case.case_id}.png")
        case_paths.append(image_path)
        input_spec = public_case_spec(case)
        records.append({
            "case_id": case.case_id,
            "description": case.description,
            "physical_has_error": case.physical_has_error,
            "expected_has_error": case.expected_has_error,
            "actual_has_error": result.get("has_error"),
            "outcome_matches_expectation": result.get("has_error") is case.expected_has_error,
            "input": input_spec,
            "metrics": _selected_metrics(result),
            "image": analyze_png(image_path),
        })
    records.sort(key=lambda item: item["case_id"])
    contact_path = build_contact_sheet(case_paths, output_directory / "contact_sheet.png")
    contact_analysis = analyze_png(contact_path)
    # Contact-sheet dimensions differ from individual figures by construction.
    contact_analysis["visual_checks_pass"] = bool(
        contact_analysis["byte_count"] > 100_000
        and contact_analysis["nonwhite_pixel_fraction"] > 0.05
    )
    match_count = sum(bool(record["outcome_matches_expectation"]) for record in records)
    manifest = {
        "schema_version": "1.0.0",
        "purpose": (
            "Synthetic native-resolution CT-versus-STL strut comparison with independent "
            "physical truth, expected conservative decisions, and inspectable PNG evidence."
        ),
        "coordinate_contract": {
            "volume_index_order": "ZYX",
            "endpoint_and_surface_order": "XYZ",
            "projection_interpolation": "nearest",
            "downsampling": False,
        },
        "case_count": len(records),
        "outcome_match_count": match_count,
        "outcome_mismatch_count": len(records) - match_count,
        "all_expected_outcomes_match": match_count == len(records),
        "all_images_pass_visual_checks": all(
            bool(record["image"]["visual_checks_pass"]) for record in records
        ) and bool(contact_analysis["visual_checks_pass"]),
        "cases": records,
        "contact_sheet": contact_analysis,
    }
    manifest = _json_safe(manifest)
    _validate_manifest(manifest, output_directory)
    manifest_path = output_directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-outcome-mismatches", action="store_true",
        help="Still generate evidence but return success when the comparator disagrees with truth.",
    )
    arguments = parser.parse_args()
    manifest = generate_visual_evidence(arguments.output_dir.resolve())
    print(json.dumps({
        "output_directory": str(arguments.output_dir.resolve()),
        "case_count": manifest["case_count"],
        "outcome_match_count": manifest["outcome_match_count"],
        "outcome_mismatch_count": manifest["outcome_mismatch_count"],
        "all_images_pass_visual_checks": manifest["all_images_pass_visual_checks"],
    }, indent=2, sort_keys=True))
    if not manifest["all_images_pass_visual_checks"]:
        return 2
    if not manifest["all_expected_outcomes_match"] and not arguments.allow_outcome_mismatches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
