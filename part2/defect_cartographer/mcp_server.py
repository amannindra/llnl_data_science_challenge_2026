"""Read-only FastMCP server for saved lattice CT evidence."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .schemas import ArtifactFilter, ThreeJSSceneRequest
from .service import DEFAULT_SERVICE


mcp = FastMCP(
    "Lattice CT Evidence",
    instructions=(
        "Query only deterministic saved artifacts from the full 18,468-strut "
        "automated classification. Candidate labels are not validated defects. "
        "Never describe classification fractions as validated prevalence or "
        "uncalibrated confidence as probability."
    ),
)


@mcp.tool
def get_pipeline_summary() -> dict[str, Any]:
    """Return aggregate candidate, alignment, thickness, and reliability evidence."""

    return DEFAULT_SERVICE.get_pipeline_summary()


@mcp.tool
def get_strut_details(strut_id: int) -> dict[str, Any]:
    """Return saved deterministic features for one sampled strut ID."""

    return DEFAULT_SERVICE.get_strut_details(strut_id)


@mcp.tool
def filter_defect_candidates(
    filters: ArtifactFilter | None = None,
) -> dict[str, Any]:
    """Filter saved candidates by validated class, location, or feature ranges."""

    return DEFAULT_SERVICE.filter_defect_candidates(filters)


@mcp.tool
def compare_defect_groups(
    group_by: str = "prediction",
    metric: str = "count",
    filters: ArtifactFilter | None = None,
) -> dict[str, Any]:
    """Compare one allow-listed metric across candidate, region, height, or orientation."""

    return DEFAULT_SERVICE.compare_defect_groups(group_by, metric, filters)


@mcp.tool
def get_methodology(section: str = "overview") -> dict[str, Any]:
    """Return a bounded generated-report section explaining the deterministic method."""

    return DEFAULT_SERVICE.get_methodology(section)


@mcp.tool
def prepare_threejs_scene(
    request: ThreeJSSceneRequest | None = None,
) -> dict[str, Any]:
    """Prepare a bounded Three.js scene spec without returning geometry or raw CT."""

    return DEFAULT_SERVICE.prepare_threejs_scene(request)


if __name__ == "__main__":
    mcp.run()
