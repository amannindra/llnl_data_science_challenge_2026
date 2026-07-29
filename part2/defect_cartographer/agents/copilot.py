"""Manager-style three-agent copilot with a graceful offline mode."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from agents import Agent, RunConfig, Runner

from ..schemas import CopilotResponse
from .coordinator import build_analysis_coordinator
from .measurement_qa import build_measurement_qa_subagent
from .visualization_reporting import build_visualization_reporting_subagent


DEFAULT_AGENT_MODEL = "gpt-5.6-terra"

@dataclass(frozen=True)
class CopilotBundle:
    """The coordinator and its two specialist agents."""

    coordinator: Agent[Any]
    analysis_specialist: Agent[Any]
    visualization_specialist: Agent[Any]
    model: str


def build_copilot(model: str | None = None) -> CopilotBundle:
    """Construct the three-agent topology without calling an external API."""

    selected_model = model or os.getenv("OPENAI_MODEL", DEFAULT_AGENT_MODEL)

    analysis_specialist = build_measurement_qa_subagent(selected_model)
    visualization_specialist = build_visualization_reporting_subagent(selected_model)
    coordinator = build_analysis_coordinator(
        selected_model,
        analysis_specialist,
        visualization_specialist,
    )
    return CopilotBundle(
        coordinator=coordinator,
        analysis_specialist=analysis_specialist,
        visualization_specialist=visualization_specialist,
        model=selected_model,
    )


def copilot_status() -> dict[str, Any]:
    """Report configuration availability without exposing secret values."""

    configured = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "available": configured,
        "api_key_configured": configured,
        "model": os.getenv("OPENAI_MODEL", DEFAULT_AGENT_MODEL),
        "mode": "live" if configured else "disabled_no_api_key",
        "message": (
            "Copilot is configured for live agent calls."
            if configured
            else "Copilot is disabled because OPENAI_API_KEY is not configured."
        ),
    }


def run_copilot(
    prompt: str,
    page_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the manager agent or return a deterministic disabled response."""

    status = copilot_status()
    if not status["available"]:
        return CopilotResponse(
            answer=status["message"],
            warnings=[
                "No external API call was attempted.",
                "Deterministic MCP tools remain available without an API key.",
            ],
            status="disabled_no_api_key",
        ).model_dump(mode="json")

    bundle = build_copilot(model)
    bounded_context = json.dumps(page_context or {}, sort_keys=True)[:4_000]
    agent_input = (
        f"User request:\n{prompt[:8_000]}\n\n"
        f"Read-only dashboard context (may be empty):\n{bounded_context}"
    )
    result = Runner.run_sync(
        bundle.coordinator,
        agent_input,
        max_turns=8,
        run_config=RunConfig(
            workflow_name="Lattice CT Analysis Copilot",
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        ),
    )
    output = result.final_output
    if isinstance(output, CopilotResponse):
        return output.model_dump(mode="json")
    return CopilotResponse(
        answer=str(output),
        warnings=["Agent output did not match the expected structured schema."],
        status="schema_fallback",
    ).model_dump(mode="json")
