"""Measurement and QA specialist sub-agent."""

from __future__ import annotations

from typing import Any

from agents import Agent

from .mcp_tools import ANALYSIS_MCP_TOOLS
from .shared import GLOBAL_SAFETY_INSTRUCTIONS


def build_measurement_qa_subagent(model: str) -> Agent[Any]:
    """Build the evidence-focused specialist used by the coordinator."""

    return Agent(
        name="Measurement and QA Sub-agent",
        model=model,
        instructions=(
            "Analyze deterministic lattice CT evidence, compare bounded groups, "
            "explain per-strut measurements and rule precedence, and audit claims "
            "for scientific overreach. Return compact evidence-backed findings to "
            "the Analysis Coordinator. "
            + GLOBAL_SAFETY_INSTRUCTIONS
        ),
        tools=ANALYSIS_MCP_TOOLS,
    )
