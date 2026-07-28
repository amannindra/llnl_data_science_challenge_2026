from __future__ import annotations

import pandas as pd

from defect_cartographer.core.metrics import pipeline_metrics


def test_metrics_are_automated_and_do_not_claim_accuracy() -> None:
    table = pd.DataFrame(
        [
            {
                "prediction": "intact",
                "runtime_seconds": 0.1,
                "alignment_error_vox": 1.0,
                "diameter_median_um": 350.0,
                "threshold_stability": 1.0,
                "thickness_measurement_valid": True,
            },
            {
                "prediction": "missing",
                "runtime_seconds": 0.2,
                "alignment_error_vox": float("nan"),
                "diameter_median_um": float("nan"),
                "threshold_stability": 1.0,
                "thickness_measurement_valid": False,
            },
        ]
    )
    metrics = pipeline_metrics(table)
    assert metrics["ground_truth_available"] is False
    assert metrics["evaluation_scope"] == "automated_internal_reliability_only"
    assert metrics["prediction_counts"] == {"intact": 1, "missing": 1}
    assert "accuracy" in metrics["warning"]
    assert not any("manual" in key or "holdout" in key for key in metrics)
