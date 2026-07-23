#!/usr/bin/env python3
"""Try malformed paths, dimensions, selectors, ranges, and output paths."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

from _harness import Checker, load_visualize


def expect_error(checker: Checker, name: str, function, *args) -> None:
    try:
        result = function(*args)
    except Exception as exc:  # noqa: BLE001 - adversarial test demands no exception
        checker.check(name, False, f"raised {type(exc).__name__}: {exc}")
        return
    checker.check(name, isinstance(result, str) and result.startswith("Error:"), repr(result))


def main() -> int:
    checker = Checker("02 — malformed inputs must return Error, not crash")
    visualize, _ = load_visualize()
    with tempfile.TemporaryDirectory(prefix="task2_invalid_") as temporary:
        work = Path(temporary)
        valid = work / "valid.npy"
        two_d = work / "two_d.npy"
        complex_volume = work / "complex.npy"
        all_nan = work / "all_nan.npy"
        archive = work / "volume.npz"
        np.save(valid, np.ones((2, 3, 4), dtype=np.float32))
        np.save(two_d, np.ones((3, 4), dtype=np.float32))
        np.save(complex_volume, np.ones((2, 3, 4), dtype=np.complex64))
        np.save(all_nan, np.full((2, 3, 4), np.nan, dtype=np.float32))
        np.savez(archive, volume=np.ones((2, 3, 4), dtype=np.float32))

        expect_error(checker, "missing input path", visualize, str(work / "missing.npy"), str(work / "out"), 0, 0)
        expect_error(checker, "non-3D array", visualize, str(two_d), str(work / "out"), 0, 0)
        expect_error(checker, "NPZ archive", visualize, str(archive), str(work / "out"), 0, 0)
        expect_error(checker, "complex-valued volume", visualize, str(complex_volume), str(work / "out"), 0, 0)
        expect_error(checker, "volume with no finite values", visualize, str(all_nan), str(work / "out"), 0, 0)
        expect_error(checker, "axis outside 0..2", visualize, str(valid), str(work / "out"), 0, 3)
        expect_error(checker, "negative axis", visualize, str(valid), str(work / "out"), 0, -1)
        expect_error(checker, "non-integer axis", visualize, str(valid), str(work / "out"), 0, 1.0)
        expect_error(checker, "slice index outside axis size", visualize, str(valid), str(work / "out"), 2, 0)
        expect_error(checker, "negative slice index", visualize, str(valid), str(work / "out"), -1, 0)
        expect_error(checker, "non-integer slice index", visualize, str(valid), str(work / "out"), 0.0, 0)
        expect_error(checker, "empty output path", visualize, str(valid), "", 0, 0)
        expect_error(checker, "non-PNG output extension", visualize, str(valid), str(work / "out.jpg"), 0, 0)
    return checker.done()


if __name__ == "__main__":
    sys.exit(main())
