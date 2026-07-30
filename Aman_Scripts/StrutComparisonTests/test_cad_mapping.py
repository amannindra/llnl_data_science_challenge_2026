"""Synthetic tests for mapping monolithic CAD surface evidence to strut IDs."""

from __future__ import annotations

import numpy as np
import pytest

from Aman_Scripts.Components.cad_strut_mapping import (
    CADStrutMappingError,
    build_registered_centerline_atlas,
    infer_specimen_cad_omissions,
    sample_stl_surface_against_atlas,
)
from Aman_Scripts.Components.lattice_graph import parse_lattice_graph

from _synthetic import write_binary_stl


def simple_graph():
    return parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [10.0, 0.0, 0.0]},
            {"id": 2, "position": [10.0, 10.0, 0.0]},
        ],
        "struts": [
            {"id": 4, "junction0": 0, "junction1": 1, "thickness": 0.1},
            {"id": 9, "junction0": 1, "junction1": 2, "thickness": 0.1},
        ],
    })


def test_atlas_preserves_stable_strut_ids_and_endpoint_coordinates() -> None:
    atlas = build_registered_centerline_atlas(simple_graph(), axial_bins=5)
    np.testing.assert_array_equal(atlas["strut_ids"], [4, 9])
    np.testing.assert_allclose(atlas["endpoint0_xyz"], [[0, 0, 0], [10, 0, 0]])
    np.testing.assert_allclose(atlas["endpoint1_xyz"], [[10, 0, 0], [10, 10, 0]])


def test_atlas_centers_apply_endpoint_exclusion_in_xyz() -> None:
    atlas = build_registered_centerline_atlas(
        simple_graph(), axial_bins=4, endpoint_exclusion_fraction=0.10
    )
    assert atlas["centers_xyz"].shape == (2, 4, 3)
    np.testing.assert_allclose(atlas["axial_fractions"], [0.2, 0.4, 0.6, 0.8])
    np.testing.assert_allclose(atlas["centers_xyz"][0, :, 0], [2, 4, 6, 8])


def test_atlas_lengths_remain_in_native_voxels() -> None:
    atlas = build_registered_centerline_atlas(simple_graph(), axial_bins=5)
    np.testing.assert_allclose(atlas["length_voxels"], [10.0, 10.0])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"axial_bins": 2},
        {"endpoint_exclusion_fraction": -0.01},
        {"endpoint_exclusion_fraction": 0.5},
    ],
)
def test_atlas_rejects_invalid_sampling_controls(kwargs) -> None:
    with pytest.raises(CADStrutMappingError):
        build_registered_centerline_atlas(simple_graph(), **kwargs)


def test_atlas_rejects_zero_length_strut() -> None:
    graph = parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [1, 1, 1]},
            {"id": 1, "position": [1, 1, 1]},
        ],
        "struts": [{"id": 0, "junction0": 0, "junction1": 1}],
    })
    with pytest.raises(CADStrutMappingError, match="zero"):
        build_registered_centerline_atlas(graph)


def coverage_fixture(count: int = 100, bins: int = 20, radii: int = 3):
    complete = np.ones((count, bins, radii), dtype=bool)
    specimen = complete.copy()
    specimen[-3:] = False
    ids = np.arange(1000, 1000 + count)
    return {"coverage": complete}, {"coverage": specimen}, ids


def test_omission_mapping_finds_clear_cluster_without_forced_count() -> None:
    complete, specimen, ids = coverage_fixture()
    result = infer_specimen_cad_omissions(complete, specimen, ids)
    assert result["removed_count"] == 3
    np.testing.assert_array_equal(result["removed_strut_ids"], ids[-3:])
    assert result["cluster_gap"] == pytest.approx(1.0)
    assert result["split_threshold"] == pytest.approx(0.5)


def test_omission_mapping_is_deterministic() -> None:
    arguments = coverage_fixture()
    first = infer_specimen_cad_omissions(*arguments)
    second = infer_specimen_cad_omissions(*arguments)
    for key in (
        "median_coverage_drop", "removed_mask", "removed_strut_ids",
        "radius_agreement",
    ):
        np.testing.assert_equal(first[key], second[key])


def test_omission_mapping_rejects_no_separated_cluster() -> None:
    complete, _, ids = coverage_fixture()
    with pytest.raises(CADStrutMappingError, match="no admissible"):
        infer_specimen_cad_omissions(complete, complete, ids)


def test_omission_mapping_rejects_weak_cluster_gap() -> None:
    count, bins, radii = 100, 20, 3
    complete = np.ones((count, bins, radii), dtype=bool)
    specimen = complete.copy()
    specimen[:-3, :4, :] = False  # ordinary drop = 0.20
    specimen[-3:, :5, :] = False  # candidate drop = 0.25; gap only 0.05
    with pytest.raises(CADStrutMappingError, match="cluster gap"):
        infer_specimen_cad_omissions(
            {"coverage": complete}, {"coverage": specimen}, np.arange(count)
        )


def test_omission_mapping_rejects_radius_instability() -> None:
    count, bins, radii = 100, 20, 4
    complete = np.ones((count, bins, radii), dtype=bool)
    specimen = complete.copy()
    # Three candidate rows have drops [0, 0, 0.9, 1.0].  Their median score
    # forms a cluster, but only half the radius decisions support removal.
    specimen[-3:, :18, 2] = False
    specimen[-3:, :, 3] = False
    with pytest.raises(CADStrutMappingError, match="unstable across radii"):
        infer_specimen_cad_omissions(
            {"coverage": complete}, {"coverage": specimen}, np.arange(count)
        )


def test_omission_mapping_rejects_shape_and_id_mismatches() -> None:
    complete, specimen, ids = coverage_fixture()
    with pytest.raises(CADStrutMappingError, match="coverage shapes differ"):
        infer_specimen_cad_omissions(
            complete, {"coverage": specimen["coverage"][:-1]}, ids
        )
    with pytest.raises(CADStrutMappingError, match="strut_ids length"):
        infer_specimen_cad_omissions(complete, specimen, ids[:-1])


def test_surface_sampling_uses_every_triangle_and_retains_nearest_points(tmp_path) -> None:
    graph = parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0, 0, 0]},
            {"id": 1, "position": [10, 0, 0]},
        ],
        "struts": [{"id": 5, "junction0": 0, "junction1": 1}],
    })
    atlas = build_registered_centerline_atlas(
        graph, axial_bins=5, endpoint_exclusion_fraction=0.0
    )
    triangles = np.asarray([
        [[x, -0.2, -0.2], [x, 0.2, -0.2], [x, 0.0, 0.4]]
        for x in (1.0, 3.0, 5.0, 7.0, 9.0)
    ])
    path = write_binary_stl(tmp_path / "atlas_surface.stl", triangles)
    result = sample_stl_surface_against_atlas(
        path,
        np.eye(4),
        atlas,
        association_radii_voxels=(0.1, 0.5, 1.0),
        chunk_faces=2,
        retain_nearest_points=True,
    )
    assert result["triangle_count"] == 5
    assert result["surface_sample_count"] == 20
    assert result["coverage"].shape == (1, 5, 3)
    assert result["coverage"].all()
    np.testing.assert_allclose(result["nearest_surface_distance"], 0.0, atol=1e-7)
    np.testing.assert_allclose(
        result["nearest_surface_point_xyz"][0],
        atlas["centers_xyz"][0],
        atol=1e-7,
    )


@pytest.mark.parametrize(
    "radii",
    [(), (0.0,), (1.0, 1.0), (2.0, 1.0), (np.nan,)],
)
def test_surface_sampling_rejects_invalid_association_radii(tmp_path, radii) -> None:
    path = write_binary_stl(
        tmp_path / "invalid_radius.stl",
        np.asarray([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]]),
    )
    atlas = build_registered_centerline_atlas(simple_graph(), axial_bins=3)
    with pytest.raises(CADStrutMappingError):
        sample_stl_surface_against_atlas(
            path, np.eye(4), atlas, association_radii_voxels=radii
        )
