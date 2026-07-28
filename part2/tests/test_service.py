"""Tests for the bounded, read-only saved-artifact service."""

from __future__ import annotations

from pathlib import Path

import pytest

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.schemas import (
    ArtifactFilter,
    SceneBounds,
    ThreeJSSceneRequest,
)
from defect_cartographer.service import ArtifactService


def _artifact_state(directory: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.iterdir()
        if path.is_file()
    }


def test_summary_and_filters_are_bounded_and_read_only() -> None:
    service = ArtifactService()
    before = _artifact_state(DEFAULT_CONFIG.output_dir)

    summary = service.get_pipeline_summary()
    filtered = service.filter_defect_candidates(
        ArtifactFilter(classes=["missing", "broken", "thin"], limit=3)
    )

    assert summary["sample_size"] == 60
    assert summary["candidate_counts"] == {
        "intact": 49,
        "thin": 5,
        "uncertain": 3,
        "missing": 2,
        "broken": 1,
    }
    assert filtered["matching_count"] == 8
    assert filtered["returned_count"] == 3
    assert all(
        row["prediction"] in {"missing", "broken", "thin"}
        for row in filtered["records"]
    )
    assert _artifact_state(DEFAULT_CONFIG.output_dir) == before


def test_strut_lookup_and_group_comparison() -> None:
    service = ArtifactService()
    details = service.get_strut_details(8578)
    comparison = service.compare_defect_groups(
        group_by="prediction", metric="occupancy"
    )

    assert details["record"]["strut_id"] == 8578
    assert details["record"]["prediction"] == "intact"
    assert "not_validated" in details["classification_status"]
    assert comparison["filtered_sample_size"] == 60
    assert {row["group"] for row in comparison["groups"]} == {
        "intact",
        "missing",
        "broken",
        "thin",
        "uncertain",
    }

    with pytest.raises(ValueError, match="not present"):
        service.get_strut_details(-1)
    with pytest.raises(ValueError, match="group_by"):
        service.compare_defect_groups(group_by="arbitrary")


def test_methodology_and_threejs_spec_are_bounded() -> None:
    service = ArtifactService()
    methodology = service.get_methodology("rules")
    scene = service.prepare_threejs_scene(
        ThreeJSSceneRequest(classes=["missing", "broken"])
    )

    assert "Provisional classification rules" in methodology["markdown"]
    assert scene["viewer_launched"] is False
    assert scene["read_only"] is True
    assert scene["matching_overlay_count"] == 3
    assert scene["returned_overlay_count"] == 3
    assert len(scene["overlay_strut_ids"]) == 3
    assert scene["nominal_strut_count"] == 18_468
    assert scene["analyzed_overlay_count"] == 60
    assert scene["scene_artifact"] == "lattice_scene.npz"
    assert scene["geometry_included_in_response"] is False
    assert scene["raw_ct_included"] is False
    assert "segments" not in scene
    assert "vertices" not in scene


def test_threejs_scene_selection_and_spatial_bounds() -> None:
    service = ArtifactService()
    details = service.get_strut_details(8578)["record"]
    bounds = SceneBounds(
        start_zyx=(
            details["mid_z"] - 1,
            details["mid_y"] - 1,
            details["mid_x"] - 1,
        ),
        stop_zyx=(
            details["mid_z"] + 1,
            details["mid_y"] + 1,
            details["mid_x"] + 1,
        ),
    )
    scene = service.prepare_threejs_scene(
        ThreeJSSceneRequest(
            classes=["intact"],
            selected_strut_id=8578,
            bounds_zyx=bounds,
            include_nominal_lattice=False,
            include_ct_context=False,
        )
    )

    assert scene["selected_strut_id"] == 8578
    assert scene["overlay_strut_ids"] == [8578]
    assert scene["bounds_zyx"]["start_zyx"] == list(bounds.start_zyx)
    assert scene["include_nominal_lattice"] is False
    assert scene["include_ct_context"] is False

    with pytest.raises(ValueError, match="requested class and spatial filters"):
        service.prepare_threejs_scene(
            ThreeJSSceneRequest(
                classes=["missing"],
                selected_strut_id=8578,
            )
        )


def test_schemas_reject_unsafe_or_inverted_requests() -> None:
    with pytest.raises(ValueError, match="min_occupancy"):
        ArtifactFilter(min_occupancy=0.9, max_occupancy=0.1)
    with pytest.raises(ValueError, match="At least one"):
        ThreeJSSceneRequest(classes=[])
    with pytest.raises(ValueError, match="start_zyx"):
        SceneBounds(start_zyx=(5, 0, 0), stop_zyx=(5, 1, 1))
    with pytest.raises(ValueError):
        ArtifactFilter(limit=201)
