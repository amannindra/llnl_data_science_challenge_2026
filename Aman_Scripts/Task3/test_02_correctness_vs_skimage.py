"""
ATTACK #2 — Correctness vs an independent skimage ground truth.

The wrapper must produce exactly what skimage.morphology.skeletonize(mask>0)
produces — no accidental transforms, no dtype loss — on synthetic data and on a
real thresholded crop of unitcell.npy.
"""
import os
import tempfile

import numpy as np
from skimage.morphology import skeletonize as sk_skeletonize

from _harness import Checker, load_skeletonize, finish, ROOT

skeletonize, _ = load_skeletonize()
c = Checker("Skeleton correctness vs skimage.morphology.skeletonize(mask>0)")

with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "s.npy")

    # Synthetic 3D grid of planes -> non-trivial skeleton.
    mask = np.zeros((40, 40, 40), np.uint8)
    for k in range(4, 40, 8):
        mask[k, :, :] = 1
        mask[:, k, :] = 1
    inp = os.path.join(tmp, "syn.npy")
    np.save(inp, mask)
    skeletonize(inp, out)
    c.check("synthetic mask: exact match to skimage",
            np.array_equal(np.load(out), sk_skeletonize(mask > 0)))

# Real data: a small thresholded crop of the actual CT volume.
real_npy = os.path.join(ROOT, "data", "unitcell", "unitcell.npy")
if os.path.exists(real_npy):
    vol = np.load(real_npy)
    crop = vol[96:144, 96:144, 96:144]
    thr = float(crop.mean() + crop.std())
    m = (crop >= thr).astype(np.uint8)
    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "rm.npy")
        out = os.path.join(tmp, "rs.npy")
        np.save(inp, m)
        skeletonize(inp, out)
        c.check("real unitcell crop: exact match to skimage",
                np.array_equal(np.load(out), sk_skeletonize(m > 0)),
                f"foreground={int(m.sum())}")
else:
    c.check("real unitcell present", False, "missing (skipped)")

finish(c.done())
