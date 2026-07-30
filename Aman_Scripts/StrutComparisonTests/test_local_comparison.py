"""Synthetic native-voxel checks for direct local STL-surface/CT comparison."""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from Aman_Scripts.Components.strut_comparison import compare_strut_local

from _synthetic import (
    add_endpoint_blobs,
    add_speckle_noise,
    cylinder_surface_points,
    cylinder_volume,
)


START = (6.0, 20.0, 20.0)
END = (34.0, 20.0, 20.0)
SURFACE = cylinder_surface_points(start_xyz=START, end_xyz=END)


def compare(
    volume: np.ndarray,
    *,
    start: tuple[float, float, float] = START,
    end: tuple[float, float, float] = END,
    surface: np.ndarray = SURFACE,
    thresholds: tuple[float, ...] = (100.0,),
    tolerance: float = 2.0,
) -> dict[str, object]:
    return dict(compare_strut_local(
        volume,
        start,
        end,
        surface,
        thresholds=thresholds,
        distance_tolerance_voxels=tolerance,
        endpoint_exclusion_fraction=0.10,
        minimum_supported_bin_fraction=0.20,
        minimum_gap_voxels=3,
        minimum_realized_fraction=0.80,
        minimum_perturbation_agreement=0.80,
    ))


def assert_decision(result: dict[str, object], expected: bool | None) -> None:
    assert result["has_error"] is expected
    # Every detected mismatch is a candidate for human confirmation; only a
    # stable healthy result is exempt from review.
    assert result["review_required"] is (expected is not False)


def test_matching_native_resolution_cylinder_is_healthy() -> None:
    result = compare(cylinder_volume())
    assert_decision(result, False)
    assert float(result["realized_axial_fraction"]) >= 0.80


def test_empty_ct_corridor_is_error() -> None:
    result = compare(np.zeros((41, 41, 41), dtype=np.uint16))
    assert_decision(result, True)
    assert result["bridge_connected_26"] is False


def test_midspan_gap_is_error() -> None:
    volume = cylinder_volume(removed_fraction_ranges=((0.40, 0.60),))
    result = compare(volume)
    assert_decision(result, True)
    assert int(result["longest_unrealized_gap_voxels"]) >= 3


def test_endpoint_break_survives_junction_exclusion() -> None:
    volume = cylinder_volume(removed_fraction_ranges=((0.0, 0.25),))
    result = compare(volume)
    assert_decision(result, True)


def test_bright_endpoint_blobs_do_not_fake_strut_body() -> None:
    volume = add_endpoint_blobs(np.zeros((41, 41, 41), dtype=np.uint16))
    result = compare(volume)
    assert_decision(result, True)
    assert float(result["realized_axial_fraction"]) < 0.80


def test_single_voxel_scale_pinhole_is_not_confirmed_error() -> None:
    volume = cylinder_volume()
    # An isolated missing voxel is segmentation noise, not a transverse break.
    volume[20, 20, 20] = 0
    result = compare(volume)
    assert_decision(result, False)
    assert int(result["longest_unrealized_gap_voxels"]) < 3


def test_one_voxel_lateral_shift_is_within_surface_tolerance() -> None:
    shifted = cylinder_volume(
        start_xyz=(6.0, 21.0, 20.0), end_xyz=(34.0, 21.0, 20.0)
    )
    assert_decision(compare(shifted), False)


def test_large_lateral_shift_is_not_silently_healthy() -> None:
    shifted = cylinder_volume(
        start_xyz=(6.0, 26.0, 20.0), end_xyz=(34.0, 26.0, 20.0)
    )
    assert compare(shifted)["has_error"] in (True, None)


def test_thicker_continuous_ct_strut_is_not_missing_or_broken() -> None:
    assert_decision(compare(cylinder_volume(radius=4.0)), False)


def test_thinner_but_continuous_ct_strut_within_tolerance_is_healthy() -> None:
    assert_decision(compare(cylinder_volume(radius=1.0)), False)


def test_random_bright_speckles_do_not_fake_continuity() -> None:
    noisy = add_speckle_noise(
        np.zeros((41, 41, 41), dtype=np.uint16), count=300
    )
    assert_decision(compare(noisy), True)


def test_parallel_neighbor_outside_tolerance_does_not_fill_target() -> None:
    neighbor = cylinder_volume(
        start_xyz=(6.0, 27.0, 20.0), end_xyz=(34.0, 27.0, 20.0)
    )
    assert compare(neighbor)["has_error"] in (True, None)


def test_diagonal_xyz_segment_samples_correct_zyx_voxels() -> None:
    start = (7.0, 8.0, 9.0)
    end = (31.0, 30.0, 28.0)
    volume = cylinder_volume(start_xyz=start, end_xyz=end)
    surface = cylinder_surface_points(start_xyz=start, end_xyz=end)
    assert_decision(compare(volume, start=start, end=end, surface=surface), False)


def test_threshold_disagreement_requires_review() -> None:
    volume = cylinder_volume(value=100)
    result = compare(volume, thresholds=(90.0, 100.0, 110.0))
    assert_decision(result, None)
    assert float(result["perturbation_agreement"]) < 0.80


def test_one_voxel_registration_perturbation_disagreement_requires_review() -> None:
    # A deliberately one-voxel-thick synthetic line is aligned centrally but
    # disappears for transverse +/-1 voxel perturbations.  It must not produce
    # a confident binary decision.
    volume = cylinder_volume(radius=0.0)
    surface = np.asarray([[x, 20.0, 20.0] for x in range(6, 35)], dtype=np.float64)
    result = compare(volume, surface=surface, tolerance=0.1)
    assert_decision(result, None)
    assert float(result["perturbation_agreement"]) < 0.80


def test_out_of_bounds_corridor_is_unobservable_not_missing() -> None:
    start = (-8.0, 20.0, 20.0)
    end = (10.0, 20.0, 20.0)
    surface = cylinder_surface_points(start_xyz=start, end_xyz=end)
    result = compare(
        np.zeros((41, 41, 41), dtype=np.uint16),
        start=start,
        end=end,
        surface=surface,
    )
    assert_decision(result, None)
    assert result["comparison_valid"] is False


def test_comparison_is_deterministic() -> None:
    volume = cylinder_volume(removed_fraction_ranges=((0.40, 0.60),))
    assert compare(volume) == compare(volume)


def test_local_result_has_visualization_writer_evidence_contract() -> None:
    result = compare(cylinder_volume())
    required = {
        "comparison_valid", "stl_expected_present", "has_error",
        "review_required", "confidence", "stl_to_ct_near_fraction",
        "ct_to_stl_near_fraction", "realized_axial_fraction",
        "longest_unrealized_gap_voxels", "bridge_connected_26",
        "perturbation_agreement", "decision_reason",
    }
    assert required <= result.keys()


def test_local_result_is_strict_json_serializable_and_stable() -> None:
    result = compare(cylinder_volume())
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert encoded == json.dumps(result, sort_keys=True, allow_nan=False)


def test_comparison_does_not_mutate_ct_or_stl_samples() -> None:
    volume = cylinder_volume()
    surface = SURFACE.copy()
    volume_before = volume.copy()
    surface_before = surface.copy()
    compare(volume, surface=surface)
    np.testing.assert_array_equal(volume, volume_before)
    np.testing.assert_array_equal(surface, surface_before)


def test_public_local_comparison_has_no_downsampling_parameter() -> None:
    assert "downsample" not in inspect.signature(compare_strut_local).parameters


def test_healthy_overlap_fractions_are_bounded() -> None:
    result = compare(cylinder_volume())
    for key in ("stl_to_ct_near_fraction", "realized_axial_fraction"):
        assert 0.0 <= float(result[key]) <= 1.0


@pytest.mark.parametrize(
    ("volume", "start", "end", "surface", "thresholds"),
    [
        (np.zeros((4, 4), dtype=np.uint16), START, END, SURFACE, (100.0,)),
        (np.zeros((41, 41, 41), dtype=np.uint16), START, START, SURFACE, (100.0,)),
        (np.zeros((41, 41, 41), dtype=np.uint16), START, END, np.zeros((3, 2)), (100.0,)),
        (np.zeros((41, 41, 41), dtype=np.uint16), START, END, SURFACE, ()),
    ],
)
def test_invalid_local_inputs_are_rejected(
    volume: np.ndarray,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    surface: np.ndarray,
    thresholds: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        compare(volume, start=start, end=end, surface=surface, thresholds=thresholds)
