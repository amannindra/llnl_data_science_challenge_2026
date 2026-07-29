#!/usr/bin/env python3
"""Adversarial and live-MCP checks for JSON/NPY reader tools."""

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
    spec = importlib.util.spec_from_file_location("aman_mcp_readers_test", SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load MCP server")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(result) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    for block in getattr(result, "content", []) or []:
        value = getattr(block, "text", None)
        if value:
            return value
    return str(result)


class Checks:
    def __init__(self):
        self.passed = 0
        self.failed = 0

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
    with tempfile.TemporaryDirectory(prefix="dssi_mcp_readers_") as temporary:
        root = Path(temporary)
        document = {
            "name": "octet",
            "records": [{"id": 4, "position": [1.25, 2.5, 3.75]}],
            "slash/key": {"value": True},
        }
        json_path = root / "fixture.json"
        json_path.write_text(json.dumps(document), encoding="utf-8")

        whole = module.read_json(str(json_path))
        checks.check("JSON root is readable", whole.startswith("Read JSON") and '"name": "octet"' in whole, whole)
        nested = module.read_json(str(json_path), "/records/0/position")
        checks.check("JSON Pointer selects nested data", "1.25" in nested and "3.75" in nested, nested)
        escaped = module.read_json(str(json_path), "/slash~1key/value")
        checks.check("JSON Pointer escaping works", "true" in escaped, escaped)
        truncated = module.read_json(str(json_path), max_characters=8)
        checks.check("JSON output is bounded", "truncated=true" in truncated and len(truncated.splitlines()[-1]) <= 8, truncated)
        checks.check("missing JSON returns Error", module.read_json(str(root / "missing.json")).startswith("Error:"))
        checks.check("non-JSON extension returns Error", module.read_json(str(root / "fixture.txt")).startswith("Error:"))
        checks.check("bad JSON Pointer returns Error", module.read_json(str(json_path), "/missing").startswith("Error:"))
        checks.check("invalid max_characters returns Error", module.read_json(str(json_path), max_characters=0).startswith("Error:"))

        array = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
        array[0, 0, 0] = np.nan
        array[1, 2, 3] = np.inf
        npy_path = root / "volume.npy"
        np.save(npy_path, array)
        summary = module.read_npy(str(npy_path))
        checks.check("NPY metadata is reported", "shape=(2, 3, 4)" in summary and "dtype=float32" in summary, summary)
        checks.check("NPY finite statistics are reported", "finite=22/24" in summary and "nonzero=" in summary, summary)
        checks.check("NPY preview and hash are reported", "preview=" in summary and "sha256=" in summary, summary)
        checks.check("missing NPY returns Error", module.read_npy(str(root / "missing.npy")).startswith("Error:"))
        checks.check("non-NPY extension returns Error", module.read_npy(str(json_path)).startswith("Error:"))
        object_path = root / "object.npy"
        np.save(object_path, np.array([{"unsafe": True}], dtype=object), allow_pickle=True)
        checks.check("pickled/object NPY is rejected", module.read_npy(str(object_path)).startswith("Error:"))

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            checks.check("read_json is registered", "read_json" in names, str(sorted(names)))
            checks.check("read_npy is registered", "read_npy" in names, str(sorted(names)))
            result = await client.call_tool("read_npy", {"input_filepath": str(npy_path)})
            checks.check("live read_npy MCP call returns summary", "Read NumPy array" in text(result), text(result))

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} JSON/NPY-reader checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
