#!/usr/bin/env python3
"""Exercise Task 1 through a real in-memory MCP server against unitcell.npy."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
from fastmcp import Client

from _harness import Checker, ROOT, load_segment


THRESHOLD = 0.005813093855977058  # Otsu value established in the data audit


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


async def run_test() -> int:
    checker = Checker("03 — real volume through FastMCP and output safety")
    segment, module = load_segment()
    source = Path(ROOT) / "data" / "unitcell" / "unitcell.npy"
    source_hash_before = digest(source)

    with tempfile.TemporaryDirectory(prefix="task1_mcp_") as temporary:
        work = Path(temporary)
        requested_output = work / "created_by_tool" / "unitcell_mask"  # no .npy and missing parent
        expected = (np.load(source, mmap_mode="r") >= THRESHOLD).astype(np.uint8)

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            checker.check("MCP server exposes segment_ct_dataset", "segment_ct_dataset" in tool_names, repr(sorted(tool_names)))
            result = await client.call_tool(
                "segment_ct_dataset",
                {
                    "input_filepath": str(source),
                    "output_filepath": str(requested_output),
                    "threshold": THRESHOLD,
                },
            )

        status = "\n".join(getattr(block, "text", "") for block in result.content)
        output = requested_output.with_suffix(".npy")
        checker.check("MCP tool call completed without an error result", not result.is_error, status)
        checker.check("MCP call created parent directory and .npy output", output.is_file(), str(output))
        if output.is_file():
            actual = np.load(output, mmap_mode="r")
            checker.check("real-volume mask has expected shape and uint8 dtype", actual.shape == expected.shape and actual.dtype == np.uint8, f"shape={actual.shape}, dtype={actual.dtype}")
            checker.check("real-volume mask exactly matches NumPy >= reference", np.array_equal(actual, expected), f"foreground={int(actual.sum())}")
            checker.check("status reports exact real-volume foreground count", f"foreground={int(expected.sum())}/{expected.size}" in status, status)
        else:
            checker.check("real-volume mask has expected shape and uint8 dtype", False, "output was not created")
            checker.check("real-volume mask exactly matches NumPy >= reference", False, "output was not created")
            checker.check("status reports exact real-volume foreground count", False, status)

        overwrite_result = segment(str(source), str(source), THRESHOLD)
        checker.check("input-as-output overwrite is rejected", overwrite_result.startswith("Error:"), overwrite_result)
        checker.check("raw CT hash remains unchanged", digest(source) == source_hash_before)
    return checker.done()


if __name__ == "__main__":
    sys.exit(asyncio.run(run_test()))
