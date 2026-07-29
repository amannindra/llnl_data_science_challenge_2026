#!/usr/bin/env python3
"""Focused adversarial and live-MCP checks for the TIFF reader tool."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

import numpy as np
import tifffile
from fastmcp import Client


REPOSITORY = Path(__file__).resolve().parents[2]
SERVER = REPOSITORY / "Aman_src" / "mcp_server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("aman_mcp_tiff_test", SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load MCP server from {SERVER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result_text(result) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return str(result)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}: {detail}")


async def main() -> int:
    module = load_server()
    read_tiff = module.read_tiff
    checks = Checks()

    with tempfile.TemporaryDirectory(prefix="dssi_mcp_tiff_") as temporary:
        root = Path(temporary)
        volume = np.arange(3 * 4 * 5, dtype=np.uint16).reshape(3, 4, 5)
        source = root / "volume.tif"
        tifffile.imwrite(source, volume, imagej=True, metadata={"axes": "ZYX"})
        source_before = source.read_bytes()

        output = root / "nested" / "volume"
        response = read_tiff(str(source), str(output))
        saved = Path(f"{output}.npy")
        checks.check("uncompressed TIFF converts", response.startswith("Saved TIFF series"), response)
        checks.check("missing .npy extension is appended", saved.is_file())
        checks.check("output parents are created", saved.parent.is_dir())
        checks.check("shape, dtype, and values are preserved",
                     np.array_equal(np.load(saved), volume))
        checks.check("ZYX axes are reported", "axes=ZYX" in response, response)
        checks.check("SHA-256 provenance is reported", "sha256=" in response, response)
        checks.check("source TIFF remains unchanged", source.read_bytes() == source_before)

        compressed_source = root / "compressed.TIFF"
        compressed = (volume * 7).astype(np.uint16)
        tifffile.imwrite(compressed_source, compressed, compression="deflate",
                         metadata={"axes": "ZYX"})
        compressed_output = root / "compressed.npy"
        compressed_response = read_tiff(str(compressed_source), str(compressed_output))
        checks.check("compressed .TIFF converts", not compressed_response.startswith("Error:"),
                     compressed_response)
        checks.check("compressed values are preserved",
                     compressed_output.is_file()
                     and np.array_equal(np.load(compressed_output), compressed))

        multi_source = root / "multi.tif"
        first = np.arange(12, dtype=np.uint8).reshape(3, 4)
        second = np.arange(30, dtype=np.int16).reshape(5, 6)
        with tifffile.TiffWriter(multi_source) as writer:
            writer.write(first)
            writer.write(second)
        multi_output = root / "second.npy"
        multi_response = read_tiff(str(multi_source), str(multi_output), 1)
        checks.check("non-default TIFF series converts", not multi_response.startswith("Error:"),
                     multi_response)
        checks.check("requested series values are preserved",
                     multi_output.is_file() and np.array_equal(np.load(multi_output), second))

        bad_output = root / "bad.npy"
        checks.check("empty input path is rejected",
                     read_tiff("", str(bad_output)).startswith("Error:"))
        checks.check("empty output path is rejected",
                     read_tiff(str(source), "").startswith("Error:"))
        checks.check("non-TIFF extension is rejected",
                     read_tiff(str(root / "volume.png"), str(bad_output)).startswith("Error:"))
        checks.check("negative series is rejected",
                     read_tiff(str(source), str(bad_output), -1).startswith("Error:"))
        checks.check("non-integer series is rejected",
                     read_tiff(str(source), str(bad_output), 1.5).startswith("Error:"))
        checks.check("past-end series is rejected",
                     read_tiff(str(source), str(bad_output), 99).startswith("Error:"))

        corrupt = root / "corrupt.tif"
        corrupt.write_bytes(b"not a TIFF")
        existing = root / "existing.npy"
        np.save(existing, np.array([91, 92], dtype=np.int16))
        existing_before = existing.read_bytes()
        corrupt_response = read_tiff(str(corrupt), str(existing))
        checks.check("corrupt TIFF returns an Error string", corrupt_response.startswith("Error:"),
                     corrupt_response)
        checks.check("failed read preserves an existing output",
                     existing.read_bytes() == existing_before)
        checks.check("failed read leaves no temporary NPY",
                     not list(root.glob(".existing.npy.*.tmp.npy")))

        pointer = root / "pointer.tif"
        pointer.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{'a' * 64}\n"
            "size 123456\n",
            encoding="utf-8",
        )
        pointer_response = read_tiff(str(pointer), str(bad_output))
        checks.check("Git-LFS pointer is rejected before TIFF decoding",
                     pointer_response.startswith("Error:") and "not materialized" in pointer_response,
                     pointer_response)

        async with Client(module.mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            checks.check("read_tiff is registered with FastMCP", "read_tiff" in names,
                         f"tools={sorted(names)}")
            tool = next(item for item in tools if item.name == "read_tiff")
            properties = (tool.inputSchema or {}).get("properties", {})
            checks.check("MCP schema exposes all TIFF reader parameters",
                         {"input_filepath", "output_filepath", "series_index"}
                         <= set(properties), f"params={sorted(properties)}")

            live_output = root / "live.npy"
            result = await client.call_tool(
                "read_tiff",
                {
                    "input_filepath": str(source),
                    "output_filepath": str(live_output),
                    "series_index": 0,
                },
            )
            text = result_text(result)
            checks.check("live MCP call saves the correct volume",
                         text.startswith("Saved TIFF series")
                         and live_output.is_file()
                         and np.array_equal(np.load(live_output), volume), text)

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} MCP TIFF-reader checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
