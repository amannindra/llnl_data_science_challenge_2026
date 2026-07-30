"""Read-only gates for real graph, registration, and native TIFF conventions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

from Aman_Scripts.Components.coordinates import xyz_to_zyx, zyx_to_xyz
from Aman_Scripts.Components.lattice_graph import (
    load_lattice_graph,
    summarize_components,
    weld_coincident_nodes,
)
from Aman_Scripts.tif2stl.registration import (
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "missing_struts"
DESIGN_JSON = DATA / "octet_truss_9x9x9.json"
REGISTERED_JSON = (
    DATA / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)
TIFF = (
    DATA / "tif_stacks"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)


@pytest.fixture(scope="module")
def graphs():
    return load_lattice_graph(DESIGN_JSON), load_lattice_graph(REGISTERED_JSON)


def test_xyz_to_zyx_has_unambiguous_order() -> None:
    np.testing.assert_array_equal(xyz_to_zyx([7, 11, 13]), [13, 11, 7])


def test_xyz_zyx_conversion_round_trips() -> None:
    points = np.asarray([[7.25, 11.5, 13.75], [2.0, 3.0, 5.0]])
    np.testing.assert_allclose(zyx_to_xyz(xyz_to_zyx(points)), points)


def test_tiff_is_materialized_native_uint16_stack() -> None:
    assert TIFF.stat().st_size > 1_000_000_000
    with tifffile.TiffFile(TIFF) as handle:
        assert handle.series[0].shape == (761, 815, 837)
        assert handle.series[0].dtype == np.dtype(np.uint16)
        assert len(handle.pages) == 761


def test_tiff_supports_true_memory_mapping_without_downsampling() -> None:
    volume = tifffile.memmap(TIFF, mode="r")
    assert isinstance(volume, np.memmap)
    assert volume.shape == (761, 815, 837)
    assert np.issubdtype(volume.dtype, np.unsignedinteger)
    assert volume.strides[-1] == volume.dtype.itemsize


def test_design_and_registered_graph_have_identical_strut_ids(graphs) -> None:
    design, registered = graphs
    assert len(design.struts) == len(registered.struts) == 18_468
    assert [item.id for item in design.struts] == [item.id for item in registered.struts]


def test_every_source_strut_id_is_unique(graphs) -> None:
    _, registered = graphs
    identifiers = [item.id for item in registered.struts]
    assert len(identifiers) == len(set(identifiers)) == 18_468


def test_registered_source_strut_references_exist(graphs) -> None:
    _, registered = graphs
    junction_ids = {item.id for item in registered.junctions}
    assert all(
        edge.junction0 in junction_ids and edge.junction1 in junction_ids
        for edge in registered.struts
    )


def test_registered_endpoints_fit_inside_native_tiff_xyz_bounds(graphs) -> None:
    _, registered = graphs
    positions = np.asarray([item.position for item in registered.junctions])
    assert np.all(positions >= 0.0)
    assert np.all(positions < np.asarray((837, 815, 761), dtype=np.float64))


def test_duplicate_junction_occurrences_are_welded_before_topology(graphs) -> None:
    _, registered = graphs
    welded = weld_coincident_nodes(registered, tolerance=1e-6)
    assert len(registered.junctions) == 10_206
    assert len(welded.nodes) == 3_430
    assert len(welded.nodes) < len(registered.junctions)


def test_welded_real_graph_is_one_connected_component(graphs) -> None:
    _, registered = graphs
    welded = weld_coincident_nodes(registered, tolerance=1e-6)
    summary = summarize_components(welded)
    assert summary.component_count == 1
    assert summary.isolated_node_ids == ()


def test_welding_preserves_every_source_strut_id(graphs) -> None:
    _, registered = graphs
    welded = weld_coincident_nodes(registered, tolerance=1e-6)
    retained = sorted(
        source_id
        for edge in welded.struts
        for source_id in edge.source_strut_ids
    )
    assert retained == [edge.id for edge in registered.struts]


def test_registration_is_derived_from_all_paired_junctions(graphs) -> None:
    design, registered = graphs
    source, target = paired_junction_positions(design, registered)
    fit = similarity_transform(source, target)
    assert fit.point_count == 10_206
    assert fit.scale == pytest.approx(39.48880949493, rel=1e-8)
    assert fit.rotation_angle_degrees == pytest.approx(0.3351084961, rel=1e-7)
    assert fit.rms_error < 1e-10


def test_established_stl_axis_mapping_is_a_proper_rotation() -> None:
    rotations = dict(proper_cube_rotations())
    assert "+z+x+y" in rotations
    mapping = rotations["+z+x+y"]
    np.testing.assert_allclose(mapping @ mapping.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(mapping) == pytest.approx(1.0)


def test_registered_endpoint_lookup_is_deterministic(graphs) -> None:
    _, registered = graphs
    first = registered.strut_by_id()[0]
    junctions = registered.junction_by_id()
    endpoints_once = (junctions[first.junction0].position, junctions[first.junction1].position)
    endpoints_twice = (junctions[first.junction0].position, junctions[first.junction1].position)
    assert endpoints_once == endpoints_twice
    assert all(len(point) == 3 for point in endpoints_once)

