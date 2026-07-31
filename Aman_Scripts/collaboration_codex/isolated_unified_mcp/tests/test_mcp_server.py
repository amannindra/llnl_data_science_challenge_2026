from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


SERVER = Path(__file__).parents[1] / "mcp_server.py"


@pytest.fixture(scope="module")
def server():
    spec = importlib.util.spec_from_file_location("isolated_unified_mcp_under_test", SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tool_discovery_has_dashboard_lifecycle_and_single_raw_namespace(server):
    names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    expected = {
        "get_pipeline_summary", "get_strut_details", "filter_defect_candidates",
        "compare_defect_groups", "get_methodology", "prepare_threejs_scene",
        "get_strut_ct_evidence", "agentic_create_run", "agentic_start_run",
        "agentic_get_run_status", "agentic_resume_run", "agentic_cancel_run",
        "agentic_list_run_artifacts", "agentic_ask",
    }
    assert expected <= names
    assert "raw_ct" not in names
    assert not any(name.startswith("raw_ct_raw_ct") for name in names)
    assert any(name.startswith("raw_ct_") for name in names)


def test_lifecycle_outputs_are_contained(server, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_RUNS_ROOT", tmp_path.resolve())
    created = server.agentic_create_run("focused test")
    run_dir = tmp_path / created["run_id"]
    assert Path(created["output_dir"]).resolve() == run_dir.resolve()
    server.agentic_ask(created["run_id"], "What evidence is available?")
    assert (run_dir / "questions.jsonl").is_file()
    with pytest.raises(ValueError, match="inside"):
        server._contained_path(run_dir, "../escape.txt")
    listed = server.agentic_list_run_artifacts(created["run_id"])
    assert listed["artifacts"] == ["questions.jsonl", "run.json"]


def test_lifecycle_transitions_and_json_state(server, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_RUNS_ROOT", tmp_path.resolve())
    run_id = server.agentic_create_run()["run_id"]
    assert server.agentic_start_run(run_id)["status"] == "running"
    assert server.agentic_resume_run(run_id)["status"] == "running"
    cancelled = server.agentic_cancel_run(run_id, "test stop")
    assert cancelled["status"] == "cancelled"
    assert json.loads((tmp_path / run_id / "run.json").read_text())["reason"] == "test stop"
