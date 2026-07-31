from __future__ import annotations

import pandas as pd

from defect_cartographer.dashboard.data import load_dashboard_artifacts


def test_full_main_artifact_is_normalised_for_current_frontend() -> None:
    artifacts = load_dashboard_artifacts()

    assert len(artifacts.table) == 18_468
    assert artifacts.scene_path is not None
    assert artifacts.scene_path.name == "full_lattice_scene.npz"
    assert artifacts.table.loc[0, "raw_prediction"] == "not_applicable"
    assert set(artifacts.table["prediction"]) == {
        "intact",
        "missing",
        "broken",
        "uncertain",
    }
    assert artifacts.metrics["sample_size"] == 18_468
    assert artifacts.metrics["prediction_counts"] == {
        "intact": 6_598,
        "missing": 246,
        "broken": 90,
        "uncertain": 11_534,
    }
    assert artifacts.metrics["prediction_counts"]["broken"] == 90
    assert "human_label" not in artifacts.table.columns
    assert "label_source" not in artifacts.table.columns
    assert "review_note" not in artifacts.table.columns
    assert (
        artifacts.table.loc[
            artifacts.table["strut_id"] == 10005, "prediction"
        ].item()
        == "missing"
    )
    assert artifacts.table.loc[0, "raw_prediction"] == artifacts.table.loc[
        0, "automated_prediction"
    ]


def test_explicit_artifact_directory_accepts_a_small_saved_run(tmp_path) -> None:
    table = pd.DataFrame(
        [
            {"strut_id": 10, "prediction": "healthy", "occupancy": 1.0, "gap_fraction": 0.0, "diameter_median_um": 350.0, "measurement_valid": True},
            {"strut_id": 11, "prediction": "bent_or_misaligned", "occupancy": 0.5, "gap_fraction": 0.5, "diameter_median_um": 300.0, "measurement_valid": True},
        ]
    )
    table.to_csv(tmp_path / "agent_results.csv", index=False)

    artifacts = load_dashboard_artifacts(tmp_path)

    assert artifacts.scene_path is None
    assert artifacts.table["prediction"].tolist() == ["intact", "uncertain"]
    assert artifacts.table["raw_prediction"].tolist() == [
        "healthy",
        "bent_or_misaligned",
    ]
