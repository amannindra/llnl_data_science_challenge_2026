"""OpenAI Agents SDK tools backed by the in-process FastMCP server."""

from __future__ import annotations

import json
from typing import Any

from agents import function_tool
from fastmcp import Client

from ..mcp_server import mcp
from ..schemas import ArtifactFilter, ThreeJSSceneRequest


async def call_readonly_mcp(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a registered MCP tool and return its structured payload."""

    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    if result.is_error:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    payload = result.structured_content
    if not isinstance(payload, dict):
        raise RuntimeError(f"MCP tool {name} returned no structured object")
    return payload


def _tool_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, allow_nan=False)


@function_tool
async def get_pipeline_summary() -> str:
    """Get aggregate candidate, alignment, thickness, and reliability evidence."""

    return _tool_text(await call_readonly_mcp("get_pipeline_summary", {}))


@function_tool
async def get_strut_details(strut_id: int) -> str:
    """Get deterministic saved features for one sampled strut ID."""

    return _tool_text(
        await call_readonly_mcp("get_strut_details", {"strut_id": strut_id})
    )


@function_tool
async def filter_defect_candidates(filters: ArtifactFilter | None = None) -> str:
    """Filter saved candidate rows using bounded, validated fields."""

    arguments = (
        {}
        if filters is None
        else {"filters": filters.model_dump(mode="json", exclude_none=True)}
    )
    return _tool_text(await call_readonly_mcp("filter_defect_candidates", arguments))


@function_tool
async def compare_defect_groups(
    group_by: str = "prediction",
    metric: str = "count",
    filters: ArtifactFilter | None = None,
) -> str:
    """Compare one allowed metric across candidate, region, height, or orientation."""

    arguments: dict[str, Any] = {"group_by": group_by, "metric": metric}
    if filters is not None:
        arguments["filters"] = filters.model_dump(mode="json", exclude_none=True)
    return _tool_text(await call_readonly_mcp("compare_defect_groups", arguments))


@function_tool
async def get_methodology(section: str = "overview") -> str:
    """Get one bounded section of the generated deterministic methodology report."""

    return _tool_text(
        await call_readonly_mcp("get_methodology", {"section": section})
    )


@function_tool
async def prepare_threejs_scene(
    request: ThreeJSSceneRequest | None = None,
) -> str:
    """Prepare bounded Three.js filters and IDs without returning scene geometry."""

    arguments = (
        {}
        if request is None
        else {"request": request.model_dump(mode="json", exclude_none=True)}
    )
    return _tool_text(await call_readonly_mcp("prepare_threejs_scene", arguments))


ANALYSIS_MCP_TOOLS = [
    get_pipeline_summary,
    get_strut_details,
    filter_defect_candidates,
    compare_defect_groups,
    get_methodology,
]

VISUALIZATION_MCP_TOOLS = [
    get_pipeline_summary,
    filter_defect_candidates,
    get_methodology,
    prepare_threejs_scene,
]
