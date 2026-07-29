#!/usr/bin/env python3
"""Focused checks for streamed Otsu segmentation of TIFF volumes."""

from __future__ import annotations

import asyncio
import importlib.util
import tempfile
from pathlib import Path

import numpy as np
import tifffile
from fastmcp import Client


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "Aman_src" / "mcp_server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("aman_mcp_otsu_test", SERVER)
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
    with tempfile.TemporaryDirectory(prefix="dssi_mcp_otsu_") as temporary:
        root = Path(temporary)
        volume = np.zeros((6, 8, 10), dtype=np.uint16)
        volume[:, :4, :] = 100
        volume[:, 4:, :] = 500
        source = root / "source.tif"
        tifffile.imwrite(source, volume, imagej=True, metadata={"axes": "ZYX"})

        output = root / "nested" / "mask"
        response = module.segment_tiff_otsu(str(source), str(output))
        saved = Path(f"{output}.tif")
        checks.check("synthetic TIFF is segmented", response.startswith("Saved Otsu TIFF mask"), response)
        checks.check("missing output extension is appended", saved.is_file())
        mask = tifffile.imread(saved)
        checks.check("mask preserves 3D shape", mask.shape == volume.shape, repr(mask.shape))
        with tifffile.TiffFile(saved) as tif:
            checks.check("mask preserves ZYX axes", tif.series[0].axes == "ZYX", tif.series[0].axes)
        checks.check("mask uses uint8 0/255 encoding",
                     mask.dtype == np.uint8 and set(np.unique(mask)) == {0, 255}, repr(np.unique(mask)))
        checks.check("Otsu separates the two intensity classes",
                     np.all(mask[:, :4, :] == np.uint8(0))
                     and np.all(mask[:, 4:, :] == np.uint8(255)))
        checks.check("threshold and foreground count are reported",
                     "threshold=" in response and "foreground=240/480" in response, response)
        checks.check("sha256 is reported", "sha256=" in response, response)

        bad = root / "bad.npy"
        checks.check("non-TIFF input is rejected",
                     module.segment_tiff_otsu(str(bad), str(output)).startswith("Error:"))
        checks.check("missing input is rejected",
                     module.segment_tiff_otsu(str(root / "missing.tif"), str(output)).startswith("Error:"))
        checks.check("negative series is rejected",
                     module.segment_tiff_otsu(str(source), str(output), -1).startswith("Error:"))
        checks.check("failed conversion does not leave a temp TIFF",
                     not list(saved.parent.glob(".*.tmp.tif")))

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            checks.check("Otsu tool is registered", "segment_tiff_otsu" in names, str(sorted(names)))
            result = await client.call_tool(
                "segment_tiff_otsu",
                {"input_filepath": str(source), "output_filepath": str(root / "live.tif")},
            )
            checks.check("live MCP Otsu call writes a mask",
                         "Saved Otsu TIFF mask" in result_text(result)
                         and (root / "live.tif").is_file(), result_text(result))

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} Otsu TIFF checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
