"""
ATTACK #4 — Missing / malformed paths.

skeletonize_mask only *prints* "Error: File not found" and returns None on a
missing file — invisible to an agent. The wrapper must surface these as proper
"Error:" strings, must not raise, and must not create bogus output.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, _ = load_skeletonize()
c = Checker("Path validation (missing/empty/dir inputs -> Error strings)")


def safe(*a):
    try:
        return skeletonize(*a), None
    except Exception as e:  # noqa: BLE001
        return None, e


def is_err(r):
    return isinstance(r, str) and r.lower().startswith("error")


with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "out.npy")

    r, e = safe(os.path.join(tmp, "nope.npy"), out)
    c.check("missing input -> Error string (no raise)", e is None and is_err(r), f"r={r!r}, e={e!r}")
    c.check("missing input wrote no output", not os.path.exists(out))

    c.check("empty input_filepath -> Error", is_err(safe("", out)[0]))

    inp = os.path.join(tmp, "m.npy")
    np.save(inp, cross_mask(16))
    c.check("empty output_filepath -> Error", is_err(safe(inp, "")[0]))

    r, e = safe(tmp, out)  # a directory, not a file
    c.check("directory as input -> Error (no raise)", e is None and is_err(r), f"r={r!r}")

finish(c.done())
