"""
ATTACK #6 — stdout pollution (a real MCP-stdio hazard).

skeletonize_mask() is full of print() calls. The default MCP transport is stdio
JSON-RPC over stdout, so ANY stray print corrupts the protocol stream. The
wrapper must swallow that chatter — a direct call should leak nothing to stdout.
"""
import contextlib
import io
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, _ = load_skeletonize()
c = Checker("No stdout pollution (would corrupt stdio JSON-RPC)")

with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "m.npy")
    out = os.path.join(tmp, "s.npy")
    np.save(inp, cross_mask(20))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        msg = skeletonize(inp, out)
    leaked = buf.getvalue()

    c.check("nothing leaked to stdout during a successful call",
            leaked.strip() == "", f"leaked={leaked[:120]!r}")
    c.check("skeletonize_mask chatter is suppressed",
            "Loading mask" not in leaked and "Extracting skeleton" not in leaked)
    c.check("call still succeeded", isinstance(msg, str) and "Saved skeleton" in msg)

    # An error path must be quiet too.
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        err = skeletonize(os.path.join(tmp, "gone.npy"), out)
    c.check("error path leaks nothing to stdout either",
            buf2.getvalue().strip() == "" and err.lower().startswith("error"),
            f"leaked={buf2.getvalue()[:120]!r}")

finish(c.done())
