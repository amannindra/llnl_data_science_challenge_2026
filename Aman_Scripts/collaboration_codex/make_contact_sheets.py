#!/usr/bin/env python3
"""Build six lightweight contact sheets for visual review of all 120 panels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Aman_Scripts.collaboration_codex.visual_audit import create_contact_sheets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--handoff-root",
        type=Path,
        default=Path("collaboration/part2_verification_handoff_20260727"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("Aman_Scripts/collaboration_codex/audit_outputs/contact_sheets"),
    )
    args = parser.parse_args()
    outputs = create_contact_sheets(args.handoff_root.resolve(), args.output_dir.resolve())
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

