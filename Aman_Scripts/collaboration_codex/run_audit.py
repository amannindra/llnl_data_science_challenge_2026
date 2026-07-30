#!/usr/bin/env python3
"""Run the complete collaboration-handoff audit and save inspectable evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Aman_Scripts.collaboration_codex.common import AuditReport
from Aman_Scripts.collaboration_codex.coverage_audit import run_coverage_audit
from Aman_Scripts.collaboration_codex.file_audit import run_file_audit
from Aman_Scripts.collaboration_codex.provenance_audit import run_provenance_audit
from Aman_Scripts.collaboration_codex.scientific_audit import run_scientific_audit
from Aman_Scripts.collaboration_codex.table_audit import run_table_audit
from Aman_Scripts.collaboration_codex.viewer_audit import run_viewer_audit
from Aman_Scripts.collaboration_codex.visual_audit import (
    create_contact_sheets,
    run_visual_audit,
    write_image_inventory,
)


DEFAULT_HANDOFF = Path("collaboration/part2_verification_handoff_20260727")
DEFAULT_OUTPUT = Path("Aman_Scripts/collaboration_codex/audit_outputs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-root", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-contact-sheets", action="store_true")
    return parser.parse_args()


def write_file_inventory(records: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "suffix", "size_bytes", "sha256"])
        writer.writeheader()
        writer.writerows(records)


def write_markdown_summary(report: AuditReport, path: Path) -> None:
    counts = report.counts()
    lines = [
        "# Collaboration Handoff Automated Audit",
        "",
        f"Results: **{counts['pass']} passed, {counts['warn']} warnings, {counts['fail']} failures**.",
        "",
        "This report validates packet integrity and internal consistency. It does not replace human CT review or recreate the absent production source code.",
        "",
        "## Findings",
        "",
    ]
    for item in report.findings:
        location = f" (`{item.path}`)" if item.path else ""
        lines.extend(
            [
                f"### {item.status.upper()} — {item.check_id}{location}",
                "",
                item.message,
                "",
                f"Severity: `{item.severity}`.",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    handoff_root = (repo_root / args.handoff_root).resolve() if not args.handoff_root.is_absolute() else args.handoff_root.resolve()
    output_dir = (repo_root / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve()
    if not handoff_root.is_dir():
        raise SystemExit(f"Handoff directory does not exist: {handoff_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    report = AuditReport()
    file_inventory = run_file_audit(handoff_root, repo_root, report)
    run_table_audit(handoff_root, report)
    run_provenance_audit(handoff_root, repo_root, report)
    run_scientific_audit(handoff_root, repo_root, report)
    run_coverage_audit(handoff_root, repo_root, report)
    run_viewer_audit(handoff_root, report)
    image_inventory = run_visual_audit(handoff_root, report)

    contact_sheets: list[Path] = []
    if not args.skip_contact_sheets:
        contact_sheets = create_contact_sheets(handoff_root, output_dir / "contact_sheets")

    write_file_inventory(file_inventory, output_dir / "file_inventory.csv")
    write_image_inventory(image_inventory, output_dir / "image_inventory.csv")
    payload = report.to_dict()
    payload["handoff_root"] = str(handoff_root)
    payload["file_count"] = len(file_inventory)
    payload["image_count"] = len(image_inventory)
    payload["contact_sheets"] = [str(path) for path in contact_sheets]
    (output_dir / "audit_report.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown_summary(report, output_dir / "audit_summary.md")

    counts = report.counts()
    print(
        json.dumps(
            {
                "pass": counts["pass"],
                "warn": counts["warn"],
                "fail": counts["fail"],
                "file_count": len(file_inventory),
                "image_count": len(image_inventory),
                "output_dir": str(output_dir),
            },
            indent=2,
        )
    )
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
