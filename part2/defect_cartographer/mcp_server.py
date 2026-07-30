"""Read-only FastMCP server for saved lattice CT evidence."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .ct_evidence import render_strut_ct_evidence
from .schemas import ArtifactFilter, ThreeJSSceneRequest
from .service import DEFAULT_SERVICE


mcp = FastMCP(
    "Unified Lattice CT Evidence",
    instructions=(
        "Unified CT and lattice evidence agent. The native dashboard tools query "
        "deterministic saved artifacts from the full 18,468-strut classification; "
        "raw CT tools are mounted under the raw_ct namespace and may write explicit "
        "user-requested derived artifacts. Candidate labels are not validated "
        "defects. Never describe classification fractions as validated prevalence "
        "or uncalibrated confidence as probability."
    ),
)


def _mount_raw_ct_server() -> None:
    """Mount the original Aman CT tools into this single formal MCP server."""

    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "Aman_src" / "mcp_server.py"
    if not source.is_file():
        raise FileNotFoundError(f"Aman CT MCP server is missing: {source}")
    spec = importlib.util.spec_from_file_location("_unified_aman_ct_mcp", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load Aman CT MCP server: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mcp.mount(module.mcp, namespace="raw_ct")


_mount_raw_ct_server()


@mcp.tool
def get_pipeline_summary() -> dict[str, Any]:
    """Return aggregate candidate, alignment, thickness, and reliability evidence."""

    return DEFAULT_SERVICE.get_pipeline_summary()


@mcp.tool
def get_strut_details(strut_id: int) -> dict[str, Any]:
    """Return saved deterministic features for one full-lattice strut ID."""

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


@mcp.tool
def get_strut_ct_evidence(
    strut_id: int,
    crop_radius_voxels: int = 24,
) -> dict[str, Any]:
    """Render bounded orthogonal CT evidence for one registered strut."""

    return render_strut_ct_evidence(
        strut_id,
        crop_radius_voxels=crop_radius_voxels,
    )


if __name__ == "__main__":
    mcp.run()
