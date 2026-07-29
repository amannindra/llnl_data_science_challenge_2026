from __future__ import annotations

import numpy as np
import pandas as pd

from defect_cartographer.core.analysis import (
    RuleSettings,
    analyze_strut,
    classify_candidates,
)


def cylinder_volume(gap: bool = False) -> np.ndarray:
    volume = np.full((41, 41, 41), 100, dtype=np.uint16)
    zz, yy, xx = np.indices(volume.shape)
    cylinder = ((zz - 20) ** 2 + (yy - 20) ** 2 <= 2**2) & (xx >= 5) & (xx <= 35)
    if gap:
        cylinder &= ~((xx >= 16) & (xx <= 25))
    volume[cylinder] = 1000
    return volume


def test_intact_and_broken_features_are_distinguishable() -> None:
    common = dict(
        start=np.array([20.0, 20.0, 5.0]),
        end=np.array([20.0, 20.0, 35.0]),
        base_threshold=500.0,
        threshold_factors=(0.9, 1.0, 1.1),
        voxel_spacing_um=(1.0, 1.0, 1.0),
        search_radius=2,
        rules=RuleSettings(),
    )
    intact = analyze_strut(cylinder_volume(False), **common)
    broken = analyze_strut(cylinder_volume(True), **common)
    assert intact["occupancy"] > 0.95
    assert intact["gap_fraction"] == 0.0
    assert broken["occupancy"] < intact["occupancy"]
    assert broken["gap_fraction"] > 0.1
    assert 4.0 <= intact["diameter_median_um"] <= 6.0


def _classify(row: dict) -> str:
    row.setdefault("threshold_states", "intact|intact|intact")
    row.setdefault("largest_gap_center_fraction", 0.5)
    row.setdefault("start_z", 0.0)
    row.setdefault("start_y", 0.0)
    row.setdefault("start_x", 0.0)
    row.setdefault("end_z", 1.0)
    row.setdefault("end_y", 1.0)
    row.setdefault("end_x", 1.0)
    classified, _ = classify_candidates(
        pd.DataFrame([row]),
        rules=RuleSettings(),
        design_diameter_um=350.0,
    )
    return str(classified.loc[0, "prediction"])


def test_rule_precedence_missing_before_alignment_uncertainty() -> None:
    assert _classify(
        {
            "coarse_state": "missing",
            "alignment_error_vox": float("nan"),
            "threshold_stability": 1.0,
            "diameter_median_um": float("nan"),
            "occupancy": 0.0,
            "gap_fraction": 1.0,
            "region": "interior",
            "threshold_states": "missing|missing|missing",
        }
    ) == "missing"


def test_missing_requires_almost_no_material_at_every_threshold() -> None:
    for occupancy in (0.0, 0.10):
        assert _classify(
            {
                "coarse_state": "missing",
                "alignment_error_vox": float("nan"),
                "threshold_stability": 1.0,
                "diameter_median_um": float("nan"),
                "occupancy": occupancy,
                "gap_fraction": 1.0 - occupancy,
                "region": "interior",
                "threshold_states": "missing|missing|missing",
            }
        ) == "missing"


def test_missing_threshold_disagreement_is_uncertain() -> None:
    assert _classify(
        {
            "coarse_state": "missing",
            "alignment_error_vox": float("nan"),
            "threshold_stability": 2.0 / 3.0,
            "diameter_median_um": float("nan"),
            "occupancy": 0.10,
            "gap_fraction": 0.90,
            "region": "interior",
            "threshold_states": "broken|missing|missing",
        }
    ) == "uncertain"


def test_partial_internal_support_is_broken_not_missing() -> None:
    assert _classify(
        {
            "coarse_state": "broken",
            "alignment_error_vox": 1.0,
            "threshold_stability": 1.0,
            "diameter_median_um": 260.0,
            "occupancy": 0.11,
            "gap_fraction": 0.40,
            "region": "interior",
            "threshold_states": "broken|broken|broken",
        }
    ) == "broken"


def test_candidate_output_exposes_replaceable_detector_contract() -> None:
    row = {
        "strut_id": 7,
        "coarse_state": "intact",
        "alignment_error_vox": 0.0,
        "threshold_stability": 1.0,
        "threshold_states": "intact|intact|intact",
        "diameter_median_um": 340.0,
        "occupancy": 1.0,
        "gap_fraction": 0.0,
        "largest_gap_center_fraction": 0.5,
        "region": "interior",
        "start_z": 0.0,
        "start_y": 1.0,
        "start_x": 2.0,
        "end_z": 2.0,
        "end_y": 3.0,
        "end_x": 4.0,
    }
    classified, _ = classify_candidates(
        pd.DataFrame([row]),
        rules=RuleSettings(),
        design_diameter_um=350.0,
    )
    assert classified.loc[0, "label"] == classified.loc[0, "prediction"]
    assert classified.loc[0, "label_source"] == "deterministic_rule_baseline"
    assert classified.loc[0, "label_version"] == "rules-v2-missing-0.10"
    assert classified.loc[0, "evidence_focus_zyx"] == "[1.0,2.0,3.0]"


def test_large_alignment_error_is_uncertain() -> None:
    assert _classify(
        {
            "coarse_state": "intact",
            "alignment_error_vox": 4.0,
            "threshold_stability": 1.0,
            "diameter_median_um": 340.0,
            "occupancy": 1.0,
            "gap_fraction": 0.0,
            "region": "interior",
        }
    ) == "uncertain"
