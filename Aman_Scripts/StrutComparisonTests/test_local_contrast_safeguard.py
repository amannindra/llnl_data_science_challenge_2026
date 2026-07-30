"""Adversarial tests for the local-intensity-contrast safeguard.

The safeguard has one narrow responsibility: a smooth, continuous strut that
falls below an absolute CT threshold must become review-required instead of a
confirmed defect.  It must not erase the original threshold evidence and must
not hide genuinely absent or interrupted struts.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from Aman_Scripts.Components.strut_comparison import (
    StrutComparisonError,
    compare_strut_local,
)

from _synthetic import cylinder_surface_points, cylinder_volume, segment_geometry


START = (6.0, 20.0, 20.0)
END = (34.0, 20.0, 20.0)
SURFACE = cylinder_surface_points(start_xyz=START, end_xyz=END)
PROFILE_KEYS = (
    "local_contrast_profile",
    "support_intensity_profile",
    "local_background_median_profile",
    "local_contrast_fraction_profile",
    "realized_profile",
    "realized_bin_support_fraction",
    "realized_bin_material_area_ratio",
)


def compare(
    volume: np.ndarray,
    *,
    minimum_local_contrast_fraction: float = 0.25,
) -> dict[str, object]:
    """Run the production comparator with fixed, auditable synthetic settings."""

    return dict(compare_strut_local(
        volume,
        START,
        END,
        SURFACE,
        thresholds=(95.0, 100.0, 105.0),
        central_threshold=100.0,
        distance_tolerance_voxels=2.0,
        endpoint_exclusion_fraction=0.10,
        minimum_supported_bin_fraction=0.20,
        minimum_gap_voxels=3,
        minimum_realized_fraction=0.80,
        minimum_perturbation_agreement=0.80,
        minimum_local_contrast_fraction=minimum_local_contrast_fraction,
    ))


def continuous_axial_gradient(
    *,
    low: float = 80.0,
    high: float = 120.0,
) -> np.ndarray:
    """Return an unbroken cylinder whose intensity crosses threshold smoothly."""

    _, fraction, distance = segment_geometry(
        start_xyz=START,
        end_xyz=END,
    )
    material = (fraction >= 0.0) & (fraction <= 1.0) & (distance <= 2.0)
    volume = np.zeros(fraction.shape, dtype=np.uint16)
    ramp = np.rint(low + (high - low) * fraction).astype(np.uint16)
    volume[material] = ramp[material]
    return volume


def test_continuous_threshold_crossing_becomes_review_not_confirmed_error() -> None:
    result = compare(continuous_axial_gradient())
    assert result["has_error"] is None
    assert result["comparison_valid"] is False
    assert result["review_required"] is True
    assert result["decision_reason"] == "subthreshold_connected_annular_contrast"


def test_continuous_threshold_crossing_preserves_absolute_decision() -> None:
    result = compare(continuous_axial_gradient())
    assert result["absolute_threshold_has_error"] is True
    assert result["absolute_threshold_decision_reason"] in {
        "low_stl_realization+continuous_unrealized_gap+broken_ct_bridge",
        "low_stl_realization+continuous_unrealized_gap",
        "low_stl_realization+broken_ct_bridge",
        "low_stl_realization",
    }
    assert float(result["realized_axial_fraction"]) < 0.80
    assert float(result["local_contrast_realized_fraction"]) >= 0.80


def test_true_missing_strut_remains_confirmed_error() -> None:
    result = compare(np.zeros((41, 41, 41), dtype=np.uint16))
    assert result["has_error"] is True
    assert result["review_required"] is True
    assert result["realized_axial_fraction"] == pytest.approx(0.0)
    assert result["local_contrast_realized_fraction"] == pytest.approx(0.0)
    assert "absolute_threshold_has_error" not in result


def test_true_transverse_gap_remains_confirmed_error() -> None:
    volume = cylinder_volume(
        value=200,
        removed_fraction_ranges=((0.40, 0.60),),
    )
    result = compare(volume)
    assert result["has_error"] is True
    assert int(result["longest_unrealized_gap_voxels"]) >= 3
    assert float(result["local_contrast_realized_fraction"]) < 1.0
    assert "absolute_threshold_has_error" not in result


def test_parallel_near_neighbor_does_not_fake_target_strut() -> None:
    neighbor = cylinder_volume(
        start_xyz=(6.0, 27.0, 20.0),
        end_xyz=(34.0, 27.0, 20.0),
        radius=2.0,
        value=200,
    )
    result = compare(neighbor)
    assert result["has_error"] is True
    assert float(result["realized_axial_fraction"]) < 0.80
    assert float(result["local_contrast_realized_fraction"]) < 0.80


def test_safeguard_never_promotes_absolute_healthy_result_to_error() -> None:
    result = compare(cylinder_volume(value=200))
    assert result["has_error"] is False
    assert result["review_required"] is False
    assert "absolute_threshold_has_error" not in result


@pytest.mark.parametrize(
    "minimum_local_contrast_fraction",
    [-0.01, 0.0, 1.01, np.nan, np.inf, -np.inf],
)
def test_invalid_minimum_local_contrast_fraction_is_rejected(
    minimum_local_contrast_fraction: float,
) -> None:
    with pytest.raises(
        StrutComparisonError,
        match="minimum_local_contrast_fraction",
    ):
        compare(
            cylinder_volume(value=200),
            minimum_local_contrast_fraction=minimum_local_contrast_fraction,
        )


@pytest.mark.parametrize("boundary", [np.nextafter(0.0, 1.0), 1.0])
def test_local_contrast_fraction_boundaries_are_valid(boundary: float) -> None:
    result = compare(cylinder_volume(value=200), minimum_local_contrast_fraction=boundary)
    assert result["minimum_local_contrast_fraction"] == boundary


def test_none_explicitly_disables_local_contrast_review() -> None:
    result = compare_strut_local(
        continuous_axial_gradient(),
        START,
        END,
        SURFACE,
        thresholds=(95.0, 100.0, 105.0),
        central_threshold=100.0,
        minimum_local_contrast_fraction=None,
    )
    assert result["has_error"] is True
    assert result["contrast_method"] == "disabled"


@pytest.mark.parametrize(
    "volume",
    [
        pytest.param(continuous_axial_gradient(), id="continuous-gradient"),
        pytest.param(np.zeros((41, 41, 41), dtype=np.uint16), id="missing"),
        pytest.param(
            cylinder_volume(
                value=200,
                removed_fraction_ranges=((0.40, 0.60),),
            ),
            id="true-gap",
        ),
    ],
)
def test_all_local_evidence_profiles_match_axial_bin_count(
    volume: np.ndarray,
) -> None:
    result = compare(volume)
    bins = int(result["axial_bin_count"])
    assert bins > 0
    for key in PROFILE_KEYS:
        assert isinstance(result[key], list), key
        assert len(result[key]) == bins, key


@pytest.mark.parametrize(
    "volume",
    [
        pytest.param(continuous_axial_gradient(), id="continuous-gradient"),
        pytest.param(np.zeros((41, 41, 41), dtype=np.uint16), id="missing"),
        pytest.param(
            cylinder_volume(
                value=200,
                removed_fraction_ranges=((0.40, 0.60),),
            ),
            id="true-gap",
        ),
    ],
)
def test_local_contrast_result_is_strict_json_safe(volume: np.ndarray) -> None:
    result = compare(volume)
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == result


def test_continuous_gradient_decision_and_profiles_are_deterministic() -> None:
    volume = continuous_axial_gradient()
    assert compare(volume) == compare(volume)
