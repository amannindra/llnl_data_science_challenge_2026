"""Visualization and reporting specialist sub-agent."""

from __future__ import annotations

from typing import Any

from agents import Agent

from .mcp_tools import VISUALIZATION_MCP_TOOLS
from .shared import GLOBAL_SAFETY_INSTRUCTIONS


def build_visualization_reporting_subagent(model: str) -> Agent[Any]:
    """Build the display-focused specialist used by the coordinator."""

    return Agent(
        name="Visualization and Reporting Sub-agent",
        model=model,
        instructions=(
            "Translate saved lattice CT artifacts into visualization and report "
            "guidance. Explain charts and methodology and prepare bounded Three.js "
            "scene specifications. Use prepare_threejs_scene to return only class "
            "filters, spatial bounds, a selected strut ID, and the compact scene "
            "artifact reference. Never request or place full lattice geometry or raw "
            "CT voxels in model context; the dashboard loads geometry directly. "
            "Only recommend clustering displays when get_pipeline_summary reports a "
            "compatible clustering artifact; otherwise state that the future specialist "
            "slot is inactive. "
            "Return display recommendations to the Analysis Coordinator. "
            + GLOBAL_SAFETY_INSTRUCTIONS
        ),
        tools=VISUALIZATION_MCP_TOOLS,
    )
