#!/usr/bin/env python3
"""Validate the generated end-to-end Markdown guide and its local links."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Aman_Scripts.collaboration_codex.build_end_to_end import (
    AUDIT_SCRIPTS,
    DOCUMENTED_MODULES,
    DOCUMENTED_TESTS,
    FILE_DESCRIPTIONS,
)


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PANEL_HEADING = re.compile(r"^### Panel \d{3}:", re.MULTILINE)


def audit_report_file(report_path: Path, audit_report_path: Path) -> dict:
    text = report_path.read_text(encoding="utf-8")
    audit = json.loads(audit_report_path.read_text(encoding="utf-8"))
    counts = audit["counts"]

    missing_links: list[str] = []
    for target in MARKDOWN_LINK.findall(text):
        target = target.strip()
        if target.startswith(("http://", "https://", "#")):
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        if not (report_path.parent / target).resolve().exists():
            missing_links.append(target)

    missing_packet_entries = [
        path for path in FILE_DESCRIPTIONS if f"### `{path}`" not in text
    ]
    missing_modules = [
        path for path, _ in DOCUMENTED_MODULES if f"### `{path}`" not in text
    ]
    missing_tests = [
        path
        for path, _ in DOCUMENTED_TESTS
        if f"### `tests/part2/{path}`" not in text
    ]
    missing_audit_scripts = [
        path for path, _ in AUDIT_SCRIPTS if f"### `{path}`" not in text
    ]
    panel_headings = len(PANEL_HEADING.findall(text))
    panel_links = text.count("[Open panel](")
    audit_count_line = (
        f"**{sum(counts.values())} consolidated checks:** {counts['pass']} passed, "
        f"{counts['warn']} warned, and {counts['fail']} failed."
    )
    required_sections = [
        "## Executive verdict",
        "## End-to-end pipeline",
        "## Documented production scripts (source absent)",
        "## Documented original tests (also absent)",
        "## How to use what is available now",
        "## Audit scripts added in `Aman_Scripts/collaboration_codex`",
        "## Errors and improvements, in priority order",
        "## Simple high-level explanation",
        "## File-by-file catalog: all 120 CT review panels",
    ]
    missing_sections = [section for section in required_sections if section not in text]
    required_coverage_ids = {
        "E_N008309_N008313",
        "E_N009317_N009321",
        "E_N009443_N009447",
        "E_N001379_N001506",
    }
    missing_coverage_ids = sorted(edge for edge in required_coverage_ids if edge not in text)

    checks = {
        "all_local_links_resolve": not missing_links,
        "all_56_nonpanel_files_cataloged": not missing_packet_entries
        and len(FILE_DESCRIPTIONS) == 56,
        "all_120_panels_cataloged": panel_headings == 120 and panel_links == 120,
        "all_documented_modules_cataloged": not missing_modules
        and len(DOCUMENTED_MODULES) == 32,
        "all_documented_tests_cataloged": not missing_tests
        and len(DOCUMENTED_TESTS) == 16,
        "all_audit_scripts_explained": not missing_audit_scripts
        and len(AUDIT_SCRIPTS) == 16,
        "audit_counts_current": audit_count_line in text,
        "coverage_failures_named": not missing_coverage_ids,
        "required_sections_present": not missing_sections,
        "no_paste_placeholder": "[Pasted Content" not in text,
        "candidate_not_ground_truth_guardrail": "not full ground truth" in text
        and "candidate fraction" in text,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "evidence": {
            "missing_links": missing_links,
            "missing_packet_entries": missing_packet_entries,
            "panel_heading_count": panel_headings,
            "panel_link_count": panel_links,
            "missing_modules": missing_modules,
            "missing_tests": missing_tests,
            "missing_audit_scripts": missing_audit_scripts,
            "missing_sections": missing_sections,
            "missing_coverage_ids": missing_coverage_ids,
            "line_count": len(text.splitlines()),
            "word_count": len(text.split()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("Aman_Scripts/collaboration_codex/end-2-end.md"),
    )
    parser.add_argument(
        "--audit-report",
        type=Path,
        default=Path(
            "Aman_Scripts/collaboration_codex/audit_outputs/audit_report.json"
        ),
    )
    args = parser.parse_args()
    result = audit_report_file(args.report.resolve(), args.audit_report.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
