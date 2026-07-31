"""SQLite WAL persistence for runs, stages, events, and content-addressed artifacts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import (
    ArtifactRecord,
    PathContainmentError,
    RunRecord,
    StageStatus,
    TransitionError,
)


_ALLOWED: dict[str, set[str]] = {
    StageStatus.PENDING: {StageStatus.RUNNING, StageStatus.CANCELLED},
    StageStatus.RUNNING: {StageStatus.SUCCEEDED, StageStatus.FAILED, StageStatus.CANCELLED},
    StageStatus.FAILED: {StageStatus.RUNNING, StageStatus.CANCELLED},
    StageStatus.CANCELLED: {StageStatus.RUNNING},
    StageStatus.SUCCEEDED: set(),
}


class RunStore:
    """A small transactional store; each operation uses a short-lived connection."""

    def __init__(self, database: str | Path, artifact_root: str | Path):
        self.database = Path(database)
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stages (
                    run_id TEXT NOT NULL, stage_name TEXT NOT NULL, position INTEGER NOT NULL,
                    status TEXT NOT NULL, error TEXT, metadata TEXT NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY (run_id, stage_name), FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL,
                    sha256 TEXT NOT NULL, size INTEGER NOT NULL, created_at REAL NOT NULL,
                    UNIQUE(run_id, stage_name, name), FOREIGN KEY (run_id, stage_name)
                    REFERENCES stages(run_id, stage_name)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    stage_name TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS events_run_idx ON events(run_id, event_id);
                """
            )

    @staticmethod
    def _json(value: Mapping[str, Any] | None) -> str:
        return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))

    def create_run(self, run_id: str, stages: Iterable[str], metadata: Mapping[str, Any] | None = None) -> RunRecord:
        names = list(stages)
        if not names or len(set(names)) != len(names):
            raise ValueError("run needs unique, non-empty stage names")
        now = time.time()
        with self._connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, 0, ?, ?, ?)", (run_id, "active", self._json(metadata), now, now))
            db.executemany(
                "INSERT INTO stages VALUES (?, ?, ?, ?, NULL, ?, ?)",
                [(run_id, name, i, StageStatus.PENDING, "{}", now) for i, name in enumerate(names)],
            )
        self.event(run_id, None, "run_created", {"stages": names})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRecord(run_id, row["status"], bool(row["cancelled"]), json.loads(row["metadata"]))

    def stages(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM stages WHERE run_id = ? ORDER BY position", (run_id,)).fetchall()
        return [dict(row) | {"metadata": json.loads(row["metadata"])} for row in rows]

    def stage_status(self, run_id: str, stage_name: str) -> StageStatus:
        with self._connect() as db:
            row = db.execute("SELECT status FROM stages WHERE run_id=? AND stage_name=?", (run_id, stage_name)).fetchone()
        if row is None:
            raise KeyError((run_id, stage_name))
        return StageStatus(row["status"])

    def transition(self, run_id: str, stage_name: str, target: StageStatus, *, error: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        target = StageStatus(target)
        now = time.time()
        with self._connect() as db:
            row = db.execute("SELECT status FROM stages WHERE run_id=? AND stage_name=?", (run_id, stage_name)).fetchone()
            if row is None:
                raise KeyError((run_id, stage_name))
            current = StageStatus(row["status"])
            if target not in _ALLOWED[current]:
                raise TransitionError(f"{stage_name}: {current.value} -> {target.value} is not allowed")
            db.execute("UPDATE stages SET status=?, error=?, metadata=?, updated_at=? WHERE run_id=? AND stage_name=?", (target, error, self._json(metadata), now, run_id, stage_name))
        self.event(run_id, stage_name, "stage_transition", {"from": current.value, "to": target.value, "error": error})

    def cancel_run(self, run_id: str, reason: str = "cancelled by user") -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("UPDATE runs SET cancelled=1, status='cancelled', updated_at=? WHERE run_id=?", (now, run_id))
            db.execute("UPDATE stages SET status='cancelled', error=?, updated_at=? WHERE run_id=? AND status IN ('pending','running')", (reason, now, run_id))
        self.event(run_id, None, "run_cancelled", {"reason": reason})

    def complete_run(self, run_id: str) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("UPDATE runs SET status='succeeded', updated_at=? WHERE run_id=? AND cancelled=0", (now, run_id))
        self.event(run_id, None, "run_succeeded", {})

    def event(self, run_id: str, stage_name: str | None, kind: str, payload: Mapping[str, Any] | None = None) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO events(run_id, stage_name, kind, payload, created_at) VALUES (?, ?, ?, ?, ?)", (run_id, stage_name, kind, self._json(payload), time.time()))

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM events WHERE run_id=? ORDER BY event_id", (run_id,)).fetchall()
        return [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]

    def _contained(self, path: str | Path) -> Path:
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(self.artifact_root)
        except ValueError as exc:
            raise PathContainmentError(f"artifact escapes root: {candidate}") from exc
        return candidate

    @staticmethod
    def _sha256(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        return digest.hexdigest(), size

    def register_artifact(self, run_id: str, stage_name: str, name: str, path: str | Path) -> ArtifactRecord:
        candidate = self._contained(path)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        digest, size = self._sha256(candidate)
        now = time.time()
        with self._connect() as db:
            existing = db.execute("SELECT * FROM artifacts WHERE run_id=? AND stage_name=? AND name=?", (run_id, stage_name, name)).fetchone()
            if existing:
                if existing["path"] != str(candidate) or existing["sha256"] != digest or existing["size"] != size:
                    raise ValueError(f"artifact identity changed: {name}")
                return ArtifactRecord(existing["artifact_id"], run_id, stage_name, name, candidate, digest, size)
            cursor = db.execute("INSERT INTO artifacts(run_id,stage_name,name,path,sha256,size,created_at) VALUES (?,?,?,?,?,?,?)", (run_id, stage_name, name, str(candidate), digest, size, now))
            artifact_id = int(cursor.lastrowid)
        self.event(run_id, stage_name, "artifact_registered", {"name": name, "sha256": digest, "size": size})
        return ArtifactRecord(artifact_id, run_id, stage_name, name, candidate, digest, size)

    def validate_artifact(self, run_id: str, stage_name: str, name: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT path, sha256, size FROM artifacts WHERE run_id=? AND stage_name=? AND name=?", (run_id, stage_name, name)).fetchone()
        if row is None:
            return False
        path = self._contained(row["path"])
        if not path.is_file():
            return False
        digest, size = self._sha256(path)
        return digest == row["sha256"] and size == row["size"]

    def artifacts(self, run_id: str, stage_name: str | None = None) -> list[ArtifactRecord]:
        query = "SELECT * FROM artifacts WHERE run_id=?" + (" AND stage_name=?" if stage_name else "")
        args = (run_id, stage_name) if stage_name else (run_id,)
        with self._connect() as db:
            rows = db.execute(query, args).fetchall()
        return [ArtifactRecord(row["artifact_id"], row["run_id"], row["stage_name"], row["name"], Path(row["path"]), row["sha256"], row["size"]) for row in rows]
