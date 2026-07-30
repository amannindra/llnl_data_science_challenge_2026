"""Focused tests for the solid-skin observability gate.

These tests distinguish a strut that lies wholly inside either CAD skin from
one that merely touches a skin at one endpoint.  The former cannot be judged
independently from CT material and must therefore be excluded from ordinary
per-strut defect classification.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from Aman_Scripts.Components.cad_strut_mapping import (
    CADStrutMappingError,
    identify_skin_embedded_struts,
)
from Aman_Scripts.Components.lattice_graph import (
    LatticeGraph,
    load_lattice_graph,
    parse_lattice_graph,
)


ROOT = Path(__file__).resolve().parents[2]
DESIGN_JSON = ROOT / "data" / "missing_struts" / "octet_truss_9x9x9.json"


def _synthetic_skin_graph() -> LatticeGraph:
    """Return lower, upper, crossing, and interior struts with stable IDs."""

    return parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [1.0, 0.0, 0.0]},
            {"id": 2, "position": [0.0, 0.0, 5.0]},
            {"id": 3, "position": [1.0, 0.0, 5.0]},
            {"id": 4, "position": [0.0, 0.0, 10.0]},
            {"id": 5, "position": [1.0, 0.0, 10.0]},
        ],
        "struts": [
            {"id": 90, "junction0": 0, "junction1": 1},
            {"id": 70, "junction0": 4, "junction1": 5},
            {"id": 50, "junction0": 0, "junction1": 2},
            {"id": 30, "junction0": 3, "junction1": 5},
            {"id": 10, "junction0": 2, "junction1": 3},
        ],
    })


def test_lower_plane_strut_is_skin_embedded() -> None:
    result = identify_skin_embedded_struts(_synthetic_skin_graph())
    assert 90 in result


def test_upper_plane_strut_is_skin_embedded() -> None:
    result = identify_skin_embedded_struts(_synthetic_skin_graph())
    assert 70 in result


def test_one_lower_boundary_endpoint_is_not_skin_embedded() -> None:
    result = identify_skin_embedded_struts(_synthetic_skin_graph())
    assert 50 not in result


def test_one_upper_boundary_endpoint_is_not_skin_embedded() -> None:
    result = identify_skin_embedded_struts(_synthetic_skin_graph())
    assert 30 not in result


def test_interior_coplanar_strut_is_not_mistaken_for_a_skin() -> None:
    result = identify_skin_embedded_struts(_synthetic_skin_graph())
    assert 10 not in result


def test_skin_axis_can_be_selected_explicitly() -> None:
    graph = parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [0.0, 1.0, 1.0]},
            {"id": 2, "position": [5.0, 0.0, 0.0]},
            {"id": 3, "position": [5.0, 1.0, 1.0]},
        ],
        "struts": [
            {"id": 8, "junction0": 0, "junction1": 1},
            {"id": 9, "junction0": 2, "junction1": 3},
        ],
    })
    np.testing.assert_array_equal(
        identify_skin_embedded_struts(graph, skin_normal_axis=0),
        [8, 9],
    )


def test_tolerance_accepts_small_coordinate_noise_at_skin_plane() -> None:
    graph = parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [1.0, 0.0, 0.0]},
            {"id": 2, "position": [0.0, 1.0, 5e-7]},
            {"id": 3, "position": [1.0, 1.0, 5e-7]},
            {"id": 4, "position": [0.0, 0.0, 10.0]},
        ],
        "struts": [{"id": 44, "junction0": 2, "junction1": 3}],
    })
    np.testing.assert_array_equal(
        identify_skin_embedded_struts(graph, tolerance=1e-6),
        [44],
    )


def test_tolerance_rejects_coordinate_noise_beyond_limit() -> None:
    graph = parse_lattice_graph({
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [1.0, 0.0, 0.0]},
            {"id": 2, "position": [0.0, 1.0, 2e-6]},
            {"id": 3, "position": [1.0, 1.0, 2e-6]},
            {"id": 4, "position": [0.0, 0.0, 10.0]},
        ],
        "struts": [{"id": 44, "junction0": 2, "junction1": 3}],
    })
    assert identify_skin_embedded_struts(graph, tolerance=1e-6).size == 0


@pytest.mark.parametrize("axis", [-1, 3, "2", None])
def test_invalid_skin_axis_is_rejected(axis) -> None:
    with pytest.raises(CADStrutMappingError, match="skin_normal_axis"):
        identify_skin_embedded_struts(_synthetic_skin_graph(), skin_normal_axis=axis)


@pytest.mark.parametrize("tolerance", [-1.0, np.nan, np.inf, -np.inf])
def test_invalid_tolerance_is_rejected(tolerance: float) -> None:
    with pytest.raises(CADStrutMappingError, match="tolerance"):
        identify_skin_embedded_struts(
            _synthetic_skin_graph(),
            tolerance=tolerance,
        )


def test_empty_graph_is_rejected() -> None:
    graph = parse_lattice_graph({"junctions": [], "struts": []})
    with pytest.raises(CADStrutMappingError, match="no junction coordinates"):
        identify_skin_embedded_struts(graph)


def test_missing_strut_endpoint_is_rejected() -> None:
    graph = parse_lattice_graph(
        {
            "junctions": [
                {"id": 0, "position": [0.0, 0.0, 0.0]},
                {"id": 1, "position": [0.0, 0.0, 10.0]},
            ],
            "struts": [{"id": 7, "junction0": 0, "junction1": 99}],
        },
        strict_references=False,
    )
    with pytest.raises(CADStrutMappingError, match="missing junction 99"):
        identify_skin_embedded_struts(graph)


def test_ids_are_sorted_unique_and_deterministic_for_unsorted_input() -> None:
    graph = _synthetic_skin_graph()
    reversed_graph = LatticeGraph(
        junctions=graph.junctions,
        struts=tuple(reversed(graph.struts)),
        unit_cells=graph.unit_cells,
        metadata=graph.metadata,
    )
    first = identify_skin_embedded_struts(reversed_graph)
    second = identify_skin_embedded_struts(reversed_graph)
    np.testing.assert_array_equal(first, [70, 90])
    np.testing.assert_array_equal(second, first)
    assert first.dtype == np.dtype(np.int64)
    assert len(first) == len(np.unique(first))


@pytest.fixture(scope="module")
def real_design_graph() -> LatticeGraph:
    return load_lattice_graph(DESIGN_JSON)


def test_real_design_has_expected_lower_and_upper_skin_counts(
    real_design_graph: LatticeGraph,
) -> None:
    skin_ids = identify_skin_embedded_struts(real_design_graph)
    junctions = real_design_graph.junction_by_id()
    struts = real_design_graph.strut_by_id()
    lower = 0
    upper = 0
    for strut_id in skin_ids:
        edge = struts[int(strut_id)]
        endpoint_z = (
            junctions[edge.junction0].position[2],
            junctions[edge.junction1].position[2],
        )
        lower += endpoint_z == (0.0, 0.0)
        upper += endpoint_z == (18.0, 18.0)
    assert lower == 324
    assert upper == 324
    assert skin_ids.size == 648


def test_real_known_cad_omissions_are_unobservable_inside_lower_skin(
    real_design_graph: LatticeGraph,
) -> None:
    """Known omitted CAD IDs cannot be classified independently from CT.

    IDs 170, 1223, and 1465 were discovered by the complete-vs-0.5% STL
    mapping.  Their design endpoints all lie on Z=0, so the skin gate must
    retain the IDs for provenance while excluding them from defect scoring.
    """

    skin_ids = set(identify_skin_embedded_struts(real_design_graph).tolist())
    assert {170, 1223, 1465} <= skin_ids

    junctions = real_design_graph.junction_by_id()
    struts = real_design_graph.strut_by_id()
    for strut_id in (170, 1223, 1465):
        edge = struts[strut_id]
        assert junctions[edge.junction0].position[2] == 0.0
        assert junctions[edge.junction1].position[2] == 0.0

