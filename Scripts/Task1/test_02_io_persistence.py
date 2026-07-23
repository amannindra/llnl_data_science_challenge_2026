"""
ATTACK #2 — I/O & PERSISTENCE integrity.

Goal: prove the function lies about where it saved, corrupts dtype/shape, fails
when the output directory doesn't exist, leaves stale data on overwrite, or
that the returned path doesn't point at the real file. The np.save ".npy"
auto-append is a common way for the reported path to diverge from reality.
"""
import hashlib
import os
import tempfile

import numpy as np

from _harness import Checker, load_segment, finish

segment, _ = load_segment()
c = Checker("I/O & persistence (path honesty, dtype/shape, dirs, overwrite)")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "in.npy")
    vol = (np.random.default_rng(1).random((20, 18, 16)) - 0.5).astype(np.float32)
    np.save(inp, vol)

    # 1) Path WITHOUT .npy: numpy appends it. The reported path must point at the
    #    file that actually exists on disk (no silent divergence).
    out_noext = os.path.join(tmp, "result_noext")
    msg = segment(inp, out_noext, 0.0)
    real_file = out_noext + ".npy"
    c.check("no-extension output: file actually exists at path+'.npy'",
            os.path.exists(real_file))
    c.check("returned message names the real saved path",
            real_file in msg, f"msg={msg!r}")

    # 2) Path WITH .npy is used verbatim (no double extension).
    out_ext = os.path.join(tmp, "result.npy")
    segment(inp, out_ext, 0.0)
    c.check("with-extension output exists, no double .npy",
            os.path.exists(out_ext) and not os.path.exists(out_ext + ".npy"))

    # 3) dtype and shape are preserved / correct.
    saved = np.load(out_ext)
    c.check("dtype is uint8", saved.dtype == np.uint8, str(saved.dtype))
    c.check("shape preserved (3D)", saved.shape == vol.shape, str(saved.shape))

    # 4) Round-trip equals the expected mask exactly.
    c.check("round-trip load == (data >= thr)",
            np.array_equal(saved, (vol >= 0.0).astype(np.uint8)))

    # 5) Nested, non-existent output directory is created automatically.
    nested = os.path.join(tmp, "a", "b", "c", "deep.npy")
    segment(inp, nested, 0.2)
    c.check("auto-creates nested output directories", os.path.exists(nested))

    # 6) Overwrite must not leave stale content from a previous run.
    ow = os.path.join(tmp, "ow.npy")
    segment(inp, ow, -10.0)            # threshold below all -> all ones
    first = np.load(ow)
    segment(inp, ow, 10.0)             # threshold above all -> all zeros
    second = np.load(ow)
    c.check("overwrite reflects the NEW threshold (no stale data)",
            first.sum() == first.size and second.sum() == 0,
            f"first={int(first.sum())}, second={int(second.sum())}")

    # 7) The INPUT file bytes are untouched across many segmentations.
    h0 = sha(inp)
    for thr in (-1, 0, 1):
        segment(inp, os.path.join(tmp, f"s{thr}.npy"), thr)
    c.check("input file bytes unchanged", sha(inp) == h0)

finish(c.done())
