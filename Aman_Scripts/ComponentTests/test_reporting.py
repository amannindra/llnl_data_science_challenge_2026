#!/usr/bin/env python3
"""Adversarial checks for deterministic report writing."""

from __future__ import annotations

import csv
import json
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from _harness import Checker
from Components.reporting import (
    atomic_write_bytes,
    build_manifest,
    canonical_json_bytes,
    file_sha256,
    json_safe,
    write_csv,
    write_json,
    write_json_lines,
)


@dataclass
class Fixture:
    count: int
    path: Path


def main() -> int:
    check = Checker("reporting", minimum_checks=10)
    with tempfile.TemporaryDirectory(prefix="dssi_reporting_") as temporary:
        root = Path(temporary)
        converted = json_safe({"array": np.array([1, 2]), "scalar": np.int64(3), "record": Fixture(4, Path("x"))})
        check.equal("NumPy array becomes JSON list", converted["array"], [1, 2])
        check.equal("NumPy scalar becomes Python scalar", converted["scalar"], 3)
        check.equal("dataclass becomes mapping", converted["record"]["count"], 4)
        check.equal("Path becomes string", converted["record"]["path"], "x")
        check.raises("nonfinite JSON rejected", ValueError, json_safe, float("nan"))
        check.raises("unknown JSON type rejected", TypeError, json_safe, object())
        check.raises(
            "JSON key collisions are rejected", ValueError, json_safe,
            {1: "integer", "1": "string"},
        )

        first = canonical_json_bytes({"b": 2, "a": 1})
        second = canonical_json_bytes({"a": 1, "b": 2})
        check.equal("canonical JSON ignores mapping insertion order", first, second)
        check.check("canonical JSON has one trailing newline", first.endswith(b"\n") and not first.endswith(b"\n\n"))

        binary = atomic_write_bytes(root / "nested" / "value.bin", b"abc", create_parents=True)
        check.equal("atomic writer preserves bytes", binary.read_bytes(), b"abc")
        check.equal("new atomic report uses readable file mode",
                    stat.S_IMODE(binary.stat().st_mode), 0o644)
        check.check("atomic writer leaves no temporary sibling", not list(binary.parent.glob("*.tmp")))
        binary.chmod(0o620)
        atomic_write_bytes(binary, b"replacement")
        check.equal("atomic replacement overwrites complete file", binary.read_bytes(), b"replacement")
        check.equal("atomic replacement preserves existing file mode",
                    stat.S_IMODE(binary.stat().st_mode), 0o620)
        check.raises("missing parent rejected by default", FileNotFoundError, atomic_write_bytes, root / "gone" / "x", b"x")

        json_path = write_json(root / "report.json", {"z": 1, "a": np.float32(2.5)})
        check.equal("written JSON round-trips", json.loads(json_path.read_text()), {"a": 2.5, "z": 1})
        check.check("pretty JSON keys are sorted", json_path.read_text().index('"a"') < json_path.read_text().index('"z"'))
        check.raises("negative JSON indent rejected", ValueError, write_json, root / "bad.json", {}, indent=-1)

        lines_path = write_json_lines(root / "rows.jsonl", [{"i": 1}, {"i": 2}])
        check.equal("JSONL writes exactly two records", len(lines_path.read_text().splitlines()), 2)
        check.equal("JSONL second record round-trips", json.loads(lines_path.read_text().splitlines()[1]), {"i": 2})

        csv_path = write_csv(root / "rows.csv", [{"b": 2, "a": 1}], ("a", "b"))
        with csv_path.open(newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        check.equal("CSV preserves requested field order", csv_path.read_text().splitlines()[0], "a,b")
        check.equal("CSV row round-trips", csv_rows, [{"a": "1", "b": "2"}])
        check.raises("duplicate CSV fields rejected", ValueError, write_csv, root / "bad.csv", [], ("a", "a"))
        check.raises(
            "CSV extra columns are rejected", ValueError, write_csv,
            root / "extra.csv", [{"a": 1, "b": 2, "typo": 3}], ("a", "b"),
        )
        check.raises(
            "CSV missing columns are rejected", ValueError, write_csv,
            root / "missing.csv", [{"a": 1}], ("a", "b"),
        )

        hello = root / "hello.txt"
        hello.write_bytes(b"hello")
        check.equal("streamed SHA-256 matches known vector", file_sha256(hello), "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        check.equal("SHA-256 independent of block size", file_sha256(hello, block_size=1), file_sha256(hello, block_size=8))
        check.raises("nonpositive hash block rejected", ValueError, file_sha256, hello, block_size=0)
        manifest = build_manifest((hello, json_path), root=root)
        check.equal("manifest is path sorted", [row["path"] for row in manifest], sorted(row["path"] for row in manifest))
        check.check("manifest includes size and SHA", all(row["bytes"] > 0 and len(row["sha256"]) == 64 for row in manifest))
    return check.done()


if __name__ == "__main__":
    raise SystemExit(main())
