#!/usr/bin/env python3
"""Call Task 2 through FastMCP and verify the real unit-cell output pixels."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
from fastmcp import Client
from PIL import Image

from _harness import Checker, ROOT, load_visualize


AXIS = 0
SLICE_INDEX = 128


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


async def run_test() -> int:
    checker = Checker("03 — real unit-cell slice through FastMCP")
    visualize, module = load_visualize()
    source = Path(ROOT) / "data" / "unitcell" / "unitcell.npy"
    source_hash_before = digest(source)
    volume = np.load(source, mmap_mode="r")
    vmin, vmax = float(volume.min()), float(volume.max())
    reference = np.take(volume, SLICE_INDEX, axis=AXIS)

    with tempfile.TemporaryDirectory(prefix="task2_mcp_") as temporary:
        work = Path(temporary)
        requested_output = work / "mcp_created" / "unitcell_axis0_128"  # no suffix and no parent
        async with Client(module.mcp) as client:
            tool_names = {tool.name for tool in await client.list_tools()}
            checker.check("MCP server exposes visualize_slice", "visualize_slice" in tool_names, repr(sorted(tool_names)))
            result = await client.call_tool(
                "visualize_slice",
                {
                    "input_filepath": str(source),
                    "output_filepath": str(requested_output),
                    "slice_index": SLICE_INDEX,
                    "axis": AXIS,
                },
            )
        status = "\n".join(getattr(block, "text", "") for block in result.content)
        output = requested_output.with_suffix(".png")
        checker.check("MCP tool call reports success", not result.is_error, status)
        checker.check("MCP tool created parent directory and PNG", output.is_file(), str(output))
        if output.is_file():
            rgba = np.asarray(Image.open(output).convert("RGBA"))
            expected = np.rint(np.clip((reference - vmin) / (vmax - vmin), 0, 1) * 255).astype(np.int16)
            actual = rgba[..., 0].astype(np.int16)
            checker.check("PNG dimensions are exactly 256×256", rgba.shape == (256, 256, 4), str(rgba.shape))
            checker.check("PNG pixel values match the selected real CT slice", np.max(np.abs(actual - expected)) <= 1, f"max_error={np.max(np.abs(actual - expected))}")
            checker.check("PNG is opaque grayscale", np.array_equal(rgba[..., 0], rgba[..., 1]) and np.array_equal(rgba[..., 1], rgba[..., 2]) and np.all(rgba[..., 3] == 255))
            checker.check("status records the requested axis and index", "axis=0" in status and "slice_index=128" in status, status)
        else:
            for name in ("PNG dimensions are exactly 256×256", "PNG pixel values match the selected real CT slice", "PNG is opaque grayscale", "status records the requested axis and index"):
                checker.check(name, False, "output was not created")

        checker.check("direct visualizer call protects raw input from overwrite", visualize(str(source), str(source), SLICE_INDEX, AXIS).startswith("Error:"))
        checker.check("raw CT hash remains unchanged", digest(source) == source_hash_before)
    return checker.done()


if __name__ == "__main__":
    sys.exit(asyncio.run(run_test()))
