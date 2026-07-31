"""User-facing manager with direct evidence tools and one specialist."""

from __future__ import annotations

from typing import Any

from agents import Agent

from ..schemas import CopilotResponse
from .mcp_tools import ANALYSIS_MCP_TOOLS
from .shared import GLOBAL_SAFETY_INSTRUCTIONS


def build_analysis_coordinator(
    model: str,
    visualization_subagent: Agent[Any],
) -> Agent[Any]:
    """Build the manager with bounded evidence tools and display delegation."""

    return Agent(
        name="Analysis Coordinator",
        model=model,
        instructions=(
            "Act as the sole user-facing manager for lattice CT analysis. Query the "
            "read-only evidence tools directly for measurements, comparisons, and "
            "methodology. Delegate display, reporting, and Three.js scene questions "
            "to the Visualization and Reporting Sub-agent. Combine the evidence into "
            "one concise response. Clustering is an inactive future integration: use "
            "pipeline or strut evidence to report a saved assignment only when the "
            "clustering artifact status says it is available, and never infer clusters. "
            "Do not answer artifact-specific claims from memory. "
            + GLOBAL_SAFETY_INSTRUCTIONS
        ),
        tools=[
            *ANALYSIS_MCP_TOOLS,
            visualization_subagent.as_tool(
                tool_name="ask_visualization_reporting_subagent",
                tool_description=(
                    "Plan evidence-backed displays, explain methodology, or prepare "
                    "a bounded Three.js scene specification."
                ),
            ),
        ],
        output_type=CopilotResponse,
    )
