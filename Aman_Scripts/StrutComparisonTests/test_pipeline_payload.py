"""Deterministic schema tests for the visualization-compatible JSON writer."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from Aman_Scripts.Components.reporting import canonical_json_bytes
from Aman_Scripts.Components.strut_pipeline import (
    StrutPipelineError,
    build_augmented_lattice_payload,
)


def source_payload() -> dict[str, object]:
    return {
        "format": "registered-synthetic",
        "custom_top_level": {"preserve": [1, 2, 3]},
        "_comparison": {"stale": True},
        "junctions": [
            {"id": 10, "position": [1.49, 2.50, 3.51], "indices": [0, 0, 0], "tag": "a"},
            {"id": 20, "position": [9.50, 8.49, 7.50], "indices": [1, 0, 0], "tag": "b"},
            {"id": 30, "position": [12.0, 14.0, 16.0], "indices": [2, 0, 0], "tag": "c"},
        ],
        "struts": [
            {
                "id": 4, "junction0": 20, "junction1": 10,
                "unit_cell_edge_idx": 7, "thickness": 0.1, "source_note": "first",
            },
            {
                "id": 9, "junction0": 20, "junction1": 30,
                "unit_cell_edge_idx": 8, "thickness": 0.2, "source_note": "second",
            },
        ],
        "unit_cells": [
            {"id": 0, "struts": [4, 9], "indices": [0, 0, 0], "cell_note": "keep"}
        ],
    }


def result_map() -> dict[int, dict[str, object]]:
    return {
        4: {
            "comparison_applicable": True,
            "comparison_valid": True,
            "stl_expected_present": True,
            "has_error": True,
            "review_required": True,
            "confidence": np.float64(0.91),
            "decision_reason": "continuous_unrealized_gap",
        },
        9: {
            "comparison_applicable": True,
            "comparison_valid": False,
            "stl_expected_present": True,
            "has_error": None,
            "review_required": True,
            "confidence": np.float32(0.0),
            "decision_reason": "threshold_or_registration_unstable",
        },
    }


def build(
    source: dict[str, object] | None = None,
    results: dict[int, dict[str, object]] | None = None,
    *,
    require_all: bool = True,
):
    return build_augmented_lattice_payload(
        source or source_payload(),
        result_map() if results is None else results,
        {"schema_version": "test.v1", "coordinate_frame": {"geometry_order": "xyz"}},
        require_all_struts=require_all,
    )


def test_source_payload_is_not_mutated() -> None:
    source = source_payload()
    before = copy.deepcopy(source)
    build(source)
    assert source == before


def test_junction_and_unit_cell_arrays_are_preserved_exactly() -> None:
    source = source_payload()
    payload = build(source)
    assert payload["junctions"] == source["junctions"]
    assert payload["unit_cells"] == source["unit_cells"]
    assert payload["junctions"] is not source["junctions"]
    assert payload["unit_cells"] is not source["unit_cells"]


def test_source_strut_order_and_fields_are_preserved_while_augmented() -> None:
    source = source_payload()
    payload = build(source)
    assert [record["id"] for record in payload["struts"]] == [4, 9]
    for original, augmented in zip(source["struts"], payload["struts"]):
        for key, value in original.items():
            assert augmented[key] == value


def test_every_source_strut_receives_comparison_evidence() -> None:
    payload = build()
    assert len(payload["struts"]) == 2
    assert all("has_error" in item for item in payload["struts"])
    assert [item["has_error"] for item in payload["struts"]] == [True, None]


def test_endpoint_xyz_and_nearest_zyx_indices_are_exact() -> None:
    first = build()["struts"][0]
    assert first["endpoint0_xyz_voxel"] == [9.50, 8.49, 7.50]
    assert first["endpoint1_xyz_voxel"] == [1.49, 2.50, 3.51]
    assert first["endpoint0_nearest_zyx_index"] == [8, 8, 10]
    assert first["endpoint1_nearest_zyx_index"] == [4, 3, 1]


def test_edge_id_is_orientation_independent_and_zero_padded() -> None:
    assert build()["struts"][0]["edge_id"] == "E_N000010_N000020"


def test_nullable_error_summary_counts_are_correct() -> None:
    summary = build()["_comparison"]["summary"]
    assert summary == {
        "strut_count": 2,
        "processed_count": 2,
        "not_processed_count": 0,
        "error_candidate_count": 1,
        "healthy_count": 0,
        "undecided_count": 1,
        "not_applicable_count": 0,
        "stl_intentionally_absent_count": 0,
    }


def test_unknown_result_id_fails_loudly() -> None:
    results = result_map()
    results[404] = {"has_error": False}
    with pytest.raises(StrutPipelineError, match="unknown strut IDs"):
        build(results=results)


def test_missing_result_id_fails_when_complete_output_required() -> None:
    with pytest.raises(StrutPipelineError, match="omit"):
        build(results={4: result_map()[4]})


def test_partial_output_explicitly_marks_unprocessed_strut_nullable() -> None:
    payload = build(results={4: result_map()[4]}, require_all=False)
    missing = payload["struts"][1]
    assert missing["has_error"] is None
    assert missing["comparison_valid"] is False
    assert missing["review_required"] is True
    assert missing["decision_reason"] == "not_processed"


def test_missing_endpoint_junction_fails_loudly() -> None:
    source = source_payload()
    source["junctions"] = source["junctions"][:-1]
    with pytest.raises(StrutPipelineError, match="missing junction 30"):
        build(source)


def test_duplicate_source_strut_ids_fail_loudly() -> None:
    source = source_payload()
    source["struts"][1]["id"] = 4
    with pytest.raises(StrutPipelineError, match="not unique"):
        build(source, results={4: result_map()[4]})


@pytest.mark.parametrize(
    "source",
    [
        {"junctions": {}, "struts": []},
        {"junctions": [], "struts": {}},
        {"unit_cells": []},
    ],
)
def test_malformed_source_arrays_fail_loudly(source: dict[str, object]) -> None:
    with pytest.raises(StrutPipelineError):
        build_augmented_lattice_payload(source, {}, {})


def test_unknown_top_level_fields_survive_but_stale_comparison_is_replaced() -> None:
    payload = build()
    assert payload["custom_top_level"] == {"preserve": [1, 2, 3]}
    assert payload["format"] == "registered-synthetic"
    assert "stale" not in payload["_comparison"]


def test_numpy_evidence_is_converted_to_strict_json_scalars() -> None:
    payload = build()
    assert isinstance(payload["struts"][0]["confidence"], float)
    assert isinstance(payload["struts"][1]["confidence"], float)
    canonical_json_bytes(payload)  # also rejects NaN and unsupported values


def test_canonical_json_bytes_are_deterministic_across_mapping_order() -> None:
    forward = result_map()
    reversed_results = dict(reversed(list(forward.items())))
    first = build(results=forward)
    second = build(results=reversed_results)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_evidence_cannot_override_source_identity_or_endpoint_fields() -> None:
    results = result_map()
    results[4] = {
        **results[4],
        "id": 999,
        "junction0": 999,
        "edge_id": "corrupt",
        "endpoint0_xyz_voxel": [-1, -1, -1],
    }
    payload = build(results=results)
    first = payload["struts"][0]
    assert first["id"] == 4
    assert first["junction0"] == 20
    assert first["edge_id"] == "E_N000010_N000020"
    assert first["endpoint0_xyz_voxel"] == [9.50, 8.49, 7.50]
