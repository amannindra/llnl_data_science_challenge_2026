"""User-facing manager agent that delegates to two specialist sub-agents."""

from __future__ import annotations

from typing import Any

from agents import Agent

from ..schemas import CopilotResponse
from .shared import GLOBAL_SAFETY_INSTRUCTIONS


def build_analysis_coordinator(
    model: str,
    measurement_subagent: Agent[Any],
    visualization_subagent: Agent[Any],
) -> Agent[Any]:
    """Build the manager with explicit, bounded specialist delegation."""

    return Agent(
        name="Analysis Coordinator",
        model=model,
        instructions=(
            "Act as the sole user-facing manager for lattice CT analysis. Delegate "
            "measurement and QA questions to the Measurement and QA Sub-agent. "
            "Delegate display, reporting, and Three.js scene questions to the "
            "Visualization and Reporting Sub-agent. Combine their evidence into one "
            "concise response. Do not answer artifact-specific claims from memory. "
            + GLOBAL_SAFETY_INSTRUCTIONS
        ),
        tools=[
            measurement_subagent.as_tool(
                tool_name="ask_measurement_qa_subagent",
                tool_description=(
                    "Analyze saved measurements, compare groups, inspect a strut, "
                    "or audit a scientific interpretation."
                ),
            ),
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
