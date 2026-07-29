"""Mocked/no-network tests for the three-agent manager topology."""

from __future__ import annotations

from defect_cartographer.agents import build_copilot, copilot_status, run_copilot


def test_three_agent_topology_builds_without_api_call(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bundle = build_copilot(model="test-model")

    assert bundle.model == "test-model"
    assert bundle.coordinator.name == "Analysis Coordinator"
    assert bundle.analysis_specialist.name == "Measurement and QA Sub-agent"
    assert (
        bundle.visualization_specialist.name
        == "Visualization and Reporting Sub-agent"
    )
    assert {tool.name for tool in bundle.coordinator.tools} == {
        "ask_measurement_qa_subagent",
        "ask_visualization_reporting_subagent",
    }
    assert "get_strut_details" in {
        tool.name for tool in bundle.analysis_specialist.tools
    }
    assert "prepare_threejs_scene" in {
        tool.name for tool in bundle.visualization_specialist.tools
    }


def test_missing_key_returns_graceful_disabled_response(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    status = copilot_status()
    response = run_copilot("How many missing candidates are there?")

    assert status["available"] is False
    assert response["status"] == "disabled_no_api_key"
    assert "disabled" in response["answer"].lower()
    assert "No external API call was attempted." in response["warnings"]
