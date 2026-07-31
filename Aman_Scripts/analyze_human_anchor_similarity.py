"""Compare human-reviewed struts with all registered struts.

This is an audit tool, not an automatic relabeler. It uses robust feature
distances to identify similar rows, then reports whether their existing labels
agree with the human anchor label.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "part2/artifacts/sample/full_strut_classification.csv"
REVIEWS = ROOT / "Aman_Scripts/outputs/strut_defect_classification/human_review_labels.csv"
OUTPUT = ROOT / "Aman_Scripts/outputs/strut_defect_classification/human_anchor_similarity"

NUMERIC_FEATURES = [
    "length_voxels",
    "occupancy",
    "gap_fraction",
    "p90_centerline_displacement_voxels",
    "expected_radius_median_voxels",
    "median_signed_radial_deviation_voxels",
    "p90_absolute_radial_deviation_voxels",
    "thickness_um_median",
]
CATEGORICAL_FEATURES = [
    "connected_support",
    "measurement_valid",
    "tiff_measurement_valid",
    "orientation",
    "region",
    "height_band",
]


def _robust_scale(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    scaled = pd.DataFrame(index=frame.index)
    stats: dict[str, dict[str, float]] = {}
    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(frame[column], errors="coerce")
        median = float(values.median())
        q1, q3 = values.quantile([0.25, 0.75])
        scale = float(q3 - q1)
        if not np.isfinite(scale) or scale <= 1e-9:
            scale = 1.0
        scaled[column] = (values.fillna(median) - median) / scale
        scaled[f"{column}__missing"] = values.isna().astype(float)
        stats[column] = {"median": median, "iqr": scale}
    return scaled, stats


def _distance(
    anchor: pd.Series,
    candidates: pd.DataFrame,
    scaled: pd.DataFrame,
    scale_stats: dict[str, dict[str, float]],
) -> pd.Series:
    anchor_values = []
    for column in NUMERIC_FEATURES:
        value = pd.to_numeric(pd.Series([anchor[column]]), errors="coerce").iloc[0]
        missing = float(pd.isna(value))
        if pd.isna(value):
            value = scale_stats[column]["median"]
        anchor_values.extend(
            [
                (float(value) - scale_stats[column]["median"]) / scale_stats[column]["iqr"],
                missing,
            ]
        )
    numeric_columns = [item for column in NUMERIC_FEATURES for item in (column, f"{column}__missing")]
    numeric_delta = scaled[numeric_columns].to_numpy() - np.asarray(anchor_values)
    # Numeric metrology carries most of the weight; missingness is explicitly
    # represented so an invalid measurement is not treated as a normal value.
    distance = np.sqrt(np.mean(numeric_delta**2, axis=1))
    for column in CATEGORICAL_FEATURES:
        anchor_value = str(anchor[column])
        distance += 0.20 * (candidates[column].astype(str).to_numpy() != anchor_value)
    return pd.Series(distance, index=candidates.index)


def analyze(top_k: int = 15) -> dict:
    table = pd.read_csv(TABLE, keep_default_na=False, low_memory=False)
    reviews = pd.read_csv(REVIEWS)
    table = table.merge(reviews[["strut_id", "human_label", "review_note"]], on="strut_id", how="inner", validate="one_to_one")
    all_rows = pd.read_csv(TABLE, keep_default_na=False, low_memory=False)
    scaled, scale_stats = _robust_scale(all_rows)
    records = []
    neighbor_rows = []
    for _, anchor in table.iterrows():
        candidates = all_rows[all_rows.strut_id != anchor.strut_id].copy()
        distances = _distance(anchor, candidates, scaled.loc[candidates.index], scale_stats)
        nearest = candidates.assign(similarity_distance=distances).sort_values(
            ["similarity_distance", "strut_id"]
        ).head(top_k)
        agreement = nearest["prediction"].astype(str) == str(anchor["human_label"])
        label_counts = nearest["prediction"].value_counts().to_dict()
        records.append(
            {
                "anchor_strut_id": int(anchor.strut_id),
                "human_label": str(anchor.human_label),
                "nearest_count": int(len(nearest)),
                "nearest_agreement_count": int(agreement.sum()),
                "nearest_agreement_fraction": float(agreement.mean()) if len(nearest) else None,
                "nearest_label_counts": label_counts,
                "propagation_recommendation": (
                    "do_not_propagate" if len(nearest) == 0 or agreement.mean() < 0.80
                    else "candidate_for_reviewed_cohort_propagation"
                ),
            }
        )
        for _, neighbor in nearest.iterrows():
            neighbor_rows.append(
                {
                    "anchor_strut_id": int(anchor.strut_id),
                    "human_label": str(anchor.human_label),
                    "neighbor_strut_id": int(neighbor.strut_id),
                    "neighbor_prediction": str(neighbor.prediction),
                    "similarity_distance": float(neighbor.similarity_distance),
                    "label_agrees": str(neighbor.prediction) == str(anchor.human_label),
                    "neighbor_occupancy": neighbor.occupancy,
                    "neighbor_gap_fraction": neighbor.gap_fraction,
                    "neighbor_thickness_um": neighbor.thickness_um_median,
                    "neighbor_centerline_displacement_voxels": neighbor.p90_centerline_displacement_voxels,
                    "neighbor_length_voxels": neighbor.length_voxels,
                }
            )
    summary = {
        "table": str(TABLE),
        "human_reviews": str(REVIEWS),
        "population_size": int(len(all_rows)),
        "anchor_count": int(len(table)),
        "features": {"numeric": NUMERIC_FEATURES, "categorical": CATEGORICAL_FEATURES},
        "distance_method": "robust median/IQR numeric distance plus categorical mismatch penalties; current labels are reported only after similarity ranking",
        "scale_statistics": scale_stats,
        "anchors": records,
        "interpretation": "Similarity is evidence for selecting additional human review, not proof that a label should be propagated. No automatic relabeling is performed by this audit.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(neighbor_rows).to_csv(OUTPUT / "nearest_neighbors.csv", index=False)
    pd.DataFrame(records).to_csv(OUTPUT / "anchor_agreement.csv", index=False)
    return summary


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, default=str))
