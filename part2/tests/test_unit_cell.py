from __future__ import annotations

import json

import numpy as np

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.core.io import read_json
from defect_cartographer.core.unit_cell import (
    FIXED_UNIT_CELL_EXAMPLES,
    UNIT_CELL_STRUT_COUNT,
    load_unit_cell_scene,
)
from defect_cartographer.dashboard.threejs_component import unit_cell_scene_payload


UNIT_CELL_DIR = DEFAULT_CONFIG.output_dir / "unit_cells"


def test_four_fixed_unit_cell_examples_are_declared() -> None:
    assert [
        (item.key, item.cell_id, item.target_strut_id, item.expected_label)
        for item in FIXED_UNIT_CELL_EXAMPLES
    ] == [
        ("broken", 521, 12958, "broken"),
        ("missing", 646, 16082, "missing"),
        ("thin", 605, 15040, "thin"),
        ("intact", 362, 9000, "intact"),
    ]


def test_fixed_unit_cell_scenes_preserve_registered_geometry() -> None:
    for example in FIXED_UNIT_CELL_EXAMPLES:
        path = UNIT_CELL_DIR / f"{example.key}_cell_{example.cell_id}.npz"
        scene = load_unit_cell_scene(path)

        assert int(scene["cell_id"]) == example.cell_id
        assert int(scene["target_strut_id"]) == example.target_strut_id
        assert str(scene["target_label"]) == example.expected_label
        assert scene["nominal_segments_zyx"].shape == (
            UNIT_CELL_STRUT_COUNT,
            2,
            3,
        )
        assert scene["nominal_strut_ids"].shape == (UNIT_CELL_STRUT_COUNT,)
        assert example.target_strut_id in scene["nominal_strut_ids"]
        assert scene["nominal_junction_ids"].shape == (
            UNIT_CELL_STRUT_COUNT,
            2,
        )
        assert len(scene["junction_ids"]) == len(scene["junction_positions_zyx"])
        assert str(scene["selected_mapping"]) == (
            "JSON (x,y,z) -> CT array (z,y,x)"
        )
        assert scene["xray_vertices_zyx"].shape[1] == 3
        assert scene["xray_faces"].shape[1] == 3
        assert scene["xray_vertex_texture"].shape == (
            len(scene["xray_vertices_zyx"]),
        )
        assert np.all((scene["xray_vertex_texture"] >= 0) & (
            scene["xray_vertex_texture"] <= 1
        ))
        assert "volume" not in scene
        assert "voxels" not in scene


def test_unit_cell_metadata_and_contours_are_traceable() -> None:
    for example in FIXED_UNIT_CELL_EXAMPLES:
        stem = f"{example.key}_cell_{example.cell_id}"
        metadata = read_json(UNIT_CELL_DIR / f"{stem}.json")

        assert metadata["display_strut_count"] == UNIT_CELL_STRUT_COUNT
        assert metadata["graph_cell_strut_count"] in {24, 28}
        assert metadata["target_strut_id"] == example.target_strut_id
        assert metadata["specimen_tilt_preserved"] is True
        assert metadata["raw_ct_embedded"] is False
        assert "not calibrated roughness" in metadata["surface_texture"]
        assert "visual evidence only" in metadata["classification_scope"]
        assert metadata["display_selection_rule"] == (
            "canonical first 24 ordered graph struts"
        )
        assert (UNIT_CELL_DIR / f"{stem}_contours.png").stat().st_size > 100_000

    broken = read_json(UNIT_CELL_DIR / "broken_cell_521.json")
    missing = read_json(UNIT_CELL_DIR / "missing_cell_646.json")
    assert "largest unsupported" in broken["focus_method"]
    assert "midpoint" in missing["focus_method"]
    assert np.isclose(broken["target_gap_fraction"], 0.40707964601769914)
    assert missing["target_gap_fraction"] == 1.0


def test_unit_cell_browser_payload_contains_no_raw_ct() -> None:
    for example in FIXED_UNIT_CELL_EXAMPLES:
        path = UNIT_CELL_DIR / f"{example.key}_cell_{example.cell_id}.npz"
        payload = unit_cell_scene_payload(str(path.resolve()))
        serialized = json.dumps(payload, separators=(",", ":")).lower()

        assert payload["sceneKind"] == "unit_cell"
        assert payload["cellId"] == example.cell_id
        assert payload["targetStrutId"] == example.target_strut_id
        assert len(payload["nominalStrutIds"]) == UNIT_CELL_STRUT_COUNT
        assert len(payload["xrayVertexTexture"]) == len(payload["xrayVerticesZyx"]) // 3
        assert "volume" not in serialized
        assert "voxelvalues" not in serialized
        assert "tiff" not in serialized
