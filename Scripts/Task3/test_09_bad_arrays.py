"""
ATTACK #9 — Hostile array payloads (must return Error, never crash the server).

Non-numeric arrays, pickled/object arrays, corrupt .npy bytes, and arrays with
the wrong number of dimensions (1D/4D that skimage rejects) must all come back
as "Error:" strings. NaN/inf in a float mask must NOT error (it's just (>0)).
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_skeletonize, finish

skeletonize, _ = load_skeletonize()
c = Checker("Hostile arrays (rejected as Error strings, no crash)")


def safe(*a):
    try:
        return skeletonize(*a), None
    except Exception as e:  # noqa: BLE001
        return None, e


def is_err(r):
    return isinstance(r, str) and r.lower().startswith("error")


with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "out.npy")
    p = os.path.join(tmp, "in.npy")

    # 1) Non-numeric (string) array.
    np.save(p, np.array([["a", "b"], ["c", "d"]]))
    r, e = safe(p, out)
    c.check("string array -> Error (no raise)", e is None and is_err(r), f"r={r!r}, e={e!r}")

    # 2) Pickled/object array (np.load defaults to allow_pickle=False).
    op = os.path.join(tmp, "obj.npy")
    np.save(op, np.array([{"x": 1}, [1, 2]], dtype=object), allow_pickle=True)
    r, e = safe(op, out)
    c.check("object/pickled array -> Error (no unsafe load)", e is None and is_err(r), f"r={r!r}")

    # 3) Corrupt / non-npy bytes.
    cp = os.path.join(tmp, "corrupt.npy")
    with open(cp, "wb") as f:
        f.write(b"this is not a numpy file at all")
    r, e = safe(cp, out)
    c.check("corrupt .npy -> Error (no raise)", e is None and is_err(r), f"r={r!r}")

    # 4) 1D array (skimage skeletonize needs 2D/3D).
    np.save(p, np.arange(10, dtype=np.uint8))
    r, e = safe(p, out)
    c.check("1D array -> Error (no raise)", e is None and is_err(r), f"r={r!r}")

    # 5) 4D array (skimage rejects).
    np.save(p, np.ones((3, 3, 3, 3), np.uint8))
    r, e = safe(p, out)
    c.check("4D array -> Error (no raise)", e is None and is_err(r), f"r={r!r}")

    # 6) NaN/inf float mask -> NOT an error (>0 handles it), no crash.
    fm = np.zeros((12, 12, 12), np.float64)
    fm[:, 6, 6] = np.inf
    fm[6, :, 6] = np.nan
    fm[6, 6, :] = 1.0
    np.save(p, fm)
    good = os.path.join(tmp, "good.npy")
    r, e = safe(p, good)
    c.check("NaN/inf float mask succeeds (no crash)",
            e is None and isinstance(r, str) and not is_err(r) and os.path.exists(good),
            f"r={r!r}, e={e!r}")

finish(c.done())
