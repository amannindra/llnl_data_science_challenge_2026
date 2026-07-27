"""
ATTACK #3 — EDGE & ERROR robustness.

Goal: prove the function crashes (uncaught exception) or produces nonsense on
inputs an agent will realistically throw at it: a missing file, thresholds
outside the data range (the real unitcell.npy value-range trap), NaN/inf voxels,
empty arrays, non-3D arrays, integer data, string thresholds, and non-numeric
or pickled arrays. Per the docstring, expected failures must be returned as an
"Error: ..." STRING, never raised.
"""
import os
import tempfile

import numpy as np

from _harness import Checker, load_segment, finish, ROOT

segment, _ = load_segment()
c = Checker("Edge & error cases (must return strings, never crash)")


def safe(*args):
    """Call segment; capture a raised exception as a sentinel instead of dying."""
    try:
        return segment(*args), None
    except Exception as e:  # noqa: BLE001
        return None, e


with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "out.npy")

    # 1) Missing input file -> Error string, no exception, no output written.
    ret, exc = safe(os.path.join(tmp, "does_not_exist.npy"), out, 0.5)
    c.check("missing input returns Error string (no raise)",
            exc is None and isinstance(ret, str) and ret.lower().startswith("error"),
            f"ret={ret!r}, exc={exc!r}")
    c.check("missing input wrote no output file", not os.path.exists(out))

    # 2) Threshold ABOVE all data (the unitcell.npy trap: values ~<=0.015, thr=0.5).
    inp = os.path.join(tmp, "small.npy")
    np.save(inp, np.linspace(-0.003, 0.015, 1000).astype(np.float32))
    ret, exc = safe(inp, out, 0.5)
    c.check("threshold above all data -> valid all-zero mask (no crash)",
            exc is None and os.path.exists(out) and int(np.load(out).sum()) == 0,
            f"ret={ret!r}")

    # 3) Threshold BELOW all data -> all ones.
    ret, exc = safe(inp, out, -1.0)
    c.check("threshold below all data -> all-one mask",
            exc is None and int(np.load(out).sum()) == np.load(out).size)

    # 4) NaN voxels -> 0 (NaN >= t is False); function must not crash.
    nanarr = np.array([0.0, np.nan, 1.0, np.nan, 2.0], dtype=np.float64)
    np.save(inp, nanarr)
    ret, exc = safe(inp, out, 0.5)
    c.check("NaN voxels become 0, others correct",
            exc is None and np.load(out).tolist() == [0, 0, 1, 0, 1], f"ret={ret!r}")

    # 5) +/- inf voxels handled: +inf>=t -> 1, -inf>=t -> 0.
    infarr = np.array([-np.inf, 0.0, np.inf], dtype=np.float64)
    np.save(inp, infarr)
    ret, exc = safe(inp, out, 0.5)
    c.check("inf voxels handled (+inf->1, -inf->0)",
            exc is None and np.load(out).tolist() == [0, 0, 1])

    # 6) Empty array -> no ZeroDivision on the percentage, valid empty mask.
    np.save(inp, np.array([], dtype=np.float32))
    ret, exc = safe(inp, out, 0.5)
    c.check("empty array does not crash (no div-by-zero)",
            exc is None and isinstance(ret, str) and not ret.lower().startswith("error"),
            f"ret={ret!r}")

    # 7) 2D array (non-3D) still thresholds fine (dimension-agnostic).
    np.save(inp, np.eye(5, dtype=np.float32))
    ret, exc = safe(inp, out, 0.5)
    c.check("2D array segmented correctly",
            exc is None and np.array_equal(np.load(out), np.eye(5, dtype=np.uint8)))

    # 8) Integer input data with a float threshold.
    np.save(inp, np.arange(10, dtype=np.int64))
    ret, exc = safe(inp, out, 4.5)
    c.check("integer data + float threshold",
            exc is None and np.load(out).tolist() == [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])

    # 9) Threshold passed as a numeric STRING (agents/JSON can do this).
    np.save(inp, np.arange(5, dtype=np.float32))
    ret, exc = safe(inp, out, "2")
    c.check("string-numeric threshold coerced",
            exc is None and np.load(out).tolist() == [0, 0, 1, 1, 1], f"ret={ret!r}")

    # 10) Non-finite threshold -> Error string.
    ret, exc = safe(inp, out, float("nan"))
    c.check("NaN threshold rejected with Error string",
            exc is None and isinstance(ret, str) and ret.lower().startswith("error"),
            f"ret={ret!r}")

    # 11) Non-numeric array (strings) -> Error string, not a crash.
    np.save(inp, np.array(["a", "b", "c"]))
    ret, exc = safe(inp, out, 0.5)
    c.check("non-numeric array rejected with Error string",
            exc is None and isinstance(ret, str) and ret.lower().startswith("error"),
            f"ret={ret!r}")

    # 12) Pickled/object array -> load with allow_pickle=False must be caught.
    obj = os.path.join(tmp, "obj.npy")
    np.save(obj, np.array([{"x": 1}, [1, 2]], dtype=object), allow_pickle=True)
    ret, exc = safe(obj, out, 0.5)
    c.check("object/pickled array rejected with Error string (no unsafe load)",
            exc is None and isinstance(ret, str) and ret.lower().startswith("error"),
            f"ret={ret!r}")

finish(c.done())
