#!/usr/bin/env python3
"""Run component tests in fixed fail-fast order and persist a compact report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.reporting import write_json  # noqa: E402
from Components.paths import output_path  # noqa: E402


TESTS = (
    "test_paths.py",
    "test_asset_io.py",
    "test_real_assets.py",
    "test_coordinates.py",
    "test_lattice_graph.py",
    "test_lattice_stl.py",
    "test_segmentation.py",
    "test_tiff_mesh.py",
    "test_tif2stl.py",
    "test_legacy_occupancy.py",
    "test_reporting.py",
    "test_testing.py",
    "test_cli_compatibility.py",
)


def _structured_summary(output: str) -> dict[str, object] | None:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("total"), int):
            return value
    return None


def _counts(output: str) -> tuple[int | None, int | None]:
    structured = _structured_summary(output)
    if structured is not None:
        return int(structured.get("passed", 0)), int(structured["total"])
    matches = re.findall(r"(\d+)/(\d+) [^\n]*checks passed", output)
    return tuple(map(int, matches[-1])) if matches else (None, None)


def _stable_summary(summary: dict[str, object] | None) -> dict[str, object] | None:
    """Remove volatile fixture paths while preserving inspectable check evidence."""

    if summary is None:
        return None
    stable = {
        key: summary[key]
        for key in ("suite", "passed", "failed", "total", "minimum_satisfied")
        if key in summary
    }
    results = summary.get("results")
    if isinstance(results, list):
        stable["results"] = [
            {"name": item.get("name"), "passed": item.get("passed")}
            for item in results if isinstance(item, dict)
        ]
    return stable


def run(output_directory: Path, *, allow_missing: bool = False) -> int:
    records = []
    for name in TESTS:
        path = Path(__file__).resolve().parent / name
        if not path.is_file():
            record = {"test": name, "status": "missing", "passed": None, "total": None}
            records.append(record)
            print(f"[MISSING] {name}")
            if not allow_missing:
                break
            continue
        print(f"\nRUN {name}")
        try:
            process = subprocess.run(
                [sys.executable, str(path)], cwd=ROOT, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            records.append({"test": name, "status": "timeout", "passed": None, "total": None})
            print(f"[TIMEOUT] {name}: {exc}", file=sys.stderr)
            break
        print(process.stdout, end="")
        if process.stderr:
            print(process.stderr, file=sys.stderr, end="")
        passed, total = _counts(process.stdout)
        structured = _structured_summary(process.stdout)
        valid_summary = (
            structured is not None
            and passed is not None and total is not None and total >= 10 and passed == total
            and int(structured.get("failed", 0)) == 0
            and bool(structured.get("minimum_satisfied", True))
        )
        status = "passed" if process.returncode == 0 and valid_summary else "failed"
        records.append({
            "test": name, "status": status, "passed": passed, "total": total,
            "summary": _stable_summary(structured),
        })
        if status != "passed":
            break

    expected_complete = len(records) == len(TESTS)
    success = expected_complete and all(record["status"] == "passed" for record in records)
    total_checks = sum(record["total"] or 0 for record in records)
    passed_checks = sum(record["passed"] or 0 for record in records)
    summary = {
        "suite": "Scripts component validation",
        "expected_tests": list(TESTS),
        "tests_run": len(records),
        "success": success,
        "checks_passed": passed_checks,
        "checks_total": total_checks,
        "tests": records,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    write_json(output_directory / "component_test_summary.json", summary)
    markdown = [
        "# Component validation", "",
        f"Overall: **{'PASS' if success else 'FAIL'}**", "",
        f"Checks: {passed_checks}/{total_checks}", "",
        "| Test | Status | Checks |", "| --- | --- | ---: |",
    ]
    markdown.extend(
        f"| `{record['test']}` | {record['status']} | {record['passed']}/{record['total']} |"
        for record in records
    )
    (output_directory / "component_test_summary.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    print(f"\nCOMPONENT TOTAL: {passed_checks}/{total_checks} checks; {'PASS' if success else 'FAIL'}")
    print(f"Summary: {output_directory / 'component_test_summary.json'}")
    allowed_incomplete = (
        allow_missing
        and all(record["status"] in {"passed", "missing"} for record in records)
    )
    return 0 if success or allowed_incomplete else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=output_path("component_validation", root=ROOT),
    )
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    return run(args.output_dir.resolve(strict=False), allow_missing=args.allow_missing)


if __name__ == "__main__":
    raise SystemExit(main())
