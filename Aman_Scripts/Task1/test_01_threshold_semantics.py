"""
ATTACK #1 — Threshold / segmentation SEMANTICS.

Goal: prove the function does NOT implement the documented rule
"Voxels >= threshold -> 1, others -> 0". The classic bug is using `>` instead
of `>=`, or getting the direction wrong. We also check exhaustively against a
numpy ground truth on synthetic AND real data, and that the input is untouched.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_segment, finish, ROOT

segment, _ = load_segment()
c = Checker("Threshold semantics (>= rule, exactness, no mutation)")

with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "in.npy")
    out = os.path.join(tmp, "out.npy")

    # 1) Exact-boundary voxel MUST become 1 (this fails a `>` implementation).
    arr = np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float64)  # all exact in binary
    np.save(inp, arr)
    segment(inp, out, 0.5)
    mask = np.load(out)
    c.check("value exactly == threshold maps to 1 (>= not >)",
            mask.tolist() == [0, 0, 1, 1, 1], f"mask={mask.tolist()}")

    # 2) Just below threshold maps to 0; just above maps to 1.
    eps = np.array([0.5 - 1e-6, 0.5, 0.5 + 1e-6], dtype=np.float64)
    np.save(inp, eps)
    segment(inp, out, 0.5)
    c.check("below->0, equal->1, above->1", np.load(out).tolist() == [0, 1, 1])

    # 3) Exhaustive match vs numpy ground truth, random data, many thresholds.
    rng = np.random.default_rng(0)
    vol = rng.standard_normal((32, 24, 16)).astype(np.float32)
    np.save(inp, vol)
    ok_all = True
    for thr in [-2.0, -0.3, 0.0, 0.37, 1.5, 3.0]:
        segment(inp, out, thr)
        expected = (vol >= thr).astype(np.uint8)
        if not np.array_equal(np.load(out), expected):
            ok_all = False
    c.check("matches (data >= thr) elementwise over 6 thresholds", ok_all)

    # 4) Output is strictly binary {0,1}.
    segment(inp, out, 0.1)
    uniq = set(np.unique(np.load(out)).tolist())
    c.check("output contains only {0, 1}", uniq <= {0, 1}, f"unique={sorted(uniq)}")

    # 5) Negative thresholds / negative data (real CT recon has negatives).
    negvol = rng.standard_normal((10, 10, 10)).astype(np.float32) - 0.5
    np.save(inp, negvol)
    segment(inp, out, -0.5)
    c.check("negative threshold handled correctly",
            np.array_equal(np.load(out), (negvol >= -0.5).astype(np.uint8)))

    # 6) The input array on disk must NOT be mutated by segmentation.
    before = np.load(inp).copy()
    segment(inp, out, 0.0)
    after = np.load(inp)
    c.check("input file/array is not mutated", np.array_equal(before, after))

# 7) Real dataset: foreground fraction must equal the manual computation.
real = os.path.join(ROOT, "data", "unitcell", "unitcell.npy")
if os.path.exists(real) and np.load(real, mmap_mode="r").size > 0:
    vol = np.load(real)
    thr = float(np.percentile(vol, 99))  # a threshold that yields ~1% foreground
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seg.npy")
        segment(real, out, thr)
        got = int(np.load(out).sum())
    expected = int((vol >= thr).sum())
    c.check("real unitcell.npy: foreground count matches numpy",
            got == expected, f"got={got}, expected={expected}")
else:
    c.check("real unitcell.npy present", False, "file missing/empty (skipped)")

finish(c.done())
