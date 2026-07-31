"""Unified MCP server for the isolated experimental checkout.

This module is intentionally a new composition layer.  The existing dashboard
and raw CT servers remain untouched.  Raw CT is mounted from ``Aman_src``
directly, while the dashboard/query functions are exposed as local wrappers so
that mounting the dashboard server cannot create ``raw_ct.raw_ct``.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


_ROOT = Path(__file__).resolve().parents[3]
_PART2 = _ROOT / "part2"
_AMAN_SRC = _ROOT / "Aman_src" / "mcp_server.py"
_RUNS_ROOT = (_PART2 / "artifacts" / "runs" / "agentic").resolve()
if str(_PART2) not in sys.path:
    sys.path.insert(0, str(_PART2))

mcp = FastMCP(
    "Isolated Unified Lattice MCP",
    instructions=(
        "Experimental unified lattice MCP. Dashboard tools query saved evidence; "
        "raw CT tools are mounted once under raw_ct. Agentic runs write only inside "
        "their own run directory. Candidate labels are not validated ground truth."
    ),
)


def _load_raw_ct() -> Any:
    if not _AMAN_SRC.is_file():
        raise FileNotFoundError(f"Aman CT MCP server is missing: {_AMAN_SRC}")
    spec = importlib.util.spec_from_file_location("_isolated_aman_ct_mcp", _AMAN_SRC)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load Aman CT MCP server: {_AMAN_SRC}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# This is the only raw CT mount in this entrypoint.
_raw_ct = _load_raw_ct()
mcp.mount(_raw_ct.mcp, namespace="raw_ct")


def _dashboard_dependencies() -> tuple[Any, Any]:
    """Load dashboard dependencies without importing/mounting its MCP server."""
    from defect_cartographer.ct_evidence import render_strut_ct_evidence
    from defect_cartographer.schemas import ArtifactFilter, ThreeJSSceneRequest
    from defect_cartographer.service import DEFAULT_SERVICE

    return DEFAULT_SERVICE, render_strut_ct_evidence


@mcp.tool
def get_pipeline_summary() -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    return service.get_pipeline_summary()


@mcp.tool
def get_strut_details(strut_id: int) -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    return service.get_strut_details(strut_id)


@mcp.tool
def filter_defect_candidates(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    from defect_cartographer.schemas import ArtifactFilter

    parsed = ArtifactFilter.model_validate(filters) if filters is not None else None
    return service.filter_defect_candidates(parsed)


@mcp.tool
def compare_defect_groups(
    group_by: str = "prediction",
    metric: str = "count",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    from defect_cartographer.schemas import ArtifactFilter

    parsed = ArtifactFilter.model_validate(filters) if filters is not None else None
    return service.compare_defect_groups(group_by, metric, parsed)


@mcp.tool
def get_methodology(section: str = "overview") -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    return service.get_methodology(section)


@mcp.tool
def prepare_threejs_scene(request: dict[str, Any] | None = None) -> dict[str, Any]:
    service, _ = _dashboard_dependencies()
    from defect_cartographer.schemas import ThreeJSSceneRequest

    parsed = ThreeJSSceneRequest.model_validate(request) if request is not None else None
    return service.prepare_threejs_scene(parsed)


@mcp.tool
def get_strut_ct_evidence(strut_id: int, crop_radius_voxels: int = 24) -> dict[str, Any]:
    _, render = _dashboard_dependencies()
    return render(strut_id, crop_radius_voxels=crop_radius_voxels)


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")


def _run_dir(run_id: str) -> Path:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must contain only letters, digits, '_' or '-'")
    root = _RUNS_ROOT.resolve()
    path = (root / run_id).resolve()
    if path.parent != root:
        raise ValueError("run_id resolved outside the run root")
    return path


def _contained_path(run_dir: Path, relative: str) -> Path:
    candidate = (run_dir / relative).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ValueError("artifact path must remain inside its run directory") from exc
    return candidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_orchestration() -> Any | None:
    """Return the local orchestration package, never an external repository."""
    configured = os.environ.get("AGENTIC_ORCHESTRATION_MODULE")
    names = [configured] if configured else [
        "defect_cartographer.agentic_orchestration",
        "agentic_orchestration",
        "orchestration",
    ]
    for name in names:
        if not name:
            continue
        try:
            module = importlib.import_module(name)
        except (ImportError, ModuleNotFoundError):
            continue
        if Path(getattr(module, "__file__", "")).resolve().is_relative_to(_ROOT):
            return module
    return None


def _run_store() -> Any | None:
    """Return the local durable store when the orchestration package is available."""
    package = _load_orchestration()
    store_type = getattr(package, "RunStore", None) if package is not None else None
    if store_type is None:
        return None
    root = _RUNS_ROOT.resolve()
    return store_type(root / "orchestrator.sqlite3", root)


def _orchestration_call(operation: str, run_id: str, **kwargs: Any) -> Any | None:
    """Call the optional local package using its small function-based contract."""
    package = _load_orchestration()
    operation_fn = getattr(package, operation, None) if package is not None else None
    if not callable(operation_fn):
        return None
    result = operation_fn(run_id=run_id, output_dir=str(_run_dir(run_id)), **kwargs)
    # A backend must not smuggle an output path outside the run directory.
    def check(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                check(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                check(nested)
        elif isinstance(value, str) and os.path.isabs(value):
            _contained_path(_run_dir(run_id), os.path.relpath(value, _run_dir(run_id)))
    check(result)
    return result


def _state(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id) / "run.json"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown run: {run_id}")
    state = json.loads(path.read_text(encoding="utf-8"))
    store = _run_store()
    if store is not None:
        try:
            record = store.get_run(run_id)
            state["cancelled"] = record.cancelled
            stage_rows = store.stages(run_id)
            state["stages"] = stage_rows
            if record.status == "active":
                statuses = {item["status"] for item in stage_rows}
                if "running" in statuses:
                    state["status"] = "running"
                elif statuses and statuses <= {"pending"}:
                    state["status"] = "created"
                elif statuses and statuses <= {"succeeded"}:
                    state["status"] = "succeeded"
                else:
                    state["status"] = "running"
            else:
                state["status"] = record.status
            state["events"] = store.events(run_id)
            state["registered_artifacts"] = [
                {
                    "name": item.name,
                    "stage_name": item.stage_name,
                    "path": str(item.path),
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in store.artifacts(run_id)
            ]
        except KeyError:
            pass
    return state


def _save_state(state: dict[str, Any]) -> dict[str, Any]:
    path = _run_dir(state["run_id"]) / "run.json"
    _write_json(path, state)
    return state


@mcp.tool
def agentic_create_run(name: str = "lattice-analysis", config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create an isolated run directory and persist its configuration."""
    run_id = f"{re.sub(r'[^A-Za-z0-9_-]+', '-', name).strip('-_')[:40] or 'run'}-{uuid.uuid4().hex[:12]}"
    directory = _run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=False)
    stages = (
        "validated",
        "registered",
        "segmented",
        "skeletonized",
        "measured",
        "reconciled",
        "qa",
        "reported",
    )
    store = _run_store()
    if store is not None:
        store.create_run(
            run_id,
            stages,
            {"name": name, "config": config or {}, "output_dir": str(directory)},
        )
    state = {"run_id": run_id, "name": name, "status": "created", "config": config or {}, "created_at": _now(), "updated_at": _now(), "output_dir": str(directory)}
    return _save_state(state)


def _transition(run_id: str, status: str, reason: str | None = None) -> dict[str, Any]:
    state = _state(run_id)
    store = _run_store()
    if store is not None:
        if status == "running":
            pending = [
                item for item in store.stages(run_id)
                if item["status"] in {"pending", "cancelled", "failed"}
            ]
            if pending:
                current = pending[0]
                if current["status"] == "failed":
                    store.transition(run_id, current["stage_name"], "running")
                elif current["status"] == "cancelled":
                    store.transition(run_id, current["stage_name"], "running")
                else:
                    store.transition(run_id, current["stage_name"], "running")
                store.event(run_id, current["stage_name"], "orchestrator_started", {})
        elif status == "cancelled":
            store.cancel_run(run_id, reason or "cancelled by user")
    state["status"] = status
    state["updated_at"] = _now()
    if reason:
        state["reason"] = reason
    return _save_state(state)


def _execute_configured_run(run_id: str) -> dict[str, Any]:
    """Execute deterministic Aman stages for runs that provide TIFF and JSON inputs."""
    state = _state(run_id)
    config = state.get("config") or {}
    if not config.get("tiff_filepath") or not config.get("registered_json_filepath"):
        return state
    package = _load_orchestration()
    if package is None:
        raise RuntimeError("local orchestration package is unavailable")
    store = _run_store()
    runtime_type = getattr(package, "AmanOrchestratorRuntime", None)
    callbacks_builder = getattr(package, "build_callbacks", None)
    if store is None or runtime_type is None or callbacks_builder is None:
        raise RuntimeError("durable Aman orchestration components are unavailable")
    runtime = runtime_type(store, callbacks_builder(config, _raw_ct))
    try:
        runtime.run(run_id)
    except Exception as exc:
        state["status"] = "failed"
        state["reason"] = f"{type(exc).__name__}: {exc}"
        state["updated_at"] = _now()
        _save_state(state)
        raise
    state["status"] = "succeeded"
    state["updated_at"] = _now()
    return _save_state(state)


@mcp.tool
def agentic_start_run(run_id: str, execute: bool = True) -> dict[str, Any]:
    """Start a run; configured TIFF/JSON runs execute the Aman stages synchronously."""
    _transition(run_id, "running")
    if execute:
        return _execute_configured_run(run_id)
    return _state(run_id)


@mcp.tool
def agentic_get_run_status(run_id: str) -> dict[str, Any]:
    return _state(run_id)


@mcp.tool
def agentic_resume_run(run_id: str, execute: bool = True) -> dict[str, Any]:
    """Resume unfinished stages, reusing verified artifacts where possible."""
    _transition(run_id, "running")
    if execute:
        return _execute_configured_run(run_id)
    return _state(run_id)


@mcp.tool
def agentic_cancel_run(run_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
    return _transition(run_id, "cancelled", reason)


@mcp.tool
def agentic_list_run_artifacts(run_id: str) -> dict[str, Any]:
    directory = _run_dir(run_id)
    _state(run_id)
    artifacts = [str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()]
    return {"run_id": run_id, "artifacts": sorted(artifacts)}


@mcp.tool
def agentic_ask(run_id: str, question: str) -> dict[str, Any]:
    """Record a question and optionally route it through Aman’s specialist copilot."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    state = _state(run_id)
    backend = _orchestration_call("ask", run_id, question=question.strip())
    path = _contained_path(_run_dir(run_id), "questions.jsonl")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": _now(), "question": question.strip()}) + "\n")
    result = {"run_id": run_id, "status": state["status"], "recorded": True, "artifact": "questions.jsonl"}
    try:
        from defect_cartographer.agents import run_copilot

        result["agent_response"] = run_copilot(
            question.strip(),
            page_context={"run_id": run_id, "status": state["status"], "artifacts": state.get("registered_artifacts", [])},
        )
    except (ImportError, ModuleNotFoundError, RuntimeError) as exc:
        result["agent_response"] = {
            "status": "unavailable",
            "warnings": [f"Aman specialist copilot unavailable: {exc}"],
        }
    if backend is not None:
        result["orchestration"] = backend
    return result


if __name__ == "__main__":
    mcp.run()
