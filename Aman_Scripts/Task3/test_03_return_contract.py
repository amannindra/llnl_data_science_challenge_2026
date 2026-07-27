"""
ATTACK #3 — Return-type contract.

An MCP tool MUST return a string, always. But skeletonize_mask returns an
ndarray on success and None on a missing file. The wrapper has to convert BOTH
into strings — never leak the array, never return None.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, _ = load_skeletonize()
c = Checker("Return contract (always a string; never None/ndarray)")

with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "m.npy")
    out = os.path.join(tmp, "s.npy")
    np.save(inp, cross_mask(20))

    ok = skeletonize(inp, out)
    c.check("success returns a str", isinstance(ok, str), f"type={type(ok).__name__}")
    c.check("success is not an ndarray", not isinstance(ok, np.ndarray))
    c.check("success message says 'Saved skeleton'", "Saved skeleton" in ok, f"msg={ok!r}")

    err = skeletonize(os.path.join(tmp, "missing.npy"), out)
    c.check("failure returns a str", isinstance(err, str), f"type={type(err).__name__}")
    c.check("failure is not None", err is not None)
    c.check("failure message starts with 'Error'", err.lower().startswith("error"), f"msg={err!r}")

finish(c.done())
