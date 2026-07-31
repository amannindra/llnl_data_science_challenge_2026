"""Small public data types for the durable orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransitionError(RuntimeError):
    """Raised when a stage state transition is not allowed."""


class PathContainmentError(ValueError):
    """Raised when an artifact is outside the configured artifact root."""


class RunCancelled(RuntimeError):
    """Raised by a runtime when cancellation is observed before a stage."""


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: int
    run_id: str
    stage_name: str
    name: str
    path: Path
    sha256: str
    size: int


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    cancelled: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageResult:
    """Callback output. Paths are resolved and registered by the runtime."""

    artifacts: tuple[Path, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageContext:
    run_id: str
    stage_name: str
    artifact_root: Path
    store: Any


StageCallback = Any
