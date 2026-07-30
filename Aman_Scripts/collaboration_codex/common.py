"""Shared result models and small, deterministic file helpers."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Finding:
    """One inspectable audit result."""

    check_id: str
    status: str
    message: str
    severity: str = "info"
    path: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditReport:
    """Collect findings without stopping at the first failure."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(
        self,
        check_id: str,
        status: str,
        message: str,
        *,
        severity: str = "info",
        path: Path | str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        if status not in {"pass", "warn", "fail"}:
            raise ValueError(f"Unsupported status: {status}")
        self.findings.append(
            Finding(
                check_id=check_id,
                status=status,
                message=message,
                severity=severity,
                path=str(path) if path is not None else None,
                evidence=evidence or {},
            )
        )

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def counts(self) -> dict[str, int]:
        return {
            status: sum(item.status == status for item in self.findings)
            for status in ("pass", "warn", "fail")
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "findings": [item.to_dict() for item in self.findings],
        }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file incrementally so large artifacts never enter memory at once."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV with strict row-width checking and normalized empty values."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV has duplicate header names")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"CSV row {index} has more values than headers")
        if any(value is None for value in row.values()):
            raise ValueError(f"CSV row {index} has fewer values than headers")
    return list(reader.fieldnames), rows


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def relative_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

