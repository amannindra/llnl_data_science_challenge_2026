#!/usr/bin/env python3
"""Try to disprove Task 1's documented >= threshold segmentation contract."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

from _harness import Checker, load_segment


def main() -> int:
    checker = Checker("01 — threshold boundary, NaN/Inf, and source preservation")
    segment, _ = load_segment()
    volume = np.array(
        [[[-1.0, 0.0], [0.4999, 0.5]], [[0.5, 1.0], [np.nan, np.inf]]],
        dtype=np.float32,
    )
    threshold = 0.5
    expected = np.array(
        [[[0, 0], [0, 1]], [[1, 1], [0, 1]]], dtype=np.uint8
    )

    with tempfile.TemporaryDirectory(prefix="task1_boundary_") as temporary:
        work = Path(temporary)
        source = work / "source.npy"
        requested_output = work / "nested" / "boundary_mask"  # no suffix on purpose
        np.save(source, volume)
        before = np.load(source)

        status = segment(str(source), str(requested_output), threshold)
        output = requested_output.with_suffix(".npy")
        checker.check("tool returned a success string", isinstance(status, str) and not status.startswith("Error"), status)
        checker.check("np.save suffix was added", output.is_file(), str(output))
        if output.is_file():
            actual = np.load(output)
            checker.check("output is literal uint8 0/1", actual.dtype == np.uint8 and set(np.unique(actual)) <= {0, 1}, str(actual.dtype))
            checker.check("shape is preserved", actual.shape == volume.shape, str(actual.shape))
            checker.check("threshold equality uses >=", np.array_equal(actual, expected), repr(actual.tolist()))
        else:
            checker.check("output is literal uint8 0/1", False, "output was not created")
            checker.check("shape is preserved", False, "output was not created")
            checker.check("threshold equality uses >=", False, "output was not created")
        after = np.load(source)
        checker.check("source file remains unchanged", np.array_equal(before, after, equal_nan=True))
        checker.check("status reports the expected foreground count", "foreground=4/8" in status, status)
    return checker.done()


if __name__ == "__main__":
    sys.exit(main())
