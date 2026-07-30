"""Lightweight orchestration tests for complete-STL surface retention.

All graph/STL operations are stubbed.  These tests therefore verify argument
routing without opening the real JSON or either multi-million-triangle STL.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np

import Aman_Scripts.Components.strut_pipeline as pipeline


def _install_stubs(monkeypatch):
    graph = object()
    atlas_ids = np.asarray([17, 23, 91], dtype=np.int64)
    atlas = {"strut_ids": atlas_ids, "atlas_marker": "same-object"}
    complete_surface = {"surface": "complete"}
    specimen_surface = {"surface": "specimen"}
    intent = {"removed_strut_ids": np.asarray([23], dtype=np.int64)}
    state = {
        "load_calls": [],
        "atlas_calls": [],
        "sample_calls": [],
        "intent_calls": [],
    }

    def fake_load(path):
        state["load_calls"].append(path)
        return graph

    def fake_atlas(received_graph, **kwargs):
        state["atlas_calls"].append((received_graph, kwargs))
        return atlas

    def fake_sample(path, transform, received_atlas, **kwargs):
        state["sample_calls"].append({
            "path": path,
            "transform": transform,
            "atlas": received_atlas,
            **kwargs,
        })
        return (
            complete_surface
            if Path(path).name == "complete.stl"
            else specimen_surface
        )

    def fake_intent(complete, specimen, received_ids):
        state["intent_calls"].append((complete, specimen, received_ids))
        return intent

    monkeypatch.setattr(pipeline, "load_lattice_graph", fake_load)
    monkeypatch.setattr(pipeline, "build_registered_centerline_atlas", fake_atlas)
    monkeypatch.setattr(pipeline, "sample_stl_surface_against_atlas", fake_sample)
    monkeypatch.setattr(pipeline, "infer_specimen_cad_omissions", fake_intent)
    return state, atlas, complete_surface, specimen_surface, intent


def _prepare(*, retain: bool | None, monkeypatch):
    state, atlas, complete, specimen, intent = _install_stubs(monkeypatch)
    transform = np.arange(16, dtype=np.float64).reshape(4, 4)
    kwargs = {
        "axial_bins": 11,
        "endpoint_exclusion_fraction": 0.15,
        "association_radii_voxels": (3.0, 4.0),
        "workers": 3,
    }
    if retain is not None:
        kwargs["retain_complete_surface_points"] = retain
    result = pipeline.prepare_cad_strut_map(
        "never_opened/complete.stl",
        "never_opened/specimen.stl",
        "never_opened/registered.json",
        transform,
        **kwargs,
    )
    return result, state, atlas, complete, specimen, intent, transform


def test_true_retention_flag_applies_only_to_complete_stl(monkeypatch) -> None:
    result, state, atlas, complete, specimen, intent, transform = _prepare(
        retain=True,
        monkeypatch=monkeypatch,
    )

    assert len(state["sample_calls"]) == 2
    complete_call, specimen_call = state["sample_calls"]
    assert Path(complete_call["path"]).name == "complete.stl"
    assert complete_call["retain_nearest_points"] is True
    assert Path(specimen_call["path"]).name == "specimen.stl"
    assert specimen_call["retain_nearest_points"] is False
    assert complete_call["atlas"] is atlas
    assert specimen_call["atlas"] is atlas
    np.testing.assert_array_equal(complete_call["transform"], transform)
    np.testing.assert_array_equal(specimen_call["transform"], transform)
    assert result == {
        "atlas": atlas,
        "complete_surface": complete,
        "specimen_surface": specimen,
        "intent": intent,
    }


def test_false_retention_flag_keeps_both_stl_calls_lightweight(monkeypatch) -> None:
    _, state, *_ = _prepare(retain=False, monkeypatch=monkeypatch)
    assert [
        call["retain_nearest_points"] for call in state["sample_calls"]
    ] == [False, False]


def test_default_retention_is_false_in_signature_and_runtime(monkeypatch) -> None:
    parameter = inspect.signature(
        pipeline.prepare_cad_strut_map
    ).parameters["retain_complete_surface_points"]
    assert parameter.default is False

    _, state, *_ = _prepare(retain=None, monkeypatch=monkeypatch)
    assert [
        call["retain_nearest_points"] for call in state["sample_calls"]
    ] == [False, False]


def test_intent_receives_same_atlas_ids_and_surface_results(monkeypatch) -> None:
    _, state, atlas, complete, specimen, *_ = _prepare(
        retain=True,
        monkeypatch=monkeypatch,
    )
    assert len(state["intent_calls"]) == 1
    received_complete, received_specimen, received_ids = state["intent_calls"][0]
    assert received_complete is complete
    assert received_specimen is specimen
    assert received_ids is atlas["strut_ids"]


def test_sampling_controls_are_forwarded_identically_to_both_stls(monkeypatch) -> None:
    _, state, *_ = _prepare(retain=True, monkeypatch=monkeypatch)
    complete_call, specimen_call = state["sample_calls"]
    for call in (complete_call, specimen_call):
        assert call["association_radii_voxels"] == (3.0, 4.0)
        assert call["workers"] == 3

    assert len(state["atlas_calls"]) == 1
    _, atlas_kwargs = state["atlas_calls"][0]
    assert atlas_kwargs == {
        "axial_bins": 11,
        "endpoint_exclusion_fraction": 0.15,
    }

