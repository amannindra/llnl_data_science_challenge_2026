"""FastMCP interface for input-preserving spatial clustering tools."""

from __future__ import annotations

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .core import (
    analyze_spatial_clusters as _analyze,
    analyze_knn_association as _knn,
    compare_random_baseline as _compare,
    prepare_cluster_scene as _scene,
    summarize_boundary_distribution as _boundary,
)


mcp = FastMCP("Spatial Defect Clustering")
INPUT_PRESERVING = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=INPUT_PRESERVING)
def analyze_spatial_clusters(config_path: str, run_id: str) -> dict:
    """Measure graph and DBSCAN clusters from saved candidate records.

    The tool never modifies inputs. It writes only versioned analysis artifacts
    inside the Anthony output root declared by the configuration.
    """

    return _analyze(config_path, run_id)


@mcp.tool(annotations=INPUT_PRESERVING)
def compare_random_baseline(config_path: str, run_id: str) -> dict:
    """Compare main candidates with graph, stratified, and uniform-3D null models."""

    return _compare(config_path, run_id)


@mcp.tool(annotations=INPUT_PRESERVING)
def analyze_knn_association(config_path: str, run_id: str) -> dict:
    """Compare cross-defect KNN neighborhoods with label-permutation null models."""

    return _knn(config_path, run_id)


@mcp.tool(annotations=INPUT_PRESERVING)
def summarize_boundary_distribution(config_path: str, run_id: str) -> dict:
    """Summarize defect and uncertainty labels by boundary and orientation."""

    return _boundary(config_path, run_id)


@mcp.tool(annotations=INPUT_PRESERVING)
def prepare_cluster_scene(
    config_path: str,
    run_id: str,
    offset: int = 0,
    limit: int = 1000,
) -> dict:
    """Create a paginated Three.js-compatible cluster-overlay JSON payload."""

    return _scene(config_path, run_id, offset=offset, limit=limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
