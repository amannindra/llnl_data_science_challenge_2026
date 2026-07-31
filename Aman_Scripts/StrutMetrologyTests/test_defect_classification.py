"""Tests for the registration-stability gate in defect subtype classification."""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.defect_classification import classify_defect_subtype


def _centerline_record(**overrides):
    record = {
        "comparison_applicable": True,
        "measurement_valid": True,
        "failed_checks": ["centerline_displacement"],
        "observed_axial_fraction": 0.98,
        "longest_unsupported_gap_voxels": 0.0,
        "median_signed_radial_deviation_voxels": 0.05,
        "p90_absolute_radial_deviation_voxels": 0.20,
        "effective_radial_tolerance_voxels": 1.0,
        "p90_centerline_displacement_voxels": 2.0,
        "effective_centerline_tolerance_voxels": 1.9,
        "registration_uncertainty_voxels": 1.2,
    }
    record.update(overrides)
    return record


def test_marginal_centerline_excess_is_demoted_to_uncertain():
    result = classify_defect_subtype(_centerline_record())
    assert result["defect_type"] == "uncertain"
    assert result["classification_reason"] == "centerline_offset_within_registration_stability_band"


def test_large_centerline_excess_stays_confirmed_bent_or_misaligned():
    result = classify_defect_subtype(
        _centerline_record(p90_centerline_displacement_voxels=5.0)
    )
    assert result["defect_type"] == "bent_or_misaligned"


def test_missing_registration_uncertainty_falls_back_to_unconditional_confirmation():
    record = _centerline_record()
    del record["registration_uncertainty_voxels"]
    result = classify_defect_subtype(record)
    assert result["defect_type"] == "bent_or_misaligned"
    assert result["classification_reason"] == "centerline_offset_cannot_separate_bend_from_registration"


def test_low_coverage_large_gap_is_still_classified_as_missing():
    record = {
        "comparison_applicable": True,
        "measurement_valid": True,
        "failed_checks": ["axial_coverage", "unsupported_gap"],
        "observed_axial_fraction": 0.10,
        "longest_unsupported_gap_voxels": 5.0,
        "median_signed_radial_deviation_voxels": 0.0,
        "p90_absolute_radial_deviation_voxels": 0.10,
    }
    result = classify_defect_subtype(record)
    assert result["defect_type"] == "missing"
    assert result["classification_status"] == "confirmed"


def test_partial_coverage_large_gap_is_still_classified_as_broken():
    record = {
        "comparison_applicable": True,
        "measurement_valid": True,
        "failed_checks": ["axial_coverage", "unsupported_gap"],
        "observed_axial_fraction": 0.50,
        "longest_unsupported_gap_voxels": 5.0,
        "median_signed_radial_deviation_voxels": 0.0,
        "p90_absolute_radial_deviation_voxels": 0.10,
    }
    result = classify_defect_subtype(record)
    assert result["defect_type"] == "broken"
    assert result["classification_status"] == "confirmed"


def test_inside_tolerance_measurement_is_still_classified_as_healthy():
    record = {
        "comparison_applicable": True,
        "measurement_valid": True,
        "failed_checks": [],
        "observed_axial_fraction": 0.98,
        "longest_unsupported_gap_voxels": 0.0,
        "median_signed_radial_deviation_voxels": 0.05,
        "p90_absolute_radial_deviation_voxels": 0.20,
        "effective_radial_tolerance_voxels": 1.0,
        "has_error": False,
    }
    result = classify_defect_subtype(record)
    assert result["defect_type"] == "healthy"
    assert result["classification_status"] == "accepted"
