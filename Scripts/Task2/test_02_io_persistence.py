"""
ATTACK #2 — I/O & PERSISTENCE integrity.

Goal: prove visualize_slice lies about where it saved, writes an unreadable or
empty file, fails to create missing directories, leaves a stale image on
overwrite, mutates the input .npy, or mishandles the output extension (missing
extension, or the wrong format).
"""
import hashlib
import os
import tempfile

import numpy as np

from _harness import Checker, load_visualize, read_luminance, finish

visualize, _ = load_visualize()
c = Checker("I/O & persistence (path honesty, formats, dirs, overwrite)")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def is_readable_image(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


with tempfile.TemporaryDirectory() as tmp:
    inp = os.path.join(tmp, "vol.npy")
    vol = np.random.default_rng(2).standard_normal((12, 10, 8)).astype(np.float32)
    np.save(inp, vol)

    # 1) No extension -> tool appends .png; reported path must be the real file.
    out_noext = os.path.join(tmp, "noext")
    msg = visualize(inp, out_noext, 3)
    real = out_noext + ".png"
    c.check("no-extension output saved at path+'.png'", os.path.exists(real))
    c.check("message names the real saved path", real in msg, f"msg={msg!r}")
    c.check("appended-.png file is a valid, non-empty image",
            is_readable_image(real) and os.path.getsize(real) > 0)

    # 2) Explicit .png is used verbatim (no double extension).
    out_png = os.path.join(tmp, "explicit.png")
    visualize(inp, out_png, 3)
    c.check("explicit .png used verbatim (no double extension)",
            os.path.exists(out_png) and not os.path.exists(out_png + ".png"))

    # 3) Other image formats are honored via the extension.
    for ext in ("jpg", "tif", "bmp"):
        op = os.path.join(tmp, f"pic.{ext}")
        r = visualize(inp, op, 3)
        c.check(f".{ext} output is written and readable",
                os.path.exists(op) and is_readable_image(op),
                f"ret={r!r}")

    # 4) Nested, non-existent output directory is created automatically.
    nested = os.path.join(tmp, "x", "y", "z", "deep.png")
    visualize(inp, nested, 4)
    c.check("auto-creates nested output directories",
            os.path.exists(nested) and is_readable_image(nested))

    # 5) Overwrite must reflect the NEW slice, not stale pixels.
    ow = os.path.join(tmp, "ow.png")
    visualize(inp, ow, 0)
    first = read_luminance(ow)
    visualize(inp, ow, 9)
    second = read_luminance(ow)
    c.check("overwrite reflects the new slice (no stale image)",
            first.shape == second.shape and not np.array_equal(first, second))

    # 6) The INPUT .npy bytes are untouched across many visualizations.
    h0 = sha(inp)
    for axis in (0, 1, 2):
        for idx in (0, 1, 2):
            visualize(inp, os.path.join(tmp, f"s_{axis}_{idx}.png"), idx, axis)
    c.check("input .npy bytes unchanged after many renders", sha(inp) == h0)

    # 7) Round-trip: a saved PNG reads back at the expected 2D resolution.
    rt = os.path.join(tmp, "rt.png")
    visualize(inp, rt, 5, 2)               # axis 2 -> slice shape (12, 10)
    c.check("saved PNG reads back at the slice resolution",
            read_luminance(rt).shape == (12, 10))

finish(c.done())
