from __future__ import annotations

import numpy as np

from defect_cartographer.core.alignment import diagnose_alignment


def test_alignment_selects_zyx_mapping_and_passes_gate() -> None:
    volume = np.zeros((22, 30, 42), dtype=np.uint16)
    graph = {
        "junctions": [
            {"id": 0, "position": [5.0, 8.0, 4.0]},
            {"id": 1, "position": [35.0, 8.0, 4.0]},
            {"id": 2, "position": [5.0, 20.0, 16.0]},
            {"id": 3, "position": [35.0, 20.0, 16.0]},
        ],
        "struts": [
            {"id": 0, "junction0": 0, "junction1": 1},
            {"id": 1, "junction0": 2, "junction1": 3},
        ],
        "unit_cells": [],
    }
    volume[4, 8, 5:36] = 1000
    volume[16, 20, 5:36] = 1000
    intensity_sample = np.concatenate(
        [np.zeros(1000, dtype=np.uint16), np.full(200, 1000, dtype=np.uint16)]
    )
    result = diagnose_alignment(
        volume,
        graph,
        intensity_sample,
        seed=1,
        sample_struts=2,
        search_radius=2,
        voxel_spacing_um=(1.0, 1.0, 1.0),
    )
    assert result.reliable
    assert result.selected_permutation == (2, 1, 0)
    assert result.residual_correction_applied is False
    assert result.median_material_distance_vox == 0.0
