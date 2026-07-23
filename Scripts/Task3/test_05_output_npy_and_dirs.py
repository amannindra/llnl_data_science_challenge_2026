"""
ATTACK #5 — Output path honesty & directory creation.

np.save appends ".npy" unless the path already ends in ".npy" (so "x", "x.dat"
BOTH become "*.npy"). The wrapper's reported path must equal the file that
actually lands on disk. Also: skeletonize_mask does NOT create missing
directories, so the wrapper must.
"""
import contextlib
import io
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, cross_mask, finish

skeletonize, mod = load_skeletonize()
c = Checker("Output path honesty (.npy append) + auto directory creation")


def saved_path_from(msg):
    # "Saved skeleton to <path> (..."
    return msg.split("Saved skeleton to ", 1)[1].split(" (", 1)[0] if "Saved skeleton to " in msg else ""


with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "m.npy")
    np.save(inp, cross_mask(18))

    # 1) No extension -> file at path+'.npy', and the message names it.
    out1 = os.path.join(tmp, "noext")
    m1 = skeletonize(inp, out1)
    c.check("no-extension output saved at path+'.npy'", os.path.exists(out1 + ".npy"))
    c.check("message names the real saved path (no-ext)",
            saved_path_from(m1) == out1 + ".npy" and os.path.exists(saved_path_from(m1)),
            f"reported={saved_path_from(m1)!r}")

    # 2) Explicit .npy used verbatim (no double extension).
    out2 = os.path.join(tmp, "explicit.npy")
    skeletonize(inp, out2)
    c.check("explicit .npy used verbatim (no double)",
            os.path.exists(out2) and not os.path.exists(out2 + ".npy"))

    # 3) NON-.npy extension: np.save STILL appends .npy -> reported path must match.
    out3 = os.path.join(tmp, "skel.dat")
    m3 = skeletonize(inp, out3)
    reported3 = saved_path_from(m3)
    c.check("non-.npy extension: reported path is the file that exists",
            os.path.exists(reported3),
            f"reported={reported3!r}, exists={os.path.exists(reported3)}, "
            f"dat.npy={os.path.exists(out3 + '.npy')}")

    # 4) Nested missing directory: wrapper must create it.
    nested = os.path.join(tmp, "a", "b", "c", "deep.npy")
    skeletonize(inp, nested)
    c.check("auto-creates nested output directories", os.path.exists(nested))

    # Contrast: skeletonize_mask ALONE fails on a missing dir (why the wrapper matters).
    raised = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mod.skeletonize_mask(inp, os.path.join(tmp, "no_such_dir", "z.npy"))
    except Exception:
        raised = True
    c.check("skeletonize_mask alone fails on a missing dir (wrapper adds creation)", raised)

finish(c.done())
