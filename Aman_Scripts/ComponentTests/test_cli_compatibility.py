#!/usr/bin/env python3
"""Adversarial import-safety and CLI-compatibility checks for root utilities."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "Scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULES = (
    "analyze_json",
    "analyze_npy",
    "analyze_project_assets",
    "analyze_tiff_stl",
    "create_pdf_contacts",
    "find_missing_points",
    "view_tif_napari",
)
HELP_CLIS = ("analyze_json", "analyze_npy", "find_missing_points", "view_tif_napari")


class Checker:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: object, detail: str = "") -> None:
        passed = bool(condition)
        self.results.append({"name": name, "passed": passed, "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    def finish(self) -> int:
        passed = sum(bool(result["passed"]) for result in self.results)
        summary = {
            "suite": "cli_compatibility",
            "total": len(self.results),
            "passed": passed,
            "failed": len(self.results) - passed,
            "results": self.results,
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if passed == len(self.results) and len(self.results) >= 10 else 1


def _tree_snapshot(directory: Path) -> dict[str, tuple[int, str]]:
    if not directory.exists():
        return {}
    snapshot = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot[str(path.relative_to(directory))] = (path.stat().st_size, digest)
    return snapshot


def _run(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
    )


def main() -> int:
    check = Checker()
    watched = (SCRIPTS / "outputs", SCRIPTS / "analysis_output")
    before = tuple(_tree_snapshot(path) for path in watched)

    for module in MODULES:
        command = (
            "import importlib; "
            f"m=importlib.import_module('Scripts.{module}'); "
            "assert callable(m.main)"
        )
        result = _run("-c", command)
        check.check(f"{module} imports successfully", result.returncode == 0, result.stderr.strip())
        check.check(f"{module} import is stdout-silent", result.stdout == "", result.stdout.strip())
        check.check(f"{module} import is stderr-silent", result.stderr == "", result.stderr.strip())

    after = tuple(_tree_snapshot(path) for path in watched)
    check.check("imports do not create or modify established artifacts", before == after)

    for cli in HELP_CLIS:
        result = _run(str(SCRIPTS / f"{cli}.py"), "--help")
        check.check(f"{cli} --help exits successfully", result.returncode == 0, result.stderr.strip())
        check.check(f"{cli} --help contains usage", "usage:" in result.stdout.lower())

    line_counts = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in sorted(SCRIPTS.glob("*.py"))
    }
    check.check(
        "no root production script exceeds 1,000 lines",
        max(line_counts.values(), default=0) < 1000,
        str(line_counts),
    )

    from Scripts.analyze_npy import extract_isosurface_xyz

    asymmetric = np.zeros((8, 10, 12), dtype=np.float32)
    asymmetric[2:6, 2:8, 4:10] = 1
    vertices_xyz, faces = extract_isosurface_xyz(asymmetric)
    check.check("isosurface extraction produces a nonempty mesh", len(vertices_xyz) > 0 and len(faces) > 0)
    check.check(
        "isosurface vertices are converted from array ZYX to geometry XYZ",
        np.allclose(vertices_xyz.min(axis=0), [1.5, 0.5, 0.5])
        and np.allclose(vertices_xyz.max(axis=0), [4.5, 3.5, 2.5]),
        f"bbox={vertices_xyz.min(0)}->{vertices_xyz.max(0)}",
    )

    legacy_help = _run(str(SCRIPTS / "analyze_json.py"), "--help")
    normalized_legacy_help = " ".join(legacy_help.stdout.lower().split())
    check.check(
        "legacy occupancy path is visibly marked and opt-in",
        "legacy" in normalized_legacy_help
        and "unvalidated" in normalized_legacy_help
        and "not defect ground truth" in normalized_legacy_help
        and "run-legacy-occupancy" in legacy_help.stdout,
    )

    with tempfile.TemporaryDirectory(prefix="dssi_cli_compat_") as temporary:
        temporary_path = Path(temporary)
        graph_output = temporary_path / "graph_outputs"
        graph_run = _run(
            str(SCRIPTS / "analyze_json.py"),
            "--skip-wireframes", "--skip-overlay", "--output-dir", str(graph_output),
        )
        check.check("graph CLI real-data smoke exits successfully", graph_run.returncode == 0, graph_run.stderr.strip())
        check.check("graph CLI reports welded physical topology", "welded" in graph_run.stdout.lower())
        check.check("graph CLI reports recovered registration", "scale" in graph_run.stdout.lower())

        volume = np.linspace(-1, 1, 9 * 8 * 7, dtype=np.float32).reshape(9, 8, 7)
        source = temporary_path / "fixture.npy"
        np.save(source, volume)
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        npy_output = temporary_path / "npy_outputs"
        npy_run = _run(
            str(SCRIPTS / "analyze_npy.py"), "--input", str(source),
            "--output-dir", str(npy_output), "--skip-isosurface",
        )
        check.check("NPY CLI synthetic smoke exits successfully", npy_run.returncode == 0, npy_run.stderr.strip())
        check.check("NPY CLI writes historical histogram name", (npy_output / "npy_histogram.png").stat().st_size > 0)
        check.check("NPY CLI writes historical center-slice name", (npy_output / "npy_center_slices.png").stat().st_size > 0)
        check.check("NPY CLI does not mutate its input", hashlib.sha256(source.read_bytes()).hexdigest() == source_digest)

    return check.finish()


if __name__ == "__main__":
    raise SystemExit(main())
