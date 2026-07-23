#!/usr/bin/env python3
"""Try to disprove Task 2's axis/index selection and pixel-scaling contract."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from _harness import Checker, load_visualize


def expected_gray(reference: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """The gray colormap quantizes normalized values to 8-bit PNG samples."""
    return np.rint(np.clip((reference - vmin) / (vmax - vmin), 0, 1) * 255).astype(np.int16)


def main() -> int:
    checker = Checker("01 — all axes, exact selected plane, and PNG pixel scaling")
    visualize, _ = load_visualize()
    volume = np.arange(3 * 4 * 5, dtype=np.float32).reshape(3, 4, 5)
    vmin, vmax = float(volume.min()), float(volume.max())
    cases = ((0, 1, "axis_0"), (1, 2, "axis_1.png"), (2, 3, "axis_2.png"))

    with tempfile.TemporaryDirectory(prefix="task2_axes_") as temporary:
        work = Path(temporary)
        source = work / "volume.npy"
        np.save(source, volume)
        before = np.load(source)
        for axis, index, output_name in cases:
            requested = work / "renders" / output_name
            status = visualize(str(source), str(requested), index, axis)
            output = requested if requested.suffix else requested.with_suffix(".png")
            expected_plane = np.take(volume, index, axis=axis)
            checker.check(f"axis {axis}: success status", isinstance(status, str) and not status.startswith("Error:"), status)
            checker.check(f"axis {axis}: PNG exists", output.is_file(), str(output))
            if output.is_file():
                rgba = np.asarray(Image.open(output).convert("RGBA"))
                actual_gray = rgba[..., 0].astype(np.int16)
                expected = expected_gray(expected_plane, vmin, vmax)
                checker.check(f"axis {axis}: image dimensions equal selected plane", actual_gray.shape == expected_plane.shape, str(actual_gray.shape))
                checker.check(f"axis {axis}: every grayscale pixel encodes the selected plane", np.max(np.abs(actual_gray - expected)) <= 1, f"max_error={np.max(np.abs(actual_gray - expected))}")
                checker.check(f"axis {axis}: image is opaque grayscale", np.array_equal(rgba[..., 0], rgba[..., 1]) and np.array_equal(rgba[..., 1], rgba[..., 2]) and np.all(rgba[..., 3] == 255))
            else:
                for name in ("image dimensions equal selected plane", "every grayscale pixel encodes the selected plane", "image is opaque grayscale"):
                    checker.check(f"axis {axis}: {name}", False, "PNG was not created")
        checker.check("source NumPy volume remains unchanged", np.array_equal(before, np.load(source)))
    return checker.done()


if __name__ == "__main__":
    sys.exit(main())
