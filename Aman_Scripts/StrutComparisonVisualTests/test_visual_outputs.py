"""Automated contract tests for generated synthetic images and their manifest."""

from __future__ import annotations

import json

from Aman_Scripts.StrutComparisonVisualTests.run_visual_tests import generate_visual_evidence


ADVERSARIAL_CASE_IDS = {
    "21_thick_gradient_crosses_thresholds",
    "22_disconnected_faint_per_bin_support",
    "23_gap_with_faint_connected_halo",
    "24_background_near_threshold_noise",
    "25_bright_annulus_contamination",
    "26_oblique_gradient_crosses_thresholds",
}

CONTRAST_PROFILE_FIELDS = (
    "local_contrast_profile",
    "support_intensity_profile",
    "local_background_median_profile",
    "local_background_noise_profile",
    "adaptive_lower_threshold_profile",
    "local_contrast_fraction_profile",
    "annulus_valid_profile",
    "annulus_contamination_fraction_profile",
)


def test_all_synthetic_truth_cases_and_images(tmp_path) -> None:
    manifest = generate_visual_evidence(tmp_path / "visual")
    assert manifest["case_count"] >= 12
    assert manifest["all_images_pass_visual_checks"] is True
    assert manifest["all_expected_outcomes_match"] is True, [
        case["case_id"] for case in manifest["cases"]
        if not case["outcome_matches_expectation"]
    ]


def test_manifest_is_strict_json_and_references_every_png(tmp_path) -> None:
    output = tmp_path / "visual"
    manifest = generate_visual_evidence(output)
    encoded = json.dumps(manifest, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == manifest
    case_pngs = {case["image"]["filename"] for case in manifest["cases"]}
    assert case_pngs == {path.name for path in output.glob("[0-9][0-9]_*.png")}
    assert (output / manifest["contact_sheet"]["filename"]).is_file()


def test_rendering_and_metrics_are_deterministic(tmp_path) -> None:
    first = generate_visual_evidence(tmp_path / "first")
    second = generate_visual_evidence(tmp_path / "second")
    for first_case, second_case in zip(first["cases"], second["cases"], strict=True):
        assert first_case["case_id"] == second_case["case_id"]
        assert first_case["metrics"] == second_case["metrics"]
        assert first_case["image"]["sha256"] == second_case["image"]["sha256"]


def test_adversarial_annular_hysteresis_cases_are_all_present(tmp_path) -> None:
    manifest = generate_visual_evidence(tmp_path / "visual")
    case_ids = {case["case_id"] for case in manifest["cases"]}
    assert ADVERSARIAL_CASE_IDS <= case_ids
    for case in manifest["cases"]:
        if case["case_id"] not in ADVERSARIAL_CASE_IDS:
            continue
        # A defect case may be ERROR or REVIEW, but never silently healthy.
        if case["physical_has_error"] is True:
            assert case["actual_has_error"] is not False


def test_evaluated_contrast_records_have_complete_profile_evidence(tmp_path) -> None:
    manifest = generate_visual_evidence(tmp_path / "visual")
    evaluated = [
        case for case in manifest["cases"]
        if case["metrics"]["contrast_method"] == "annular_hysteresis_v2"
    ]
    assert evaluated
    for case in evaluated:
        metrics = case["metrics"]
        bins = metrics["axial_bin_count"]
        assert isinstance(bins, int) and bins > 0
        for field in CONTRAST_PROFILE_FIELDS:
            assert isinstance(metrics[field], list), (case["case_id"], field)
            assert len(metrics[field]) == bins, (case["case_id"], field)
        trials = metrics["contrast_shift_trials"]
        assert isinstance(trials, list) and 1 <= len(trials) <= 7
        assert metrics["contrast_valid_shift_count"] == sum(
            trial["valid"] is True for trial in trials
        )
        assert metrics["contrast_pass_shift_count"] == sum(
            trial["passed"] is True for trial in trials
        )
        if metrics["contrast_review_authorized"] is True:
            assert case["actual_has_error"] is None
            assert metrics["absolute_threshold_has_error"] is True
            assert metrics["contrast_pass_shift_count"] >= metrics["contrast_required_pass_count"]
            assert metrics["contrast_low_path_connected_26"] is True
        else:
            assert case["actual_has_error"] is True


def test_adversarial_cases_reach_the_intended_evidence_branches(tmp_path) -> None:
    manifest = generate_visual_evidence(tmp_path / "visual")
    cases = {case["case_id"]: case for case in manifest["cases"]}

    for case_id in (
        "21_thick_gradient_crosses_thresholds",
        "23_gap_with_faint_connected_halo",
        "26_oblique_gradient_crosses_thresholds",
    ):
        metrics = cases[case_id]["metrics"]
        assert cases[case_id]["actual_has_error"] is None
        assert metrics["contrast_review_authorized"] is True
        assert metrics["contrast_decision_reason"] == "stable_annular_hysteresis_continuity"
        assert metrics["contrast_low_path_connected_26"] is True
        assert metrics["contrast_pass_shift_count"] >= metrics["contrast_required_pass_count"]

    disconnected = cases["22_disconnected_faint_per_bin_support"]
    assert disconnected["actual_has_error"] is True
    assert disconnected["metrics"]["contrast_review_authorized"] is False
    assert disconnected["metrics"]["contrast_low_path_connected_26"] is False
    assert disconnected["metrics"]["contrast_decision_reason"] == (
        "no_admissible_annular_hysteresis_path"
    )

    noisy = cases["24_background_near_threshold_noise"]
    assert noisy["actual_has_error"] is True
    assert noisy["metrics"]["contrast_review_authorized"] is False
    assert noisy["metrics"]["contrast_low_path_connected_26"] is False

    contaminated = cases["25_bright_annulus_contamination"]
    assert contaminated["actual_has_error"] is True
    assert contaminated["metrics"]["contrast_review_authorized"] is False
    assert contaminated["metrics"]["contrast_valid_shift_count"] == 0
    assert contaminated["metrics"]["contrast_decision_reason"] == (
        "insufficient_uncontaminated_annulus"
    )
