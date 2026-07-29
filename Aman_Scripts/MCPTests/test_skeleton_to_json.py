#!/usr/bin/env python3
"""Focused and live-MCP checks for skeleton-to-JSON export."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from pathlib import Path

import numpy as np
from fastmcp import Client


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "Aman_src" / "mcp_server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("aman_mcp_skeleton_json_test", SERVER)
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


async def main() -> int:
    module = load_server()
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="dssi_mcp_skeleton_json_") as temporary:
        root = Path(temporary)
        skeleton = np.zeros((3, 4, 5), dtype=np.float32)
        skeleton[0, 1, 2] = 1.0  # ZYX -> XYZ [2, 1, 0]
        skeleton[2, 3, 4] = 1.0  # ZYX -> XYZ [4, 3, 2]
        skeleton[1, 1, 1] = np.nan
        source = root / "skeleton.npy"
        np.save(source, skeleton)
        source_before = source.read_bytes()

        output = root / "nested" / "skeleton"
        response = module.skeleton_to_json(str(source), str(output))
        saved = Path(f"{output}.json")
        checks.check("skeleton JSON is written", response.startswith("Saved skeleton JSON"), response)
        checks.check("missing JSON suffix is appended", saved.is_file())
        document = json.loads(saved.read_text(encoding="utf-8"))
        checks.check("schema identifies voxel export", document["schema_version"] == "skeleton-voxels.v1")
        checks.check("source ZYX shape is retained", document["source"]["shape_zyx"] == [3, 4, 5])
        checks.check("coordinates are explicitly XYZ", document["coordinate_order"] == "xyz")
        checks.check("ZYX indices are converted to XYZ",
                     document["voxel_coordinates_xyz"] == [[2, 1, 0], [4, 3, 2]],
                     repr(document["voxel_coordinates_xyz"]))
        checks.check("NaN skeleton values are excluded", document["skeleton_voxel_count"] == 2)
        checks.check("input array remains unchanged", source.read_bytes() == source_before)
        checks.check("output hash is reported", "sha256=" in response, response)

        checks.check("missing skeleton returns Error",
                     module.skeleton_to_json(str(root / "missing.npy"), str(output)).startswith("Error:"))
        checks.check("non-NPY source returns Error",
                     module.skeleton_to_json(str(root / "wrong.json"), str(output)).startswith("Error:"))
        two_dimensional = root / "two_dimensional.npy"
        np.save(two_dimensional, np.zeros((3, 4), dtype=np.uint8))
        checks.check("non-3D skeleton returns Error",
                     module.skeleton_to_json(str(two_dimensional), str(output)).startswith("Error:"))
        checks.check("voxel limit returns Error",
                     module.skeleton_to_json(str(source), str(output), max_voxels=1).startswith("Error:"))

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            checks.check("skeleton_to_json is registered", "skeleton_to_json" in names, str(sorted(names)))
            result = await client.call_tool(
                "skeleton_to_json",
                {"input_filepath": str(source), "output_filepath": str(root / "live.json")},
            )
            checks.check("live MCP export succeeds",
                         "Saved skeleton JSON" in result_text(result) and (root / "live.json").is_file(),
                         result_text(result))

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} skeleton-JSON checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
