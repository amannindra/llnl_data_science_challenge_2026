"""Persistent Aman-only runtime using injected deterministic stage callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from .models import RunCancelled, StageContext, StageResult, StageStatus
from .persistence import RunStore


class AmanOrchestratorRuntime:
    """Resume a run by skipping verified successes and retrying unfinished stages."""

    def __init__(self, store: RunStore, callbacks: Mapping[str, Callable[[StageContext], StageResult | None]]):
        self.store = store
        self.callbacks = dict(callbacks)

    def run(self, run_id: str) -> None:
        for stage in self.store.stages(run_id):
            name = stage["stage_name"]
            status = StageStatus(stage["status"])
            if status == StageStatus.SUCCEEDED:
                continue
            if self.store.get_run(run_id).cancelled:
                raise RunCancelled(run_id)
            callback = self.callbacks.get(name)
            if callback is None:
                raise KeyError(f"no deterministic callback for stage {name!r}")
            if status != StageStatus.RUNNING:
                self.store.transition(run_id, name, StageStatus.RUNNING)
            self.store.event(run_id, name, "stage_started", {})
            try:
                result = callback(StageContext(run_id, name, self.store.artifact_root, self.store))
                if result is None:
                    result = StageResult()
                if self.store.get_run(run_id).cancelled:
                    raise RunCancelled(run_id)
                for artifact in result.artifacts:
                    path = Path(artifact)
                    self.store.register_artifact(run_id, name, path.name, path)
                self.store.transition(run_id, name, StageStatus.SUCCEEDED, metadata=result.metadata)
            except RunCancelled:
                self.store.transition(run_id, name, StageStatus.CANCELLED, error="cancelled")
                raise
            except Exception as exc:
                self.store.transition(run_id, name, StageStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
                raise
        if not self.store.get_run(run_id).cancelled:
            self.store.complete_run(run_id)
