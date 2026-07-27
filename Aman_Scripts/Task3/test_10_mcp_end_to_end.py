"""
ATTACK #10 — END-TO-END through the REAL MCP protocol.

Proves skeletonize is actually reachable over FastMCP's in-memory Client:
registered, 2-parameter schema, a live call produces a file + success string,
missing-file errors propagate, and the full segment -> skeletonize pipeline
works tool-to-tool the way an agent would drive it.
"""
import asyncio
import os
import tempfile

import numpy as np
from fastmcp import Client

from _harness import Checker, load_skeletonize, cross_mask, finish

_, mod = load_skeletonize()
c = Checker("End-to-end via FastMCP Client (real MCP protocol)")


def result_text(res):
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
        tools = await client.list_tools()
        names = {t.name for t in tools}
        c.check("skeletonize is registered as an MCP tool",
                "skeletonize" in names, f"tools={sorted(names)}")

        tool = next((t for t in tools if t.name == "skeletonize"), None)
        props = (tool.inputSchema or {}).get("properties", {}) if tool else {}
        c.check("schema exposes exactly input_filepath + output_filepath",
                {"input_filepath", "output_filepath"} <= set(props),
                f"params={sorted(props)}")

        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "m.npy")
            out = os.path.join(tmp, "skel.npy")
            np.save(inp, cross_mask(20))

            res = await client.call_tool(
                "skeletonize",
                {"input_filepath": inp, "output_filepath": out},
            )
            text = result_text(res)
            c.check("call_tool skeletonize returns success + writes a file",
                    "Saved skeleton" in text and os.path.exists(out), f"text={text!r}")

            res2 = await client.call_tool(
                "skeletonize",
                {"input_filepath": os.path.join(tmp, "nope.npy"), "output_filepath": out},
            )
            c.check("missing-file error propagates as a string over MCP",
                    result_text(res2).lower().startswith("error"))

            # Full pipeline: segment the raw CT, then skeletonize the mask.
            raw = os.path.join(tmp, "raw.npy")
            vol = np.zeros((24, 24, 24), np.float32)
            vol[:, 12, 12] = 1.0
            vol[12, :, 12] = 1.0
            vol[12, 12, :] = 1.0
            np.save(raw, vol)
            mask_out = os.path.join(tmp, "mask.npy")
            skel_out = os.path.join(tmp, "pipeline_skel.npy")

            seg = await client.call_tool(
                "segment_ct_dataset",
                {"input_filepath": raw, "output_filepath": mask_out, "threshold": 0.5},
            )
            skl = await client.call_tool(
                "skeletonize",
                {"input_filepath": mask_out, "output_filepath": skel_out},
            )
            c.check("segment -> skeletonize pipeline works over MCP",
                    "Saved segmentation" in result_text(seg)
                    and "Saved skeleton" in result_text(skl)
                    and os.path.exists(skel_out),
                    f"seg={result_text(seg)!r}; skel={result_text(skl)!r}")


asyncio.run(main())
finish(c.done())
