"""
ATTACK #1 — Prove it does NOT actually wrap skeletonize_mask.

Task 3's whole point is exposing the EXISTING skeletonize_mask() API, not
reimplementing skeletonization. We spy on mod.skeletonize_mask to prove the
wrapper delegates to it (once, with the input path and an output path), and
that the saved result equals an independent skimage skeletonization.
"""
import os
import tempfile

import numpy as np
from skimage.morphology import skeletonize as sk_skeletonize

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, mod = load_skeletonize()
c = Checker("Genuine wrapper around skeletonize_mask (not a reimplementation)")

real = mod.skeletonize_mask
calls = []


def spy(file_path, output_path):
    calls.append((file_path, output_path))
    return real(file_path, output_path)


with tempfile.TemporaryDirectory() as tmp:
    mask = cross_mask(24)
    inp = os.path.join(tmp, "m.npy")
    out = os.path.join(tmp, "s.npy")
    np.save(inp, mask)

    mod.skeletonize_mask = spy
    try:
        msg = skeletonize(inp, out)
    finally:
        mod.skeletonize_mask = real

    c.check("skeletonize_mask was invoked exactly once", len(calls) == 1, f"calls={calls}")
    c.check("invoked with the input path as first arg",
            bool(calls) and calls[0][0] == inp, f"calls={calls}")
    c.check("invoked with a .npy output path as second arg",
            bool(calls) and isinstance(calls[0][1], str) and calls[0][1].endswith(".npy"),
            f"calls={calls}")
    expected = sk_skeletonize(mask > 0)
    c.check("saved skeleton equals independent skimage.skeletonize(mask>0)",
            os.path.exists(out) and np.array_equal(np.load(out), expected))
    c.check("returns a success string naming the saved file",
            isinstance(msg, str) and "Saved skeleton" in msg and out in msg,
            f"msg={msg!r}")

finish(c.done())
