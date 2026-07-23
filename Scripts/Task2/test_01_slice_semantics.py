"""
ATTACK #1 — Slice / axis SEMANTICS.

Goal: prove visualize_slice picks the WRONG slice, the WRONG axis, gets the
default axis wrong, transposes/flips the image, or ignores negative indexing.

Strategy: use a NON-cubic volume (7, 5, 3) so every axis yields a differently
shaped 2D slice — that alone proves the axis was honored. Then read the saved
PNG back to a luminance array and compare it (min-max normalized) to the numpy
ground-truth slice, which proves the correct INDEX was rendered, right-side up.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_visualize, read_luminance, finish, ROOT

visualize, _ = load_visualize()
c = Checker("Slice semantics (axis, index, default, orientation)")


def norm(a):
    a = a.astype(np.float64)
    lo, hi = a.min(), a.max()
    return np.zeros_like(a) if hi <= lo else (a - lo) / (hi - lo)


with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "vol.npy")
    vol = np.random.default_rng(0).standard_normal((7, 5, 3)).astype(np.float32)
    np.save(inp, vol)

    # 1) DEFAULT axis must be 0: slice shape equals vol[idx] -> (5, 3).
    out = os.path.join(tmp, "default.png")
    msg = visualize(inp, out, 2)
    lum = read_luminance(out)
    c.check("default axis == 0 (image shape matches vol[idx])",
            lum.shape == (5, 3), f"shape={lum.shape}, msg={msg!r}")

    # 2) Each axis is honored: the 2D image dims match np.take(...).shape.
    for axis, expshape in ((0, (5, 3)), (1, (7, 3)), (2, (7, 5))):
        out = os.path.join(tmp, f"axis{axis}.png")
        visualize(inp, out, 1, axis)
        lum = read_luminance(out)
        c.check(f"axis={axis} yields correctly shaped image {expshape}",
                lum.shape == expshape, f"got {lum.shape}")

    # 3) The rendered CONTENT is the right slice, right-side up (index correct).
    #    Compare min-max-normalized ground truth to the read-back luminance.
    ok_content = True
    worst = 0.0
    for axis in (0, 1, 2):
        for idx in range(vol.shape[axis]):
            out = os.path.join(tmp, f"c_{axis}_{idx}.png")
            visualize(inp, out, idx, axis)
            lum = read_luminance(out)
            expected = norm(np.take(vol, idx, axis=axis))
            d = float(np.max(np.abs(lum - expected)))
            worst = max(worst, d)
            if lum.shape != expected.shape or d > 0.02:  # ~8-bit LUT tolerance
                ok_content = False
    c.check("rendered pixels match numpy ground-truth slice (no flip/transpose)",
            ok_content, f"worst abs diff={worst:.4f}")

    # 4) A WRONG index would look different: adjacent slices must not be identical
    #    (guards against 'always renders slice 0' style bugs).
    a = read_luminance(os.path.join(tmp, "c_0_0.png"))
    b = read_luminance(os.path.join(tmp, "c_0_1.png"))
    c.check("different slice_index produces a different image",
            a.shape == b.shape and not np.array_equal(a, b))

    # 5) numpy-style NEGATIVE indexing: idx=-1 == last slice along the axis.
    out_neg = os.path.join(tmp, "neg.png")
    out_last = os.path.join(tmp, "last.png")
    visualize(inp, out_neg, -1, 0)
    visualize(inp, out_last, vol.shape[0] - 1, 0)
    c.check("slice_index=-1 equals the last slice",
            np.array_equal(read_luminance(out_neg), read_luminance(out_last)))

    # 6) The message reports the true image_size (width x height).
    out = os.path.join(tmp, "msg.png")
    m = visualize(inp, out, 0, 1)  # axis 1 -> (7, 3) -> 3x7
    c.check("message reports correct image_size WxH",
            "image_size=3x7" in m and "Saved slice visualization" in m, f"msg={m!r}")

# 7) Real dataset: a mid-volume slice renders to a valid, correctly sized image.
real = os.path.join(ROOT, "data", "unitcell", "unitcell.npy")
if os.path.exists(real):
    vol = np.load(real, mmap_mode="r")
    if vol.ndim == 3:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "real.png")
            mid = vol.shape[0] // 2
            visualize(real, out, mid, 0)
            lum = read_luminance(out)
            c.check("real unitcell.npy mid-slice renders at native resolution",
                    lum.shape == tuple(int(s) for s in vol.shape[1:]),
                    f"img={lum.shape}, expected={vol.shape[1:]}")
    else:
        c.check("real unitcell.npy is 3D", False, f"ndim={vol.ndim}")
else:
    c.check("real unitcell.npy present", False, "file missing (skipped)")

finish(c.done())
