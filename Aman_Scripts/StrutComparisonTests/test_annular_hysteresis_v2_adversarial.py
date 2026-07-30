"""Adversarial regression tests for ``annular_hysteresis_v2``.

The adaptive path may only downgrade a confirmed absolute-threshold error to
human review.  These cases attack its connectivity, high-threshold seeding,
annular-background, perturbation, and oblique-geometry safeguards.  A result
from this module is never allowed to turn suspicious evidence into healthy.
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


SHAPE = (65, 65, 65)
START = (15.0, 32.0, 32.0)
END = (49.0, 32.0, 32.0)
OBLIQUE_START = (15.0, 16.0, 17.0)
OBLIQUE_END = (48.0, 47.0, 45.0)
THRESHOLDS = (95.0, 100.0, 105.0)


def compare(
    volume: np.ndarray,
    *,
    start: tuple[float, float, float] = START,
    end: tuple[float, float, float] = END,
    radius: float = 2.0,
    alpha: float | None = 0.25,
) -> dict[str, object]:
    """Run the public comparator with fixed native-voxel test controls."""

    surface = cylinder_surface_points(
        start_xyz=start,
        end_xyz=end,
        radius=radius,
    )
    return dict(compare_strut_local(
        volume,
        start,
        end,
        surface,
        thresholds=THRESHOLDS,
        central_threshold=100.0,
        distance_tolerance_voxels=2.0,
        endpoint_exclusion_fraction=0.10,
        minimum_supported_bin_fraction=0.20,
        minimum_gap_voxels=3,
        minimum_realized_fraction=0.80,
        minimum_perturbation_agreement=0.80,
        minimum_local_contrast_fraction=alpha,
        expected_radius_voxels=radius,
    ))


def ramp_cylinder(
    *,
    start: tuple[float, float, float] = START,
    end: tuple[float, float, float] = END,
    radius: float = 2.0,
    low: float = 80.0,
    high: float = 120.0,
) -> np.ndarray:
    """Return a connected cylinder with intensity crossing 100 smoothly."""

    _, fraction, distance = segment_geometry(SHAPE, start, end)
    material = (fraction >= 0.0) & (fraction <= 1.0) & (distance <= radius)
    volume = np.zeros(SHAPE, dtype=np.uint16)
    ramp = np.rint(low + (high - low) * fraction).astype(np.uint16)
    volume[material] = ramp[material]
    return volume


def bright_cylinder_with_gap(
    *,
    start: tuple[float, float, float] = START,
    end: tuple[float, float, float] = END,
    radius: float = 2.0,
) -> np.ndarray:
    return cylinder_volume(
        shape_zyx=SHAPE,
        start_xyz=start,
        end_xyz=end,
        radius=radius,
        value=200,
        removed_fraction_ranges=((0.40, 0.60),),
    )


def faint_hollow_bridge(intensity: int) -> np.ndarray:
    """Fill a true bright-cylinder gap with a faint connected hollow shell."""

    volume = bright_cylinder_with_gap()
    _, fraction, distance = segment_geometry(SHAPE, START, END)
    gap = (fraction >= 0.40) & (fraction <= 0.60)
    shell = gap & (distance >= 1.0) & (distance <= 2.0)
    volume[shell] = intensity
    return volume


def disconnected_faint_per_bin_volume() -> np.ndarray:
    """Place enough faint voxels per station but break 26-connectivity."""

    volume = np.zeros(SHAPE, dtype=np.uint16)
    # Bright terminal pieces satisfy the high-threshold seed requirement on
    # both sides.  Alternating middle triplets jump four voxels in Y, so no
    # faint component can span between those seeds.
    terminal = cylinder_volume(
        shape_zyx=SHAPE,
        start_xyz=START,
        end_xyz=END,
        radius=2.0,
        value=200,
    )
    volume[:, :, 15:21] = terminal[:, :, 15:21]
    volume[:, :, 44:50] = terminal[:, :, 44:50]
    for x in range(21, 44):
        y = 30 if x % 2 == 0 else 34
        volume[31:34, y, x] = 40
    return volume


def add_annulus_contamination(volume: np.ndarray) -> np.ndarray:
    """Fill the radial 5--6 voxel shell without entering the target core."""

    result = volume.copy()
    _, fraction, distance = segment_geometry(SHAPE, START, END)
    contaminant = (
        (fraction >= 0.0)
        & (fraction <= 1.0)
        & (distance >= 5.0)
        & (distance <= 6.0)
    )
    result[contaminant] = 200
    return result


def test_disconnected_faint_per_bin_voxels_remain_confirmed_error() -> None:
    result = compare(disconnected_faint_per_bin_volume())
    assert result["has_error"] is True
    assert result["contrast_review_authorized"] is False
    assert result["contrast_low_path_connected_26"] is False
    assert result["contrast_decision_reason"] == "no_admissible_annular_hysteresis_path"


@pytest.mark.parametrize("radius", [2.0, 3.0, 4.0])
def test_intact_gradient_is_review_consistently_across_radii(radius: float) -> None:
    result = compare(ramp_cylinder(radius=radius), radius=radius)
    assert result["has_error"] is None
    assert result["review_required"] is True
    assert result["comparison_valid"] is False
    assert result["absolute_threshold_has_error"] is True
    assert result["decision_reason"] == "subthreshold_connected_annular_contrast"
    assert result["contrast_method"] == "annular_hysteresis_v2"
    assert result["contrast_review_authorized"] is True


@pytest.mark.parametrize("faint_intensity", [24, 25, 26, 35])
def test_faint_hollow_gap_sweep_around_alpha_is_never_healthy(
    faint_intensity: int,
) -> None:
    result = compare(faint_hollow_bridge(faint_intensity))
    assert result["has_error"] in (True, None)
    assert result["has_error"] is not False


def test_connected_significant_faint_bridge_is_review() -> None:
    result = compare(faint_hollow_bridge(35))
    assert result["has_error"] is None
    assert result["contrast_review_authorized"] is True
    assert result["contrast_low_path_connected_26"] is True
    assert result["absolute_threshold_has_error"] is True


@pytest.mark.parametrize("offset", [1, 2, 3, 4, 5, 6])
def test_faint_parallel_neighbor_offset_sweep_is_never_healthy(offset: int) -> None:
    neighbor = cylinder_volume(
        shape_zyx=SHAPE,
        start_xyz=(START[0], START[1] + offset, START[2]),
        end_xyz=(END[0], END[1] + offset, END[2]),
        radius=1.0,
        value=40,
    )
    result = compare(neighbor)
    assert result["has_error"] in (True, None)
    assert result["has_error"] is not False
    if offset >= 4:
        assert result["has_error"] is True
        assert result["contrast_review_authorized"] is False


@pytest.mark.parametrize("background", [90, 95, 99])
def test_background_near_absolute_threshold_cannot_authorize_veto(
    background: int,
) -> None:
    volume = np.full(SHAPE, background, dtype=np.uint16)
    result = compare(volume)
    # At 95/99 the ordinary 95/100/105 threshold trials legitimately disagree
    # and can already force review.  The invariant under attack here is that
    # annular contrast itself never authorizes that downgrade.
    assert result["has_error"] in (True, None)
    assert result["has_error"] is not False
    assert result["contrast_review_authorized"] is False


def test_threshold_adjacent_random_noise_cannot_authorize_veto() -> None:
    generator = np.random.default_rng(20260728)
    noisy = np.rint(generator.normal(90.0, 3.0, size=SHAPE)).clip(0, 99).astype(np.uint16)
    result = compare(noisy)
    assert result["has_error"] is True
    assert result["contrast_review_authorized"] is False


def test_zero_alpha_is_invalid() -> None:
    with pytest.raises(StrutComparisonError, match="minimum_local_contrast_fraction"):
        compare(np.zeros(SHAPE, dtype=np.uint16), alpha=0.0)


def test_tiny_positive_alpha_does_not_turn_empty_volume_into_review() -> None:
    result = compare(np.zeros(SHAPE, dtype=np.uint16), alpha=1e-12)
    assert result["has_error"] is True
    assert result["contrast_review_authorized"] is False
    assert result["contrast_pass_shift_count"] == 0


def test_shift_evidence_reports_real_counts_and_requires_six_passes() -> None:
    result = compare(ramp_cylinder())
    trials = result["contrast_shift_trials"]
    assert isinstance(trials, list)
    assert len(trials) == 7
    assert result["contrast_valid_shift_count"] == sum(
        trial["valid"] is True for trial in trials
    )
    assert result["contrast_pass_shift_count"] == sum(
        trial["passed"] is True for trial in trials
    )
    assert result["contrast_required_pass_count"] == 6
    assert int(result["contrast_pass_shift_count"]) >= 6
    assert result["contrast_shift_agreement"] == pytest.approx(
        int(result["contrast_pass_shift_count"]) / 7.0
    )


def test_annulus_contamination_invalidates_otherwise_valid_gradient_veto() -> None:
    result = compare(add_annulus_contamination(ramp_cylinder()))
    assert result["has_error"] is True
    assert result["contrast_review_authorized"] is False
    assert result["contrast_annulus_valid_fraction"] < 0.95
    assert result["contrast_decision_reason"] == "insufficient_uncontaminated_annulus"


def test_oblique_intact_gradient_is_review() -> None:
    result = compare(
        ramp_cylinder(start=OBLIQUE_START, end=OBLIQUE_END),
        start=OBLIQUE_START,
        end=OBLIQUE_END,
    )
    assert result["has_error"] is None
    assert result["contrast_review_authorized"] is True
    assert result["absolute_threshold_has_error"] is True


def test_oblique_true_gap_remains_confirmed_error() -> None:
    result = compare(
        bright_cylinder_with_gap(start=OBLIQUE_START, end=OBLIQUE_END),
        start=OBLIQUE_START,
        end=OBLIQUE_END,
    )
    assert result["has_error"] is True
    assert result["contrast_review_authorized"] is False
    assert int(result["longest_unrealized_gap_voxels"]) >= 3


def test_annular_hysteresis_result_is_strict_json_safe() -> None:
    result = compare(ramp_cylinder())
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == result


def test_annular_hysteresis_result_is_deterministic() -> None:
    volume = add_annulus_contamination(ramp_cylinder())
    assert compare(volume) == compare(volume)
