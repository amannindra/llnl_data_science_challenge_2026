"""
ATTACK #4 — END-TO-END through the REAL MCP server.

The other suites call the Python function directly. This one proves the tool is
actually registered and callable over the MCP protocol (FastMCP in-memory
Client): schema is generated, arguments are validated/serialized, the tool runs,
and the on-disk result is correct. If the @mcp.tool() wiring were broken, direct
unit tests could still pass while the agent-facing tool did not.
"""
import asyncio
import os
import tempfile

import numpy as np
from fastmcp import Client

from _harness import Checker, load_segment, finish

_, mod = load_segment()
c = Checker("End-to-end via FastMCP Client (real MCP protocol)")


def result_text(res):
    """Robustly pull the tool's string return out of a CallToolResult."""
    data = getattr(res, "data", None)
    if isinstance(data, str):
        return data
    for block in getattr(res, "content", []) or []:
        txt = getattr(block, "text", None)
        if txt:
            return txt
    return str(res)


async def main():
    async with Client(mod.mcp) as client:
        # 1) The tool is discoverable with the expected name.
        tools = await client.list_tools()
        names = {t.name for t in tools}
        c.check("segment_ct_dataset is registered as an MCP tool",
                "segment_ct_dataset" in names, f"tools={sorted(names)}")

        # 2) Its input schema exposes the 3 documented parameters.
        tool = next((t for t in tools if t.name == "segment_ct_dataset"), None)
        props = (tool.inputSchema or {}).get("properties", {}) if tool else {}
        c.check("schema exposes input_filepath/output_filepath/threshold",
                {"input_filepath", "output_filepath", "threshold"} <= set(props),
                f"params={sorted(props)}")

        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "vol.npy")
            out = os.path.join(tmp, "seg.npy")
            vol = (np.random.default_rng(7).random((16, 16, 16)) - 0.5).astype(np.float32)
            np.save(inp, vol)

            # 3) Call the tool exactly as an agent would (kwargs dict).
            res = await client.call_tool(
                "segment_ct_dataset",
                {"input_filepath": inp, "output_filepath": out, "threshold": 0.0},
            )
            text = result_text(res)
            c.check("call_tool returns a success string",
                    isinstance(text, str) and "Saved segmentation" in text,
                    f"text={text!r}")

            # 4) The on-disk output produced via MCP matches the numpy ground truth.
            c.check("MCP-produced file matches (data >= 0.0)",
                    os.path.exists(out)
                    and np.array_equal(np.load(out), (vol >= 0.0).astype(np.uint8)))

            # 5) A missing-file call surfaces the Error string through the protocol.
            res2 = await client.call_tool(
                "segment_ct_dataset",
                {"input_filepath": os.path.join(tmp, "nope.npy"),
                 "output_filepath": out, "threshold": 0.5},
            )
            t2 = result_text(res2)
            c.check("missing-file error propagates as a string over MCP",
                    isinstance(t2, str) and t2.lower().startswith("error"),
                    f"text={t2!r}")


asyncio.run(main())
finish(c.done())
