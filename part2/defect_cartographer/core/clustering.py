"""Read-only contract for an optional teammate clustering artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


CLUSTERING_ARTIFACT_NAMES = (
    "strut_clusters.csv",
    "clustering_results.csv",
    "cluster_assignments.csv",
)
REQUIRED_CLUSTER_COLUMNS = {
    "strut_id",
    "cluster_id",
    "cluster_description",
    "clustering_source",
    "clustering_version",
}
OPTIONAL_CLUSTER_COLUMNS = {
    "cluster_size",
    "spatial_metric_name",
    "spatial_metric_value",
    "supporting_evidence",
}


def clustering_artifact_path(directory: Path | str) -> Path | None:
    """Return the first recognized clustering CSV without searching broadly."""

    root = Path(directory)
    for name in CLUSTERING_ARTIFACT_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def load_clustering_artifact(path: Path | str) -> pd.DataFrame:
    """Load and validate Anthony's future strut-level clustering contract."""

    table = pd.read_csv(Path(path))
    missing = REQUIRED_CLUSTER_COLUMNS.difference(table.columns)
    if missing:
        raise ValueError(
            f"Clustering artifact is missing columns: {sorted(missing)}"
        )
    ids = pd.to_numeric(table["strut_id"], errors="coerce")
    if ids.isna().any() or ids.duplicated().any() or (ids < 0).any():
        raise ValueError("Clustering strut_id values must be unique non-negative integers")
    table = table.copy()
    table["strut_id"] = ids.astype("int64")
    for column in (
        "cluster_id",
        "cluster_description",
        "clustering_source",
        "clustering_version",
    ):
        values = table[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"Clustering column {column} cannot contain empty values")
        table[column] = values.astype(str)
    for column in ("cluster_size", "spatial_metric_value"):
        if column in table.columns:
            numeric = pd.to_numeric(table[column], errors="coerce")
            if numeric.isna().any():
                raise ValueError(f"Clustering column {column} must be numeric")
            table[column] = numeric
    return table.sort_values("strut_id").reset_index(drop=True)


def clustering_summary(directory: Path | str) -> dict[str, Any]:
    """Report readiness without inventing assignments when no artifact exists."""

    path = clustering_artifact_path(directory)
    if path is None:
        return {
            "status": "not_available",
            "agent_active": False,
            "artifact_present": False,
            "assignment_count": 0,
            "contract_version": 1,
            "expected_artifact_names": list(CLUSTERING_ARTIFACT_NAMES),
        }
    table = load_clustering_artifact(path)
    return {
        "status": "artifact_ready_for_integration",
        "agent_active": False,
        "artifact_present": True,
        "artifact_name": path.name,
        "assignment_count": len(table),
        "cluster_count": int(table["cluster_id"].nunique()),
        "sources": sorted(table["clustering_source"].unique().tolist()),
        "versions": sorted(table["clustering_version"].unique().tolist()),
        "contract_version": 1,
    }


def clustering_record(directory: Path | str, strut_id: int) -> dict[str, Any]:
    """Return one optional assignment through the same bounded evidence boundary."""

    path = clustering_artifact_path(directory)
    if path is None:
        return {"status": "not_available", "strut_id": int(strut_id)}
    table = load_clustering_artifact(path)
    rows = table.loc[table["strut_id"] == int(strut_id)]
    if rows.empty:
        return {"status": "no_assignment", "strut_id": int(strut_id)}
    return {
        "status": "assignment_available",
        "record": rows.iloc[0].to_dict(),
    }
