from __future__ import annotations

import numpy as np

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.core.scene import LABEL_NAMES, load_lattice_scene


SCENE_PATH = DEFAULT_CONFIG.output_dir / "lattice_scene.npz"


def test_saved_scene_contains_full_lattice_and_sample() -> None:
    scene = load_lattice_scene(SCENE_PATH)

    assert int(scene["schema_version"]) == 2
    assert scene["nominal_segments_zyx"].shape == (18_468, 2, 3)
    assert scene["nominal_strut_ids"].shape == (18_468,)
    assert scene["junction_positions_zyx"].shape == (10_206, 3)
    assert scene["junction_ids"].shape == (10_206,)
    assert scene["nominal_junction_ids"].shape == (18_468, 2)
    assert scene["analyzed_segments_zyx"].shape == (60, 2, 3)
    assert scene["analyzed_strut_ids"].shape == (60,)
    assert scene["analyzed_label_codes"].shape == (60,)
    assert tuple(scene["label_names"].tolist()) == LABEL_NAMES
    assert str(scene["selected_mapping"]) == "JSON (x,y,z) -> CT array (z,y,x)"


def test_analyzed_segments_are_exact_nominal_subsets() -> None:
    scene = load_lattice_scene(SCENE_PATH)
    nominal = {
        int(strut_id): segment
        for strut_id, segment in zip(
            scene["nominal_strut_ids"], scene["nominal_segments_zyx"]
        )
    }

    for strut_id, analyzed in zip(
        scene["analyzed_strut_ids"], scene["analyzed_segments_zyx"]
    ):
        np.testing.assert_allclose(analyzed, nominal[int(strut_id)], atol=1e-4)


def test_scene_contains_bounded_ct_surface_not_voxels() -> None:
    scene = load_lattice_scene(SCENE_PATH)

    assert scene["xray_vertices_zyx"].shape[1] == 3
    assert scene["xray_faces"].shape[1] == 3
    assert "volume" not in scene
    assert "voxels" not in scene


def test_registered_junctions_match_each_nominal_segment_endpoint() -> None:
    scene = load_lattice_scene(SCENE_PATH)
    positions = {
        int(junction_id): position
        for junction_id, position in zip(
            scene["junction_ids"], scene["junction_positions_zyx"]
        )
    }

    for segment, endpoint_ids in zip(
        scene["nominal_segments_zyx"], scene["nominal_junction_ids"]
    ):
        np.testing.assert_allclose(segment[0], positions[int(endpoint_ids[0])], atol=1e-4)
        np.testing.assert_allclose(segment[1], positions[int(endpoint_ids[1])], atol=1e-4)
