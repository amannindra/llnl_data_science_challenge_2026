from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


SAMPLE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "sample"


def test_verified_sample_artifacts_have_expected_schema_and_counts() -> None:
    table = pd.read_csv(SAMPLE_DIR / "sampled_struts.csv")
    metrics = json.loads((SAMPLE_DIR / "pipeline_metrics.json").read_text())
    alignment = json.loads((SAMPLE_DIR / "alignment.json").read_text())
    manifest = json.loads((SAMPLE_DIR / "run_manifest.json").read_text())

    assert len(table) == 60
    assert table["strut_id"].nunique() == 60
    assert table["prediction"].value_counts().sort_index().to_dict() == {
        "broken": 1,
        "intact": 49,
        "missing": 2,
        "thin": 5,
        "uncertain": 3,
    }
    assert not {"split", "manual_label", "manual_notes"}.intersection(table.columns)
    assert metrics["ground_truth_available"] is False
    assert metrics["classification_coverage"] == 0.95
    assert alignment["reliable"] is True
    assert alignment["selected_permutation"] == [2, 1, 0]
    assert manifest["pipeline_scope"] == "deterministic_60_strut_mvp"
    assert manifest["artifacts"]["xray_context.npz"]["size_bytes"] > 0


def test_report_embeds_both_generated_figures() -> None:
    report = (SAMPLE_DIR / "defect_cartographer_report.md").read_text()
    assert "](thickness_histogram.png)" in report
    assert "](spatial_distribution.png)" in report
    assert "not validated defect labels" in report


def test_saved_metadata_contains_no_machine_specific_absolute_paths() -> None:
    alignment = (SAMPLE_DIR / "alignment.json").read_text(encoding="utf-8")
    manifest = (SAMPLE_DIR / "run_manifest.json").read_text(encoding="utf-8")

    assert "/Users/" not in alignment
    assert "/Users/" not in manifest
