"""Conservative subtype classification for STL-to-TIFF strut evidence.

This module classifies the output of ``strut_metrology``.  It does not invent
measurements: every defect label is tied to an existing measurement and its
declared tolerance.  Ambiguous or invalid measurements remain review cases.
"""

from __future__ import annotations

from typing import Any


def _finite(record: dict[str, Any], name: str) -> float | None:
    value = record.get(name)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def classify_defect_subtype(record: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative defect type, status, and explanation.

    ``confirmed`` means the existing measurement decision exceeded a declared
    tolerance.  ``review`` means the evidence suggests a subtype but does not
    clear the confirmation gate.  ``uncertain`` means the measurement cannot
    support a subtype.  ``healthy`` is reserved for the existing clearly
    inside-tolerance decision.
    """

    if not record.get("comparison_applicable", False):
        return {
            "defect_type": "not_applicable",
            "classification_status": "excluded",
            "classification_confidence": "not_applicable",
            "classification_reason": record.get(
                "decision_reason", "comparison_not_applicable"
            ),
        }

    if record.get("measurement_valid") is not True:
        return {
            "defect_type": "uncertain",
            "classification_status": "review",
            "classification_confidence": "low",
            "classification_reason": record.get(
                "decision_reason", "insufficient_measurement_evidence"
            ),
        }

    coverage = _finite(record, "observed_axial_fraction")
    gap = _finite(record, "longest_unsupported_gap_voxels")
    radial = _finite(record, "median_signed_radial_deviation_voxels")
    radial_p90 = _finite(record, "p90_absolute_radial_deviation_voxels")
    radial_limit = _finite(record, "effective_radial_tolerance_voxels")
    failed = set(record.get("failed_checks") or [])

    if coverage is None or gap is None or radial is None or radial_p90 is None:
        return {
            "defect_type": "uncertain",
            "classification_status": "review",
            "classification_confidence": "low",
            "classification_reason": "required_subtype_measurement_missing",
        }

    # A strut with very little supported body and a large unsupported run is
    # treated as missing.  If some body remains, the same evidence is broken.
    # The 0.35 boundary is deliberately a reviewable policy threshold, not a
    # claim of physical ground truth.
    if {"axial_coverage", "unsupported_gap"}.issubset(failed):
        subtype = "missing" if coverage < 0.35 else "broken"
        return {
            "defect_type": subtype,
            "classification_status": "confirmed",
            "classification_confidence": "medium",
            "classification_reason": "low_axial_support_and_large_gap",
        }

    if "continuous_support" in failed or gap > 3.0:
        return {
            "defect_type": "broken",
            "classification_status": "confirmed",
            "classification_confidence": "medium",
            "classification_reason": "disconnected_or_unsupported_body",
        }

    if radial_limit is not None and radial_p90 > radial_limit:
        subtype = "thin" if radial < 0.0 else "thick"
        return {
            "defect_type": subtype,
            "classification_status": "confirmed",
            "classification_confidence": "medium",
            "classification_reason": "radial_deviation_exceeds_effective_tolerance",
        }

    if "centerline_displacement" in failed:
        center_p90 = _finite(record, "p90_centerline_displacement_voxels")
        center_limit = _finite(record, "effective_centerline_tolerance_voxels")
        reg_uncertainty = _finite(record, "registration_uncertainty_voxels")
        if center_p90 is not None and center_limit is not None and reg_uncertainty is not None:
            excess = center_p90 - center_limit
            if excess <= reg_uncertainty:
                return {
                    "defect_type": "uncertain",
                    "classification_status": "review",
                    "classification_confidence": "low",
                    "classification_reason": "centerline_offset_within_registration_stability_band",
                }
        return {
            "defect_type": "bent_or_misaligned",
            "classification_status": "review",
            "classification_confidence": "low",
            "classification_reason": "centerline_offset_cannot_separate_bend_from_registration",
        }

    if record.get("has_error") is False:
        return {
            "defect_type": "healthy",
            "classification_status": "accepted",
            "classification_confidence": "high",
            "classification_reason": record.get(
                "decision_reason", "inside_declared_tolerances"
            ),
        }

    return {
        "defect_type": "uncertain",
        "classification_status": "review",
        "classification_confidence": "low",
        "classification_reason": record.get(
            "decision_reason", "near_or_conflicting_tolerances"
        ),
    }


__all__ = ["classify_defect_subtype"]
