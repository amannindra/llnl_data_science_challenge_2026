#!/usr/bin/env python3
"""Focused and live-MCP checks for octet-lattice JSON comparison."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from pathlib import Path

from fastmcp import Client


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "Aman_src" / "mcp_server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("aman_mcp_octet_compare_test", SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load MCP server")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result_text(result) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    return next((getattr(block, "text", "") for block in getattr(result, "content", []) or []), str(result))


class Checks:
    def __init__(self):
        self.passed = self.failed = 0

    def check(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}: {detail}")


def lattice(*, position_2=(1.0, 0.0, 0.0), endpoint_1=2, thickness=0.2):
    return {
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0], "indices": [0, 0, 0]},
            {"id": 1, "position": list(position_2), "indices": [1, 0, 0]},
            {"id": 2, "position": [0.0, 1.0, 0.0], "indices": [0, 1, 0]},
        ],
        "struts": [
            {"id": 10, "junction0": 0, "junction1": endpoint_1, "thickness": thickness,
             "unit_cell_edge_idx": 0},
        ],
        "unit_cells": [{"id": 0, "struts": [10], "indices": [0, 0, 0]}],
    }


async def main() -> int:
    module = load_server()
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="dssi_mcp_octet_compare_") as temporary:
        root = Path(temporary)
        left, right = root / "left.json", root / "right.json"
        left.write_text(json.dumps(lattice()), encoding="utf-8")
        right.write_text(json.dumps(lattice(position_2=(1.1, 0, 0), endpoint_1=1, thickness=0.3)), encoding="utf-8")

        output = root / "nested" / "comparison"
        response = module.compare_octet_json(str(left), str(right), str(output))
        saved = Path(f"{output}.json")
        checks.check("comparison report is written", response.startswith("Saved octet JSON comparison"), response)
        checks.check("missing JSON suffix is appended", saved.is_file())
        report = json.loads(saved.read_text(encoding="utf-8"))
        checks.check("report uses octet comparison schema", report["schema_version"] == "octet-lattice-json-comparison.v1")
        checks.check("shared node IDs are counted", report["junctions"]["shared_id_count"] == 3)
        checks.check("XYZ node position mismatch is recorded", report["junctions"]["position_mismatches"]["count"] == 1)
        checks.check("undirected strut endpoint mismatch is recorded", report["struts"]["endpoint_mismatches"]["count"] == 1)
        checks.check("strut thickness mismatch is recorded", report["struts"]["thickness_mismatches"]["count"] == 1)
        checks.check("direct equality is false for modified records", report["direct_comparison_equal"] is False)
        checks.check("welded physical topology counts are reported",
                     report["welded_physical_topology"]["left"]["nodes"] == 3
                     and report["welded_physical_topology"]["right"]["struts"] == 1)
        checks.check("input checksums are recorded", len(report["inputs"]["left"]["sha256"]) == 64)

        identical = root / "identical.json"
        identical.write_text(left.read_text(encoding="utf-8"), encoding="utf-8")
        identical_response = module.compare_octet_json(str(left), str(identical), str(root / "identical_report.json"))
        checks.check("identical graphs compare equal", "direct_equal=true" in identical_response, identical_response)
        checks.check("missing JSON returns Error",
                     module.compare_octet_json(str(root / "missing.json"), str(right), str(output)).startswith("Error:"))
        checks.check("invalid input extension returns Error",
                     module.compare_octet_json(str(root / "left.txt"), str(right), str(output)).startswith("Error:"))
        checks.check("negative coordinate tolerance returns Error",
                     module.compare_octet_json(str(left), str(right), str(output), coordinate_tolerance=-1).startswith("Error:"))

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            checks.check("compare_octet_json is registered", "compare_octet_json" in names, str(sorted(names)))
            result = await client.call_tool(
                "compare_octet_json",
                {"left_filepath": str(left), "right_filepath": str(right),
                 "output_filepath": str(root / "live.json")},
            )
            checks.check("live MCP comparison succeeds",
                         "Saved octet JSON comparison" in result_text(result)
                         and (root / "live.json").is_file(), result_text(result))

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} octet-JSON comparison checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
