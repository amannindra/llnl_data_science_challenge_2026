from __future__ import annotations

import numpy as np

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.core.scene import LABEL_NAMES, load_lattice_scene


SCENE_PATH = DEFAULT_CONFIG.dashboard_scene_path


def test_saved_scene_contains_full_lattice_and_sample() -> None:
    scene = load_lattice_scene(SCENE_PATH)

    assert scene["nominal_segments_zyx"].shape == (18_468, 2, 3)
    assert scene["nominal_strut_ids"].shape == (18_468,)
    assert scene["analyzed_segments_zyx"].shape == (18_468, 2, 3)
    assert scene["analyzed_strut_ids"].shape == (18_468,)
    assert scene["analyzed_label_codes"].shape == (18_468,)
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
