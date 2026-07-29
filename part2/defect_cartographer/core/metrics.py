"""Honest automated summaries for an unlabeled exploratory pipeline."""

from __future__ import annotations

from collections import Counter
import platform
import resource
from typing import Any

import numpy as np
import pandas as pd


def _safe_number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def pipeline_metrics(table: pd.DataFrame) -> dict[str, Any]:
    """Summarize reliability and runtime without claiming accuracy."""

    prediction_counts = Counter(table["prediction"].astype(str))
    classified = table["prediction"] != "uncertain"
    peak_rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    peak_rss_mb = (
        peak_rss / (1024.0 * 1024.0)
        if platform.system() == "Darwin"
        else peak_rss / 1024.0
    )
    valid_thickness = table["thickness_measurement_valid"].astype(bool)
    return {
        "sample_size": int(len(table)),
        "prediction_counts": dict(sorted(prediction_counts.items())),
        "classification_coverage": float(classified.mean()),
        "uncertain_fraction": float((~classified).mean()),
        "mean_runtime_seconds_per_strut": float(table["runtime_seconds"].mean()),
        "total_runtime_seconds": float(table["runtime_seconds"].sum()),
        "process_peak_rss_mb": peak_rss_mb,
        "median_alignment_error_vox": _safe_number(
            float(table["alignment_error_vox"].median())
        ),
        "p90_alignment_error_vox": _safe_number(
            float(table["alignment_error_vox"].quantile(0.9))
        ),
        "valid_thickness_measurement_count": int(valid_thickness.sum()),
        "median_diameter_um": _safe_number(
            float(table.loc[valid_thickness, "diameter_median_um"].median())
        ),
        "diameter_std_um": _safe_number(
            float(table.loc[valid_thickness, "diameter_median_um"].std())
        ),
        "median_threshold_stability": float(
            table["threshold_stability"].median()
        ),
        "evaluation_scope": "automated_internal_reliability_only",
        "ground_truth_available": False,
        "warning": (
            "Predictions are exploratory candidates. Counts are not accuracy, "
            "precision, recall, or full-part prevalence."
        ),
    }
