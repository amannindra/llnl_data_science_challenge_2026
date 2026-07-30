"""Adversarial tests for the compact native-CT strut metrology pipeline."""

from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.coordinates import apply_transform
from Components.ct_surface_metrology import (
    local_iso50_crossings,
    refine_rigid_registration,
    rigid_correction_matrix,
    sample_stl_surface_by_area,
    trilinear_sample,
)
from Components.strut_metrology import (
    classify_strut_measurement,
    measure_strut_cross_sections,
)
import run_simple_strut_metrology as cli


def _soft_plane(shape=(32, 32, 32), *, crossing_x=15.25, contrast=1000.0):
    z, y, x = np.indices(shape, dtype=np.float64)
    del z, y
    return 100.0 + contrast / (1.0 + np.exp((x - crossing_x) / 0.35))


def _box_surface_points(center, half, face_steps=10):
    center = np.asarray(center, dtype=np.float64)
    half = np.asarray(half, dtype=np.float64)
    points, normals = [], []
    coordinates = np.linspace(-0.8, 0.8, face_steps)
    for axis in range(3):
        others = [value for value in range(3) if value != axis]
        for sign in (-1.0, 1.0):
            for first in coordinates:
                for second in coordinates:
                    local = np.zeros(3, dtype=np.float64)
                    local[axis] = sign * half[axis]
                    local[others[0]] = first * half[others[0]]
                    local[others[1]] = second * half[others[1]]
                    normal = np.zeros(3, dtype=np.float64)
                    normal[axis] = sign
                    points.append(center + local)
                    normals.append(normal)
    return np.asarray(points), np.asarray(normals)


def _soft_rotated_box(shape, center, half, rotation, translation):
    z, y, x = np.indices(shape, dtype=np.float32)
    world = np.stack((x, y, z), axis=-1).astype(np.float64)
    center = np.asarray(center, dtype=np.float64)
    translation = np.asarray(translation, dtype=np.float64)
    local = (world - center - translation) @ rotation
    q = np.abs(local) - np.asarray(half, dtype=np.float64)
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    inside = np.minimum(np.maximum.reduce(q, axis=-1), 0.0)
    signed_distance = outside + inside
    return (100.0 + 1200.0 / (1.0 + np.exp(signed_distance / 0.40))).astype(np.float32)


def _soft_cylinder(
    shape=(52, 52, 52),
    endpoint0=(8.0, 26.0, 26.0),
    endpoint1=(43.0, 26.0, 26.0),
    *,
    radius=4.0,
    center_shift=(0.0, 0.0, 0.0),
    gap_fraction=None,
    contrast=1400.0,
):
    first = np.asarray(endpoint0, dtype=np.float64) + np.asarray(center_shift)
    second = np.asarray(endpoint1, dtype=np.float64) + np.asarray(center_shift)
    z, y, x = np.indices(shape, dtype=np.float32)
    points = np.stack((x, y, z), axis=-1).astype(np.float64)
    delta = second - first
    length_squared = float(delta @ delta)
    axial_fraction = np.clip(((points - first) @ delta) / length_squared, 0.0, 1.0)
    closest = first + axial_fraction[..., None] * delta
    radial = np.linalg.norm(points - closest, axis=-1)
    material = 100.0 + contrast / (1.0 + np.exp((radial - radius) / 0.35))
    if gap_fraction is not None:
        lower, upper = gap_fraction
        in_gap = (axial_fraction >= lower) & (axial_fraction <= upper)
        material[in_gap] = 100.0
    return material.astype(np.float32)


def _valid_measurement(**overrides):
    result = {
        "measurement_valid": True,
        "observed_axial_fraction": 0.98,
        "longest_unsupported_gap_voxels": 0.0,
        "connected_support": True,
        "median_signed_radial_deviation_voxels": 0.05,
        "p90_absolute_radial_deviation_voxels": 0.20,
        "p90_centerline_displacement_voxels": 0.15,
    }
    result.update(overrides)
    return result


def test_trilinear_sample_is_exact_for_a_linear_field():
    z, y, x = np.indices((8, 9, 10), dtype=np.float64)
    volume = x + 10.0 * y + 100.0 * z
    point = np.asarray([[2.25, 3.5, 4.75]])
    values, valid = trilinear_sample(volume, point)
    assert valid.tolist() == [True]
    assert values[0] == pytest.approx(2.25 + 35.0 + 475.0)


def test_trilinear_sample_marks_out_of_bounds_without_clipping():
    values, valid = trilinear_sample(np.zeros((5, 5, 5)), [[4.1, 2.0, 2.0]])
    assert valid.tolist() == [False]
    assert np.isnan(values[0])


def test_local_iso50_recovers_a_subvoxel_plane_crossing():
    result = local_iso50_crossings(
        _soft_plane(crossing_x=15.25), [[15.0, 12.0, 12.0]], [[1.0, 0.0, 0.0]],
        minimum_end_contrast=400.0,
    )
    assert result["valid"].tolist() == [True]
    assert result["crossing_offset_voxels"][0] == pytest.approx(0.25, abs=0.06)


def test_local_iso50_accepts_reversed_triangle_winding():
    result = local_iso50_crossings(
        _soft_plane(crossing_x=15.25), [[15.0, 12.0, 12.0]], [[-1.0, 0.0, 0.0]],
        minimum_end_contrast=400.0,
    )
    assert result["valid"].tolist() == [True]
    assert result["crossing_offset_voxels"][0] == pytest.approx(-0.25, abs=0.06)


def test_local_iso50_rejects_a_profile_without_material_contrast():
    result = local_iso50_crossings(
        np.full((20, 20, 20), 500.0), [[10.0, 10.0, 10.0]], [[1.0, 0.0, 0.0]],
        minimum_end_contrast=10.0,
    )
    assert result["valid"].tolist() == [False]


def test_local_iso50_rejects_an_incomplete_profile_instead_of_clipping():
    result = local_iso50_crossings(
        _soft_plane(), [[0.5, 10.0, 10.0]], [[1.0, 0.0, 0.0]],
        minimum_end_contrast=10.0,
    )
    assert result["in_bounds"].tolist() == [False]
    assert result["valid"].tolist() == [False]


def test_rigid_matrix_rotates_about_the_declared_pivot():
    matrix = rigid_correction_matrix((0.0, 0.0, math.pi / 2), (1.0, 0.0, 0.0), (2, 3, 4))
    pivot_after = apply_transform(np.asarray([[2.0, 3.0, 4.0]]), matrix)[0]
    assert pivot_after == pytest.approx((3.0, 3.0, 4.0))


def test_rigid_matrix_rejects_nonfinite_parameters():
    with pytest.raises(ValueError, match="rotation vector"):
        rigid_correction_matrix((np.nan, 0, 0), (0, 0, 0), (0, 0, 0))


def test_area_sampler_is_deterministic_and_transforms_normals(tmp_path):
    path = tmp_path / "two_triangles.stl"
    path.write_text(
        "solid test\n"
        "facet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 2 0 0\nvertex 0 2 0\nendloop\nendfacet\n"
        "facet normal 0 0 1\nouter loop\nvertex 3 0 0\nvertex 4 0 0\nvertex 3 1 0\nendloop\nendfacet\n"
        "endsolid test\n",
        encoding="utf-8",
    )
    transform = np.eye(4)
    transform[:3, 3] = (5, 6, 7)
    first = sample_stl_surface_by_area(path, transform, sample_count=100)
    second = sample_stl_surface_by_area(path, transform, sample_count=100)
    assert np.array_equal(first["points_xyz"], second["points_xyz"])
    assert np.array_equal(first["normals_xyz"], second["normals_xyz"])
    assert np.all(first["points_xyz"][:, 2] == pytest.approx(7.0))
    assert np.allclose(np.abs(first["normals_xyz"][:, 2]), 1.0)
    assert first["triangle_count"] == 2


def test_area_sampler_rejects_an_unsafe_tiny_sample(tmp_path):
    path = tmp_path / "empty.stl"
    path.write_text("solid empty\nendsolid empty\n", encoding="utf-8")
    with pytest.raises(ValueError, match=">= 100"):
        sample_stl_surface_by_area(path, np.eye(4), sample_count=10)


def test_registration_recovers_a_planted_small_rigid_correction():
    from scipy.spatial.transform import Rotation

    shape = (56, 58, 60)
    center = np.asarray((30.0, 28.0, 27.0))
    half = np.asarray((12.0, 9.0, 7.0))
    rotation_vector = np.radians((0.18, -0.12, 0.15))
    rotation = Rotation.from_rotvec(rotation_vector).as_matrix()
    translation = np.asarray((0.42, -0.31, 0.24))
    volume = _soft_rotated_box(shape, center, half, rotation, translation)
    points, normals = _box_surface_points(center, half, face_steps=9)
    result = refine_rigid_registration(
        volume, points, normals,
        maximum_iterations=8,
        minimum_end_contrast=300.0,
        maximum_translation_voxels=1.5,
        maximum_rotation_degrees=0.5,
    )
    planted = rigid_correction_matrix(rotation_vector, translation, center)
    recovered_points = apply_transform(points, result["correction_matrix"])
    planted_points = apply_transform(points, planted)
    assert np.median(np.linalg.norm(recovered_points - planted_points, axis=1)) < 0.20
    assert result["after_held_out"]["median_absolute_offset_voxels"] < (
        result["before_held_out"]["median_absolute_offset_voxels"]
    )


def test_registration_rejects_underconstrained_parallel_normals():
    points = np.stack((
        np.full(125, 15.0),
        np.repeat(np.linspace(5, 25, 5), 25),
        np.tile(np.repeat(np.linspace(5, 25, 5), 5), 5),
    ), axis=1)
    normals = np.tile((1.0, 0.0, 0.0), (len(points), 1))
    with pytest.raises(RuntimeError, match="constrain all six"):
        refine_rigid_registration(
            _soft_plane(), points, normals,
            minimum_end_contrast=300.0,
            maximum_iterations=1,
        )


def test_registration_rejects_insufficient_valid_surface_fraction():
    points, normals = _box_surface_points((16, 16, 16), (6, 5, 4), face_steps=5)
    with pytest.raises(RuntimeError, match="surface crossing coverage"):
        refine_rigid_registration(
            np.zeros((32, 32, 32), dtype=np.float32), points, normals,
            minimum_end_contrast=1.0,
            maximum_iterations=1,
        )


def test_healthy_cylinder_is_measured_at_native_subvoxel_radius():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(), *endpoints, 4.0, minimum_local_contrast=400.0
    )
    assert result["measurement_valid"] is True
    assert result["observed_axial_fraction"] > 0.95
    assert result["connected_support"] is True
    assert abs(result["median_signed_radial_deviation_voxels"]) < 0.20


def test_missing_axial_gap_is_not_hidden_by_radial_surface_quality():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(gap_fraction=(0.43, 0.57)), *endpoints, 4.0,
        minimum_local_contrast=400.0,
    )
    decision = classify_strut_measurement(result, registration_uncertainty_voxels=0.25)
    assert result["longest_unsupported_gap_voxels"] > 3.0
    assert decision["has_error"] is True
    assert "unsupported_gap" in decision["failed_checks"]


def test_thin_but_continuous_cylinder_exceeds_radial_tolerance():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(radius=2.5), *endpoints, 4.0,
        minimum_local_contrast=400.0, minimum_area_fraction=0.20,
    )
    decision = classify_strut_measurement(result, registration_uncertainty_voxels=0.25)
    assert result["observed_axial_fraction"] > 0.90
    assert result["median_signed_radial_deviation_voxels"] < -1.0
    assert decision["has_error"] is True
    assert "radial_deviation" in decision["failed_checks"]


def test_visible_material_is_present_when_radius_quality_is_insufficient():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(radius=2.0), *endpoints, 4.0,
        minimum_local_contrast=300.0,
        minimum_area_fraction=0.80,
    )
    assert result["observed_axial_fraction"] > 0.95
    assert result["connected_support"] is True
    assert result["longest_unsupported_gap_voxels"] == 0.0
    assert "present_radial_area_uncertain" in result["station_reason"]


def test_shifted_cylinder_reports_centerline_displacement():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(center_shift=(0.0, 1.6, -0.8)), *endpoints, 4.0,
        minimum_local_contrast=300.0,
    )
    decision = classify_strut_measurement(result, registration_uncertainty_voxels=0.25)
    assert result["p90_centerline_displacement_voxels"] > 1.0
    assert decision["has_error"] is None
    assert decision["review_required"] is True
    assert "centerline_displacement" in decision["failed_checks"]


def test_shifted_target_is_not_erased_by_bright_neighboring_members():
    """A dense lattice must not treat nearby struts as local background."""

    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    volume = _soft_cylinder(center_shift=(0.0, 0.3, -0.2))
    z, y, _x = np.indices(volume.shape, dtype=np.float32)
    radial_from_cad = np.sqrt((y - 26.0) ** 2 + (z - 26.0) ** 2)
    # A separated bright shell is a worst-case surrogate for several nearby
    # members collectively occupying most of the legacy background annulus.
    shell = np.where(
        (radial_from_cad >= 5.2) & (radial_from_cad <= 7.0), 1500.0, 100.0
    )
    volume = np.maximum(volume, shell.astype(np.float32))
    result = measure_strut_cross_sections(
        volume, *endpoints, 4.0,
        minimum_local_contrast=400.0,
        minimum_valid_ray_fraction=0.25,
    )
    assert result["measurement_valid"] is True
    assert result["observed_axial_fraction"] > 0.90
    assert result["connected_support"] is True
    assert result["longest_unsupported_gap_voxels"] <= 1.5


def test_absent_target_does_not_borrow_a_parallel_neighbor_as_support():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    neighbor_only = _soft_cylinder(radius=3.0, center_shift=(0.0, 7.5, 0.0))
    result = measure_strut_cross_sections(
        neighbor_only, *endpoints, 4.0,
        minimum_local_contrast=300.0,
        minimum_valid_ray_fraction=0.25,
    )
    assert result["measurement_valid"] is False
    assert result["observed_axial_fraction"] == 0.0
    assert result["connected_support"] is False


def test_low_contrast_member_becomes_review_not_healthy():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(contrast=200.0), *endpoints, 4.0,
        minimum_local_contrast=500.0,
    )
    decision = classify_strut_measurement(result, registration_uncertainty_voxels=0.25)
    assert result["measurement_valid"] is False
    assert decision["has_error"] is None
    assert decision["review_required"] is True


def test_out_of_bounds_cross_sections_are_not_clipped_into_false_errors():
    endpoints = ((8.0, 2.0, 26.0), (40.0, 2.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(endpoint0=endpoints[0], endpoint1=endpoints[1]),
        *endpoints, 4.0, minimum_local_contrast=300.0,
    )
    assert "cross_section_out_of_bounds" in result["station_reason"]


def test_diagonal_member_uses_an_orthonormal_cross_section_frame():
    endpoints = ((10.0, 10.0, 10.0), (40.0, 40.0, 40.0))
    volume = _soft_cylinder(
        shape=(52, 52, 52), endpoint0=endpoints[0], endpoint1=endpoints[1], radius=3.5
    )
    result = measure_strut_cross_sections(
        volume, *endpoints, 3.5, minimum_local_contrast=300.0
    )
    assert result["measurement_valid"] is True
    assert result["observed_axial_fraction"] > 0.85


def test_expected_radius_vector_is_interpolated_to_axial_stations():
    endpoints = ((8.0, 26.0, 26.0), (43.0, 26.0, 26.0))
    result = measure_strut_cross_sections(
        _soft_cylinder(), *endpoints, [3.8, 4.0, 4.2], minimum_local_contrast=300.0
    )
    profile = result["station_expected_radius_voxels"]
    assert profile[0] == pytest.approx(3.8)
    assert profile[-1] == pytest.approx(4.2)


def test_clear_measurement_is_called_healthy_only_inside_margin():
    decision = classify_strut_measurement(
        _valid_measurement(), registration_uncertainty_voxels=0.25
    )
    assert decision["has_error"] is False
    assert decision["review_required"] is False


def test_near_tolerance_measurement_is_review_not_forced_healthy():
    decision = classify_strut_measurement(
        _valid_measurement(p90_absolute_radial_deviation_voxels=0.90),
        registration_uncertainty_voxels=0.25,
    )
    assert decision["has_error"] is None
    assert decision["review_required"] is True


def test_endpoint_connectivity_alone_requires_review_not_confirmed_error():
    decision = classify_strut_measurement(
        _valid_measurement(connected_support=False),
        registration_uncertainty_voxels=0.25,
    )
    assert decision["has_error"] is None
    assert decision["review_required"] is True
    assert decision["failed_checks"] == ["continuous_support"]


def test_registration_uncertainty_expands_location_tolerance_explicitly():
    measurement = _valid_measurement(p90_centerline_displacement_voxels=1.20)
    strict = classify_strut_measurement(measurement, registration_uncertainty_voxels=0.10)
    conservative = classify_strut_measurement(
        measurement, registration_uncertainty_voxels=0.60
    )
    assert strict["has_error"] is None
    assert strict["review_required"] is True
    assert "centerline_displacement" in strict["failed_checks"]
    assert conservative["has_error"] is None


def test_invalid_radius_profile_is_rejected_before_sampling():
    with pytest.raises(ValueError, match="radius"):
        measure_strut_cross_sections(
            _soft_cylinder(), (8, 26, 26), (43, 26, 26), [4.0, np.nan]
        )


def test_zero_length_strut_is_rejected():
    with pytest.raises(ValueError, match="distinct"):
        measure_strut_cross_sections(
            _soft_cylinder(), (8, 26, 26), (8, 26, 26), 4.0
        )


def test_cli_defaults_to_specimen_cad_and_full_run():
    arguments = cli.parse_args([])
    assert arguments.stl.endswith("/stls/0.5.stl")
    assert arguments.complete_stl.endswith("/stls/0.stl")
    assert arguments.registration_only is False
    assert arguments.limit_struts is None


def test_cli_rejects_zero_diagnostic_struts():
    with pytest.raises(SystemExit):
        cli.parse_args(["--limit-struts", "0"])


def test_evenly_spaced_diagnostic_ids_include_both_extremes():
    selected = cli._evenly_spaced_ids(np.arange(100, 200), 10)
    assert len(selected) == 10
    assert selected[0] == 100
    assert selected[-1] == 199
    assert len(np.unique(selected)) == 10


def test_radius_profile_interpolates_sparse_missing_stations():
    distances = np.asarray([4.0, np.inf, 4.2, np.inf, 4.4, 4.5, 4.6])
    profile = cli._radius_profile(distances)
    assert profile is not None
    assert np.isfinite(profile).all()
    assert profile[1] == pytest.approx(4.1)


def test_radius_profile_rejects_mostly_invalid_stl_evidence():
    assert cli._radius_profile(np.asarray([np.inf] * 8 + [4.0, 4.1])) is None


def test_corrected_atlas_moves_endpoints_centers_and_preserves_ids():
    atlas = {
        "strut_ids": np.asarray([7]),
        "endpoint0_xyz": np.asarray([[1.0, 2.0, 3.0]]),
        "endpoint1_xyz": np.asarray([[4.0, 2.0, 3.0]]),
        "centers_xyz": np.asarray([[[2.0, 2.0, 3.0], [3.0, 2.0, 3.0]]]),
        "length_voxels": np.asarray([3.0]),
    }
    correction = np.eye(4)
    correction[:3, 3] = (0.5, -1.0, 2.0)
    corrected = cli._correct_atlas(atlas, correction)
    assert corrected["strut_ids"] is atlas["strut_ids"]
    assert corrected["endpoint0_xyz"][0] == pytest.approx((1.5, 1.0, 5.0))
    assert corrected["centers_xyz"][0, 1] == pytest.approx((3.5, 1.0, 5.0))
    assert corrected["length_voxels"][0] == pytest.approx(3.0)


def test_cad_absence_is_nonapplicable_not_an_error():
    evidence = cli._not_applicable(cad_absent=True, skin_embedded=False)
    assert evidence["stl_expected_present"] is False
    assert evidence["comparison_applicable"] is False
    assert evidence["has_error"] is None
    assert evidence["review_required"] is False


def test_panel_ranking_places_errors_before_review_before_healthy():
    results = {
        3: {"comparison_applicable": True, "has_error": False},
        2: {"comparison_applicable": True, "has_error": None},
        1: {"comparison_applicable": True, "has_error": True},
        0: {"comparison_applicable": False, "has_error": None},
    }
    assert cli._panel_ids(results, 3) == [1, 2, 3]


def test_panel_renderer_writes_real_ct_evidence_png(tmp_path):
    volume = _soft_cylinder()
    evidence = measure_strut_cross_sections(
        volume, (8, 26, 26), (43, 26, 26), 4.0, minimum_local_contrast=300.0
    )
    evidence.update(classify_strut_measurement(
        evidence, registration_uncertainty_voxels=0.25
    ))
    destination = tmp_path / "panel.png"
    cli._render_panel(volume, 42, evidence, destination)
    assert destination.is_file()
    assert destination.stat().st_size > 20_000
