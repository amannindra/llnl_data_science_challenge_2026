"""Inventory, manifest, structured-file, and source-availability checks."""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .common import AuditReport, load_json, read_csv, relative_files, sha256_file


def inventory_files(root: Path) -> list[dict[str, Any]]:
    """Return one record for every handoff file, including a fresh SHA-256."""

    records: list[dict[str, Any]] = []
    for relative in relative_files(root):
        path = root / relative
        records.append(
            {
                "path": relative.as_posix(),
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def audit_manifest(root: Path, inventory: list[dict[str, Any]], report: AuditReport) -> None:
    manifest_path = root / "MANIFEST.json"
    manifest = load_json(manifest_path)
    actual = {item["path"]: item for item in inventory}
    listed_entries = manifest.get("files", [])
    listed = {item["path"]: item for item in listed_entries}

    count_ok = manifest.get("file_count") == len(actual) == len(listed_entries)
    report.add(
        "manifest.file_count",
        "pass" if count_ok else "fail",
        "Manifest file counts reconcile." if count_ok else "Manifest file counts do not reconcile.",
        severity="critical" if not count_ok else "info",
        path=manifest_path,
        evidence={
            "declared": manifest.get("file_count"),
            "listed": len(listed_entries),
            "actual": len(actual),
        },
    )

    missing = sorted(set(listed) - set(actual))
    unlisted = sorted(set(actual) - set(listed))
    report.add(
        "manifest.coverage",
        "pass" if not missing and not unlisted else "fail",
        "Every handoff file is represented exactly once in the manifest."
        if not missing and not unlisted
        else "Manifest paths and actual paths differ.",
        severity="critical" if missing or unlisted else "info",
        path=manifest_path,
        evidence={"missing_files": missing, "unlisted_files": unlisted},
    )

    mismatches: list[dict[str, Any]] = []
    for relative in sorted(set(actual) & set(listed)):
        current = actual[relative]
        expected = listed[relative]
        if current["size_bytes"] != expected.get("size_bytes") or current["sha256"] != expected.get("sha256"):
            mismatches.append(
                {
                    "path": relative,
                    "listed_size": expected.get("size_bytes"),
                    "actual_size": current["size_bytes"],
                    "listed_sha256": expected.get("sha256"),
                    "actual_sha256": current["sha256"],
                }
            )

    nonself = [item for item in mismatches if item["path"] != "MANIFEST.json"]
    report.add(
        "manifest.nonself_integrity",
        "pass" if not nonself else "fail",
        "All non-manifest file hashes and sizes match the handoff manifest."
        if not nonself
        else "One or more non-manifest files differ from the recorded handoff.",
        severity="critical" if nonself else "info",
        path=manifest_path,
        evidence={"mismatches": nonself},
    )

    self_mismatch = [item for item in mismatches if item["path"] == "MANIFEST.json"]
    report.add(
        "manifest.self_hash",
        "warn" if self_mismatch else "pass",
        "MANIFEST.json records a stale hash/size for itself; a directly embedded self-hash cannot be stable after serialization."
        if self_mismatch
        else "The manifest self-entry matches its current bytes.",
        severity="medium" if self_mismatch else "info",
        path=manifest_path,
        evidence={"mismatches": self_mismatch},
    )

    forbidden = [
        item["path"]
        for item in inventory
        if item["suffix"] in {".tif", ".tiff", ".stl", ".npy", ".numpy"}
        or "data/missing_struts" in item["path"]
    ]
    report.add(
        "packet.raw_data_exclusion",
        "pass" if not forbidden else "fail",
        "The packet excludes raw TIFF/STL/NumPy/source-data artifacts."
        if not forbidden
        else "The packet contains artifacts prohibited by its raw-data policy.",
        severity="high" if forbidden else "info",
        evidence={"forbidden_paths": forbidden},
    )


def audit_structured_files(root: Path, report: AuditReport) -> None:
    parse_errors: list[dict[str, str]] = []
    parsed_counts: Counter[str] = Counter()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                load_json(path)
            elif suffix == ".csv":
                read_csv(path)
            elif suffix in {".yaml", ".yml"}:
                with path.open("r", encoding="utf-8") as handle:
                    yaml.safe_load(handle)
            elif suffix == ".toml":
                with path.open("rb") as handle:
                    tomllib.load(handle)
            else:
                continue
            parsed_counts[suffix] += 1
        except Exception as exc:  # keep a complete handoff error list
            parse_errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    report.add(
        "structured.parseability",
        "pass" if not parse_errors else "fail",
        "Every JSON, CSV, YAML, and TOML artifact parses successfully."
        if not parse_errors
        else "At least one structured artifact cannot be parsed.",
        severity="critical" if parse_errors else "info",
        evidence={"parsed_counts": dict(parsed_counts), "errors": parse_errors},
    )


def audit_documentation_and_source_availability(
    handoff_root: Path, repo_root: Path, report: AuditReport
) -> None:
    python_in_packet = sorted(
        str(path.relative_to(handoff_root)) for path in handoff_root.rglob("*.py")
    )
    expected_source_dirs = [repo_root / "src" / "part2", repo_root / "tests" / "part2"]
    missing_source_dirs = [str(path.relative_to(repo_root)) for path in expected_source_dirs if not path.exists()]
    report.add(
        "source.production_code_available",
        "fail" if not python_in_packet and missing_source_dirs else "pass",
        "The handoff does not contain the production/test Python implementation it documents, and those directories are absent from this worktree."
        if not python_in_packet and missing_source_dirs
        else "Referenced implementation code is locally available.",
        severity="critical" if not python_in_packet and missing_source_dirs else "info",
        evidence={
            "python_files_in_packet": python_in_packet,
            "missing_repo_directories": missing_source_dirs,
        },
    )

    haseeb_refs: list[dict[str, Any]] = []
    pattern = re.compile(r"/Users/haseebahmad(?:/[^\s`\"']+)?")
    for path in sorted(handoff_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        if matches:
            haseeb_refs.append(
                {
                    "path": str(path.relative_to(handoff_root)),
                    "occurrences": len(matches),
                    "examples": matches[:3],
                }
            )
    report.add(
        "documentation.portability",
        "warn" if haseeb_refs else "pass",
        "Some copied runbooks contain collaborator-specific absolute paths and are not directly runnable on this Mac."
        if haseeb_refs
        else "No collaborator-specific absolute paths were found in Markdown.",
        severity="medium" if haseeb_refs else "info",
        evidence={"files": haseeb_refs},
    )


def run_file_audit(root: Path, repo_root: Path, report: AuditReport) -> list[dict[str, Any]]:
    inventory = inventory_files(root)
    audit_manifest(root, inventory, report)
    audit_structured_files(root, report)
    audit_documentation_and_source_availability(root, repo_root, report)
    return inventory

