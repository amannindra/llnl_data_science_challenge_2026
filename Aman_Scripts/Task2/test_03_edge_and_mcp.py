"""
ATTACK #3 — EDGE / ERROR robustness + LIVE MCP protocol.

Part A: prove visualize_slice crashes (uncaught exception) or writes garbage on
inputs an agent will realistically throw at it: missing files, empty paths,
non-3D arrays, out-of-range axis/index, bad types, non-numeric or pickled
arrays, and NaN/inf/constant slices. Per the docstring, expected failures must
be returned as an "Error: ..." STRING, never raised.

Part B: prove the tool is actually reachable over the real MCP protocol
(FastMCP in-memory Client): registered, schema exposes all 4 params, a real
call renders a file, and a bad call surfaces the Error string over the wire.
"""
import asyncio
import os
import tempfile

import numpy as np
from fastmcp import Client

from _harness import Checker, load_visualize, finish

visualize, mod = load_visualize()
c = Checker("Edge/error robustness + live MCP (must return strings, never crash)")


def safe(*args):
    """Call visualize; capture a raised exception instead of dying."""
    try:
        return visualize(*args), None
    except Exception as e:  # noqa: BLE001
        return None, e


def is_err(ret):
    return isinstance(ret, str) and ret.lower().startswith("error")


# ---------------------------------------------------------------- Part A -----
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "out.png")
    inp = os.path.join(tmp, "vol.npy")
    np.save(inp, np.random.default_rng(3).standard_normal((6, 5, 4)).astype(np.float32))

    # 1) Missing input file -> Error string, nothing written.
    miss_out = os.path.join(tmp, "should_not_exist.png")
    ret, exc = safe(os.path.join(tmp, "nope.npy"), miss_out, 0)
    c.check("missing input -> Error string (no raise)",
            exc is None and is_err(ret), f"ret={ret!r}, exc={exc!r}")
    c.check("missing input wrote no image", not os.path.exists(miss_out))

    # 2) Empty path strings -> Error strings.
    c.check("empty input_filepath -> Error", is_err(safe("", out, 0)[0]))
    c.check("empty output_filepath -> Error", is_err(safe(inp, "", 0)[0]))

    # 3) Non-3D arrays are rejected (2D, 1D, 4D).
    for shape in ((10, 10), (10,), (2, 3, 4, 5)):
        p = os.path.join(tmp, "nd.npy")
        np.save(p, np.zeros(shape, dtype=np.float32))
        ret, exc = safe(p, out, 0)
        c.check(f"{len(shape)}D array rejected with Error string",
                exc is None and is_err(ret), f"shape={shape}, ret={ret!r}")

    # 4) Axis out of range / bad type -> Error (strict 0/1/2).
    for bad_axis in (3, -1, 99):
        c.check(f"axis={bad_axis} rejected", is_err(safe(inp, out, 0, bad_axis)[0]))
    c.check("non-integer axis rejected", is_err(safe(inp, out, 0, "x")[0]))

    # 5) slice_index out of range -> Error, and NO file written.
    oor = os.path.join(tmp, "oor.png")
    ret, exc = safe(inp, oor, 999, 0)
    c.check("slice_index too large -> Error (no raise)", exc is None and is_err(ret))
    c.check("out-of-range index wrote no image", not os.path.exists(oor))
    c.check("slice_index too negative -> Error", is_err(safe(inp, out, -7, 0)[0]))

    # 6) slice_index type coercion: numeric string / float ok; junk rejected.
    r_str, _ = safe(inp, os.path.join(tmp, "s_str.png"), "2", 0)
    c.check("string-numeric slice_index coerced (renders)",
            not is_err(r_str) and os.path.exists(os.path.join(tmp, "s_str.png")),
            f"ret={r_str!r}")
    r_float, _ = safe(inp, os.path.join(tmp, "s_flt.png"), 2.0, 0)
    c.check("float slice_index coerced (renders)", not is_err(r_float))
    c.check("non-numeric slice_index rejected", is_err(safe(inp, out, "abc", 0)[0]))

    # 7) Non-numeric array (strings) -> Error, not a crash.
    sp = os.path.join(tmp, "strs.npy")
    np.save(sp, np.array([["a", "b"], ["c", "d"]]))
    ret, exc = safe(sp, out, 0)
    c.check("non-numeric array rejected with Error string",
            exc is None and is_err(ret), f"ret={ret!r}")

    # 8) Pickled/object array -> allow_pickle=False must be caught, not crash.
    op = os.path.join(tmp, "obj.npy")
    np.save(op, np.array([{"a": 1}, [1, 2]], dtype=object), allow_pickle=True)
    ret, exc = safe(op, out, 0)
    c.check("object/pickled array rejected with Error string (no unsafe load)",
            exc is None and is_err(ret), f"ret={ret!r}")

    # 9) NaN/inf voxels in the slice must NOT crash; a valid image is produced.
    nanvol = np.random.default_rng(4).standard_normal((4, 4, 4)).astype(np.float64)
    nanvol[0, 0, 0], nanvol[0, 1, 1], nanvol[0, 2, 2] = np.nan, np.inf, -np.inf
    npath = os.path.join(tmp, "nan.npy")
    np.save(npath, nanvol)
    nout = os.path.join(tmp, "nan.png")
    ret, exc = safe(npath, nout, 0)
    c.check("NaN/inf slice renders without crashing",
            exc is None and not is_err(ret) and os.path.exists(nout), f"ret={ret!r}")

    # 10) Constant slice (zero dynamic range) must not divide-by-zero.
    cvol = np.zeros((3, 3, 3), dtype=np.float32)
    cpath = os.path.join(tmp, "const.npy")
    np.save(cpath, cvol)
    cout = os.path.join(tmp, "const.png")
    ret, exc = safe(cpath, cout, 0)
    c.check("constant slice renders (no zero-range crash)",
            exc is None and not is_err(ret) and os.path.exists(cout), f"ret={ret!r}")


# ---------------------------------------------------------------- Part B -----
async def mcp_checks():
    async with Client(mod.mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        c.check("visualize_slice registered as an MCP tool",
                "visualize_slice" in names, f"tools={sorted(names)}")

        tool = next((t for t in tools if t.name == "visualize_slice"), None)
        props = (tool.inputSchema or {}).get("properties", {}) if tool else {}
        c.check("schema exposes all 4 params",
                {"input_filepath", "output_filepath", "slice_index", "axis"} <= set(props),
                f"params={sorted(props)}")

        with tempfile.TemporaryDirectory() as tmp:
            inp = os.path.join(tmp, "vol.npy")
            out = os.path.join(tmp, "seg_slice.png")
            np.save(inp, np.random.default_rng(5).random((8, 8, 8)).astype(np.float32))

            res = await client.call_tool(
                "visualize_slice",
                {"input_filepath": inp, "output_filepath": out,
                 "slice_index": 4, "axis": 0},
            )
            text = getattr(res, "data", None)
            if not isinstance(text, str):
                text = next((getattr(b, "text", "") for b in
                             getattr(res, "content", []) or []), str(res))
            c.check("call_tool renders a file and returns success string",
                    isinstance(text, str) and "Saved slice visualization" in text
                    and os.path.exists(out), f"text={text!r}")

            res2 = await client.call_tool(
                "visualize_slice",
                {"input_filepath": os.path.join(tmp, "gone.npy"),
                 "output_filepath": out, "slice_index": 0, "axis": 0},
            )
            t2 = getattr(res2, "data", None)
            if not isinstance(t2, str):
                t2 = next((getattr(b, "text", "") for b in
                           getattr(res2, "content", []) or []), str(res2))
            c.check("missing-file error propagates as a string over MCP",
                    isinstance(t2, str) and t2.lower().startswith("error"),
                    f"text={t2!r}")


asyncio.run(mcp_checks())
finish(c.done())
