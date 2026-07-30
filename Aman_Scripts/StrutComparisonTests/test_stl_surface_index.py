"""Exact-query and safety tests for the non-voxelized STL surface index."""

from __future__ import annotations

import numpy as np
import pytest

from Aman_Scripts.Components.stl_surface_index import STLSurfaceIndex

from _synthetic import write_binary_stl


def fixture_triangles() -> np.ndarray:
    """Three near cross-sections and one deliberately distant triangle."""

    return np.asarray([
        [[0.5, -1.0, -1.0], [0.5, 1.0, -1.0], [0.5, 0.0, 1.0]],
        [[5.5, -1.0, -1.0], [5.5, 1.0, -1.0], [5.5, 0.0, 1.0]],
        [[9.5, -1.0, -1.0], [9.5, 1.0, -1.0], [9.5, 0.0, 1.0]],
        [[100.0, 100.0, 100.0], [101.0, 100.0, 100.0], [100.0, 101.0, 100.0]],
    ], dtype=np.float64)


@pytest.fixture()
def surface_index(tmp_path) -> STLSurfaceIndex:
    path = write_binary_stl(tmp_path / "fixture.stl", fixture_triangles())
    return STLSurfaceIndex.from_stl(path, base_radius=0.25, chunk_faces=2)


def test_index_retains_every_original_triangle(surface_index: STLSurfaceIndex) -> None:
    assert surface_index.triangle_count == 4
    np.testing.assert_allclose(surface_index.triangles_xyz, fixture_triangles())


def test_indexed_triangles_are_read_only(surface_index: STLSurfaceIndex) -> None:
    assert not surface_index.triangles_xyz.flags.writeable
    with pytest.raises(ValueError):
        surface_index.triangles_xyz[0, 0, 0] = 999.0


def test_affine_transform_is_applied_to_all_vertices(tmp_path) -> None:
    path = write_binary_stl(tmp_path / "translated.stl", fixture_triangles())
    transform = np.eye(4)
    transform[:3, 3] = (10.0, 20.0, 30.0)
    index = STLSurfaceIndex.from_stl(path, transform=transform)
    np.testing.assert_allclose(
        index.triangles_xyz,
        fixture_triangles() + np.array([10.0, 20.0, 30.0]),
    )
    assert index.bounds_min_xyz == pytest.approx((10.5, 19.0, 29.0))


def test_query_returns_exact_nearby_original_triangles(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), radius=0.05, axial_step=1.0
    )
    np.testing.assert_array_equal(result.unique_triangle_indices, [0, 1, 2])
    assert result.axial_bin_count == 10
    assert result.matched_triangle_count == 3


def test_query_uses_exact_surface_distance_not_centroid_only(tmp_path) -> None:
    # This triangle contains (1, 1, 0), but its centroid is around (33, 33, 0).
    huge = np.asarray([[[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0]]])
    path = write_binary_stl(tmp_path / "large_plate.stl", huge)
    index = STLSurfaceIndex.from_stl(path, base_radius=0.25)
    result = index.query_segment(
        (1.0, 1.0, 0.5), (2.0, 1.0, 0.5), radius=0.51, axial_step=0.5
    )
    assert result.matched_triangle_count == 1
    assert np.allclose(result.nearest_surface_distances, 0.5)


def test_far_triangle_is_filtered_out_by_exact_distance(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), radius=0.1
    )
    assert 3 not in result.unique_triangle_indices


def test_no_hit_query_has_explicit_empty_and_infinite_evidence(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 50.0, 50.0), (10.0, 50.0, 50.0), radius=0.1
    )
    assert result.triangle_indices.size == 0
    assert result.surface_points_xyz.shape == (0, 3)
    assert np.isinf(result.nearest_surface_distances).all()
    assert np.isnan(result.nearest_surface_points_xyz).all()


def test_csr_offsets_and_bin_slices_are_consistent(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), radius=0.05
    )
    assert result.bin_offsets.shape == (result.axial_bin_count + 1,)
    assert result.bin_offsets[0] == 0
    assert result.bin_offsets[-1] == len(result.triangle_indices)
    for bin_index in range(result.axial_bin_count):
        section = result.bin_slice(bin_index)
        assert section.stop - section.start == result.bin_counts[bin_index]


def test_endpoint_exclusion_changes_centers_not_source_geometry(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
        radius=0.05,
        endpoint_exclusion_fraction=0.20,
    )
    assert np.all(result.axial_fractions > 0.20)
    assert np.all(result.axial_fractions < 0.80)
    assert surface_index.triangle_count == 4


def test_triangles_for_preserves_requested_order_and_is_read_only(surface_index: STLSurfaceIndex) -> None:
    selected = surface_index.triangles_for(np.array([2, 0], dtype=np.int64))
    np.testing.assert_allclose(selected, fixture_triangles()[[2, 0]])
    assert not selected.flags.writeable


def test_index_and_query_are_deterministic(surface_index: STLSurfaceIndex) -> None:
    arguments = ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    first = surface_index.query_segment(*arguments, radius=0.05)
    second = surface_index.query_segment(*arguments, radius=0.05)
    for name in (
        "axial_fractions", "bin_centers_xyz", "bin_counts", "bin_offsets",
        "triangle_indices", "surface_distances", "surface_points_xyz",
        "nearest_surface_distances", "nearest_surface_points_xyz",
    ):
        np.testing.assert_equal(getattr(first, name), getattr(second, name))


def test_all_query_result_arrays_are_read_only(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), radius=0.05
    )
    arrays = [
        result.axial_fractions, result.bin_centers_xyz, result.bin_counts,
        result.bin_offsets, result.triangle_indices, result.surface_distances,
        result.surface_points_xyz, result.nearest_surface_distances,
        result.nearest_surface_points_xyz, result.unique_triangle_indices,
    ]
    assert all(not value.flags.writeable for value in arrays)


def test_triangle_count_budget_fails_before_indexing(tmp_path) -> None:
    path = write_binary_stl(tmp_path / "budget.stl", fixture_triangles())
    with pytest.raises(ValueError, match="max_triangles"):
        STLSurfaceIndex.from_stl(path, max_triangles=3)


def test_memory_budget_fails_before_indexing(tmp_path) -> None:
    path = write_binary_stl(tmp_path / "memory.stl", fixture_triangles())
    with pytest.raises(ValueError, match="max_index_bytes"):
        STLSurfaceIndex.from_stl(path, max_index_bytes=1)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"radius": 0.0}, "radius"),
        ({"radius": 1.0, "axial_step": 0.0}, "axial_step"),
        ({"radius": 1.0, "endpoint_exclusion_fraction": 0.5}, "endpoint_exclusion"),
        ({"radius": 1.0, "max_axial_bins": 1}, "max_axial_bins"),
        ({"radius": 1.0, "workers": 0}, "workers"),
    ],
)
def test_invalid_query_controls_are_rejected(
    surface_index: STLSurfaceIndex, kwargs: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        surface_index.query_segment((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), **kwargs)


def test_zero_length_segment_is_rejected(surface_index: STLSurfaceIndex) -> None:
    with pytest.raises(ValueError, match="nonzero"):
        surface_index.query_segment((1.0, 2.0, 3.0), (1.0, 2.0, 3.0), radius=1.0)


@pytest.mark.parametrize("bad_index", [-1, 10, True])
def test_invalid_bin_slice_is_rejected(surface_index: STLSurfaceIndex, bad_index) -> None:
    result = surface_index.query_segment(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), radius=0.05
    )
    with pytest.raises((IndexError, TypeError)):
        result.bin_slice(bad_index)


def test_noninteger_triangle_selection_is_rejected(surface_index: STLSurfaceIndex) -> None:
    with pytest.raises(ValueError):
        surface_index.triangles_for(np.array([0.0]))


def test_out_of_range_triangle_selection_is_rejected(surface_index: STLSurfaceIndex) -> None:
    with pytest.raises(IndexError):
        surface_index.triangles_for(np.array([4]))


def test_nearest_query_chooses_exact_surface_over_closer_centroid(tmp_path) -> None:
    # The huge face is only 0.5 voxel from the query but its centroid is far
    # away.  The compact distractor has a nearer centroid but a farther surface.
    triangles = np.asarray([
        [[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0]],
        [[0.5, 0.5, 2.0], [1.5, 0.5, 2.0], [1.0, 1.5, 2.0]],
    ])
    path = write_binary_stl(tmp_path / "nearest_exact.stl", triangles)
    index = STLSurfaceIndex.from_stl(path, base_radius=0.25)
    result = index.query_segment_nearest(
        (1.0, 1.0, 0.5),
        (2.0, 1.0, 0.5),
        axial_step=0.5,
        endpoint_exclusion_fraction=0.0,
        candidates_per_bucket=1,
    )
    np.testing.assert_array_equal(result.triangle_indices, 0)
    np.testing.assert_allclose(result.nearest_surface_distances, 0.5)
    np.testing.assert_allclose(result.nearest_surface_points_xyz[:, 2], 0.0)


def test_nearest_query_respects_transform_and_endpoint_exclusion(tmp_path) -> None:
    path = write_binary_stl(tmp_path / "nearest_transform.stl", fixture_triangles())
    transform = np.eye(4)
    transform[:3, 3] = (10.0, 20.0, 30.0)
    index = STLSurfaceIndex.from_stl(path, transform=transform, base_radius=0.25)
    result = index.query_segment_nearest(
        (10.0, 20.0, 30.0),
        (20.0, 20.0, 30.0),
        axial_step=1.0,
        endpoint_exclusion_fraction=0.20,
    )
    assert np.all(result.axial_fractions > 0.20)
    assert np.all(result.axial_fractions < 0.80)
    assert result.start_xyz == (10.0, 20.0, 30.0)
    assert result.end_xyz == (20.0, 20.0, 30.0)
    assert np.all(result.nearest_surface_points_xyz[:, 1] == pytest.approx(20.0))


def test_nearest_query_candidate_limit_is_recorded(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment_nearest(
        (0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
        candidates_per_bucket=1,
        endpoint_exclusion_fraction=0.0,
    )
    assert result.candidates_per_bucket == 1
    assert result.axial_bin_count == 10
    assert np.all((0 <= result.triangle_indices) & (result.triangle_indices < 4))


def test_nearest_query_large_candidate_limit_clamps_safely(surface_index: STLSurfaceIndex) -> None:
    result = surface_index.query_segment_nearest(
        (0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
        candidates_per_bucket=10_000,
        endpoint_exclusion_fraction=0.0,
    )
    assert result.candidates_per_bucket == 10_000
    assert result.triangle_indices.shape == (10,)


def test_nearest_query_tie_uses_smallest_original_triangle_id(tmp_path) -> None:
    triangle = fixture_triangles()[0]
    path = write_binary_stl(tmp_path / "nearest_tie.stl", np.stack((triangle, triangle)))
    index = STLSurfaceIndex.from_stl(path)
    result = index.query_segment_nearest(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        endpoint_exclusion_fraction=0.0,
        candidates_per_bucket=2,
    )
    np.testing.assert_array_equal(result.triangle_indices, [0])


def test_nearest_query_is_deterministic_and_read_only(surface_index: STLSurfaceIndex) -> None:
    kwargs = {
        "axial_step": 0.75,
        "endpoint_exclusion_fraction": 0.1,
        "candidates_per_bucket": 2,
    }
    first = surface_index.query_segment_nearest(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), **kwargs
    )
    second = surface_index.query_segment_nearest(
        (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), **kwargs
    )
    for name in (
        "axial_fractions", "bin_centers_xyz", "nearest_surface_distances",
        "nearest_surface_points_xyz", "triangle_indices",
    ):
        first_array = getattr(first, name)
        assert not first_array.flags.writeable
        np.testing.assert_equal(first_array, getattr(second, name))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"axial_step": 0.0},
        {"axial_step": np.nan},
        {"endpoint_exclusion_fraction": -0.01},
        {"endpoint_exclusion_fraction": 0.5},
        {"candidates_per_bucket": 0},
        {"candidates_per_bucket": 1.5},
        {"workers": 0},
    ],
)
def test_nearest_query_rejects_invalid_controls(
    surface_index: STLSurfaceIndex, kwargs: dict[str, float]
) -> None:
    with pytest.raises(ValueError):
        surface_index.query_segment_nearest(
            (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), **kwargs
        )


def test_nearest_query_rejects_zero_length_segment(surface_index: STLSurfaceIndex) -> None:
    with pytest.raises(ValueError, match="nonzero"):
        surface_index.query_segment_nearest((1.0, 2.0, 3.0), (1.0, 2.0, 3.0))


def test_nearest_query_rejects_unbounded_axial_allocation(surface_index: STLSurfaceIndex) -> None:
    with pytest.raises(ValueError, match="axial bins"):
        surface_index.query_segment_nearest(
            (0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0),
            axial_step=1e-6,
            endpoint_exclusion_fraction=0.0,
        )
