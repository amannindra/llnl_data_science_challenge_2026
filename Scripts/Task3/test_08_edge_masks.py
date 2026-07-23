"""
ATTACK #8 — Degenerate but VALID masks (must succeed, not error).

All-zero, all-one, single-voxel, float (>0 semantics), and already-boolean
masks are all legitimate inputs. The wrapper must handle them without crashing
and must match skimage where a ground truth is well defined.
"""
import os
import tempfile

import numpy as np
from skimage.morphology import skeletonize as sk_skeletonize

from _harness import Checker, load_skeletonize, finish

skeletonize, _ = load_skeletonize()
c = Checker("Degenerate-but-valid masks (empty/solid/single/float/bool)")


def run(mask, tmp, name="m"):
    inp = os.path.join(tmp, f"{name}.npy")
    out = os.path.join(tmp, f"{name}_s.npy")
    np.save(inp, mask)
    msg = skeletonize(inp, out)
    return msg, (np.load(out) if os.path.exists(out) else None)


with tempfile.TemporaryDirectory() as tmp:
    # 1) All-zero mask -> valid empty skeleton, NOT an error.
    msg, skel = run(np.zeros((16, 16, 16), np.uint8), tmp, "zero")
    c.check("all-zero mask succeeds with empty skeleton",
            "Saved skeleton" in msg and skel is not None and int(skel.sum()) == 0,
            f"msg={msg!r}")

    # 2) Solid cube -> no crash, and faithfully matches skimage. (A solid convex
    #    block legitimately skeletonizes to EMPTY under skimage's 3D thinning, so
    #    the contract is "match skimage exactly", not "non-empty".)
    solid = np.ones((14, 14, 14), np.uint8)
    msg, skel = run(solid, tmp, "solid")
    c.check("solid cube succeeds and matches skimage exactly",
            "Saved skeleton" in msg and skel is not None
            and np.array_equal(skel, sk_skeletonize(solid > 0)),
            f"msg={msg!r}")

    # 3) Single voxel -> no crash.
    sv = np.zeros((10, 10, 10), np.uint8)
    sv[5, 5, 5] = 1
    msg, skel = run(sv, tmp, "single")
    c.check("single-voxel mask does not crash",
            "Saved skeleton" in msg and skel is not None, f"msg={msg!r}")

    # 4) Float mask -> uses (>0); must match skimage on (>0).
    fm = np.zeros((20, 20, 20), np.float32)
    fm[:, 10, 10] = 0.7
    fm[10, :, 10] = -0.3   # <=0 must be background
    fm[10, 10, :] = 2.5
    msg, skel = run(fm, tmp, "float")
    c.check("float mask uses (>0) semantics, matches skimage",
            skel is not None and np.array_equal(skel, sk_skeletonize(fm > 0)),
            f"msg={msg!r}")

    # 5) Already-boolean mask -> matches skimage.
    bm = np.zeros((18, 18, 18), bool)
    bm[:, 9, 9] = True
    bm[9, :, 9] = True
    msg, skel = run(bm, tmp, "bool")
    c.check("boolean-dtype mask matches skimage",
            skel is not None and np.array_equal(skel, sk_skeletonize(bm)),
            f"msg={msg!r}")

finish(c.done())
