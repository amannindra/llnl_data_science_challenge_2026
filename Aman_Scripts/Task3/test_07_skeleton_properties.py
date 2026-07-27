"""
ATTACK #7 — Structural properties a real skeleton must obey.

A skeleton is a thinned subset of the mask: every skeleton voxel must be inside
the original foreground, it must never have MORE voxels than the mask, it must
keep the same shape, and it must be boolean.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, _ = load_skeletonize()
c = Checker("Skeleton properties (subset of mask, thinner, boolean, same shape)")

with tempfile.TemporaryDirectory() as tmp:
    mask = cross_mask(24).astype(np.uint8)
    # thicken the bars so skeletonization has something to thin
    mask[:, 11:14, 11:14] = 1
    mask[11:14, :, 11:14] = 1
    mask[11:14, 11:14, :] = 1
    inp = os.path.join(tmp, "m.npy")
    out = os.path.join(tmp, "s.npy")
    np.save(inp, mask)

    skeletonize(inp, out)
    skel = np.load(out)
    fg = mask > 0

    c.check("skeleton dtype is boolean", skel.dtype == bool, str(skel.dtype))
    c.check("skeleton shape equals mask shape", skel.shape == mask.shape, str(skel.shape))
    c.check("every skeleton voxel lies inside the mask (subset)",
            bool(np.all(fg[skel])))
    c.check("skeleton has no more voxels than the mask",
            int(skel.sum()) <= int(fg.sum()),
            f"skel={int(skel.sum())}, fg={int(fg.sum())}")
    c.check("skeleton is genuinely thinner than the (thickened) mask",
            0 < int(skel.sum()) < int(fg.sum()),
            f"skel={int(skel.sum())}, fg={int(fg.sum())}")

finish(c.done())
