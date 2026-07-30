"""In-process protocol tests for the FastMCP boundary."""

from __future__ import annotations

import asyncio

from fastmcp import Client

from defect_cartographer.mcp_server import mcp


NATIVE_TOOLS = {
    "get_pipeline_summary",
    "get_strut_details",
    "filter_defect_candidates",
    "compare_defect_groups",
    "get_methodology",
    "prepare_threejs_scene",
    "get_strut_ct_evidence",
}


def test_mcp_lists_unified_dashboard_and_raw_ct_tools() -> None:
    async def inspect() -> set[str]:
        return {tool.name for tool in await mcp.list_tools()}

    names = asyncio.run(inspect())
    assert NATIVE_TOOLS <= names
    assert "raw_ct_read_tiff" in names
    assert "raw_ct_get_full_defect_summary" in names


def test_mcp_calls_return_structured_read_only_results() -> None:
    async def call_tools() -> tuple[dict, dict]:
        async with Client(mcp) as client:
            summary_result = await client.call_tool("get_pipeline_summary", {})
            filter_result = await client.call_tool(
                "filter_defect_candidates",
                {"filters": {"classes": ["missing"], "limit": 10}},
            )
        assert not summary_result.is_error
        assert not filter_result.is_error
        return summary_result.structured_content, filter_result.structured_content

    summary, filtered = asyncio.run(call_tools())
    assert summary["sample_size"] == 18_468
    assert filtered["matching_count"] == 120
    assert all(row["prediction"] == "missing" for row in filtered["records"])


def test_mcp_threejs_scene_response_excludes_large_geometry() -> None:
    async def call_scene() -> dict:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "prepare_threejs_scene",
                {
                    "request": {
                        "classes": ["missing", "broken"],
                        "include_nominal_lattice": True,
                        "include_ct_context": True,
                        "max_overlays": 10,
                    }
                },
            )
        assert not result.is_error
        return result.structured_content

    scene = asyncio.run(call_scene())
    assert scene["nominal_strut_count"] == 18_468
    assert scene["returned_overlay_count"] == 10
    assert scene["geometry_included_in_response"] is False
    assert scene["raw_ct_included"] is False
    assert "segments" not in scene
    assert "vertices" not in scene
