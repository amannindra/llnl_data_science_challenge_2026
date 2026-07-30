from __future__ import annotations

import pandas as pd
import pytest

from defect_cartographer.core.clustering import (
    clustering_record,
    clustering_summary,
    load_clustering_artifact,
)


def test_clustering_contract_is_optional(tmp_path) -> None:
    assert clustering_summary(tmp_path)["status"] == "not_available"
    assert clustering_record(tmp_path, 42) == {
        "status": "not_available",
        "strut_id": 42,
    }


def test_clustering_contract_discovers_valid_assignments(tmp_path) -> None:
    path = tmp_path / "strut_clusters.csv"
    pd.DataFrame(
        [
            {
                "strut_id": 10,
                "cluster_id": "edge-a",
                "cluster_description": "Edge-adjacent candidate group",
                "clustering_source": "anthony-clustering-agent",
                "clustering_version": "0.1",
                "cluster_size": 2,
                "spatial_metric_name": "neighbor_distance_vox",
                "spatial_metric_value": 8.5,
                "supporting_evidence": "saved-neighbor-summary",
            },
            {
                "strut_id": 11,
                "cluster_id": "edge-a",
                "cluster_description": "Edge-adjacent candidate group",
                "clustering_source": "anthony-clustering-agent",
                "clustering_version": "0.1",
                "cluster_size": 2,
                "spatial_metric_name": "neighbor_distance_vox",
                "spatial_metric_value": 7.0,
                "supporting_evidence": "saved-neighbor-summary",
            },
        ]
    ).to_csv(path, index=False)

    table = load_clustering_artifact(path)
    summary = clustering_summary(tmp_path)
    record = clustering_record(tmp_path, 10)

    assert table["strut_id"].tolist() == [10, 11]
    assert summary["status"] == "artifact_ready_for_integration"
    assert summary["assignment_count"] == 2
    assert summary["cluster_count"] == 1
    assert summary["agent_active"] is False
    assert record["status"] == "assignment_available"
    assert record["record"]["cluster_id"] == "edge-a"


def test_clustering_contract_rejects_incomplete_artifacts(tmp_path) -> None:
    path = tmp_path / "clustering_results.csv"
    pd.DataFrame([{"strut_id": 1, "cluster_id": "a"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        load_clustering_artifact(path)
