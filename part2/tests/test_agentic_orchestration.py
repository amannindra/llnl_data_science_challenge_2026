"""Focused persistence and restart tests for the Aman-only runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from defect_cartographer.agentic_orchestration import (
    AmanOrchestratorRuntime,
    PathContainmentError,
    RunCancelled,
    RunStore,
    StageResult,
    StageStatus,
    TransitionError,
)


def make_store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs.sqlite3", tmp_path / "artifacts")


def test_stage_state_machine_rejects_invalid_transitions(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["segment"])
    store.transition("r1", "segment", StageStatus.RUNNING)
    store.transition("r1", "segment", StageStatus.SUCCEEDED)
    with pytest.raises(TransitionError):
        store.transition("r1", "segment", StageStatus.RUNNING)


def test_artifact_registration_and_validation_are_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["segment"])
    artifact = store.artifact_root / "result.txt"
    artifact.write_text("stable", encoding="utf-8")
    first = store.register_artifact("r1", "segment", "result", artifact)
    second = store.register_artifact("r1", "segment", "result", artifact)
    assert first == second
    assert store.validate_artifact("r1", "segment", "result")
    artifact.write_text("changed", encoding="utf-8")
    assert not store.validate_artifact("r1", "segment", "result")
    with pytest.raises(ValueError, match="identity changed"):
        store.register_artifact("r1", "segment", "result", artifact)


def test_runtime_recovers_failed_stage_after_restart(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["first", "second"])
    calls: list[str] = []
    attempts = {"first": 0}

    def first(ctx):
        calls.append(ctx.stage_name)
        attempts["first"] += 1
        if attempts["first"] == 1:
            raise RuntimeError("temporary failure")

    def second(ctx):
        calls.append(ctx.stage_name)

    runtime = AmanOrchestratorRuntime(store, {"first": first, "second": second})
    with pytest.raises(RuntimeError):
        runtime.run("r1")
    assert store.stage_status("r1", "first") == StageStatus.FAILED
    AmanOrchestratorRuntime(store, {"first": first, "second": second}).run("r1")
    assert calls == ["first", "first", "second"]
    assert [row["status"] for row in store.stages("r1")] == ["succeeded", "succeeded"]
    assert store.get_run("r1").status == "succeeded"


def test_cancellation_prevents_pending_callback(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["first", "second"])
    store.cancel_run("r1", "operator requested stop")
    called = []
    with pytest.raises(RunCancelled):
        AmanOrchestratorRuntime(store, {"first": lambda _: called.append("first")}).run("r1")
    assert called == []
    assert all(row["status"] == StageStatus.CANCELLED for row in store.stages("r1"))


def test_artifact_path_containment_rejects_escape(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["segment"])
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    with pytest.raises(PathContainmentError):
        store.register_artifact("r1", "segment", "outside", outside)


def test_wal_mode_and_events_are_persisted(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_run("r1", ["segment"])
    with store._connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert any(event["kind"] == "run_created" for event in store.events("r1"))
