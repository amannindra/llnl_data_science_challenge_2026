#!/usr/bin/env python3
"""Try to break Task 1 with malformed paths, arrays, and thresholds."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

from _harness import Checker, load_segment


def call_as_error(checker: Checker, name: str, function, *args) -> None:
    """A public MCP tool must return an Error string, never raise, for bad input."""
    try:
        result = function(*args)
    except Exception as exc:  # noqa: BLE001 - this is an adversarial test
        checker.check(name, False, f"raised {type(exc).__name__}: {exc}")
        return
    checker.check(name, isinstance(result, str) and result.startswith("Error:"), repr(result))


def main() -> int:
    checker = Checker("02 — malformed volume and threshold inputs")
    segment, _ = load_segment()
    with tempfile.TemporaryDirectory(prefix="task1_invalid_") as temporary:
        work = Path(temporary)
        two_d = work / "two_d.npy"
        scalar = work / "scalar.npy"
        archive = work / "archive.npz"
        object_array = work / "object.npy"
        valid = work / "valid.npy"
        np.save(two_d, np.ones((2, 2), dtype=np.float32))
        np.save(scalar, np.array(1.0, dtype=np.float32))
        np.savez(archive, volume=np.ones((2, 2, 2), dtype=np.float32))
        np.save(object_array, np.array([[["not-a-number"]]], dtype=object))
        np.save(valid, np.ones((2, 2, 2), dtype=np.float32))

        call_as_error(checker, "missing input path returns Error", segment, str(work / "missing.npy"), str(work / "out"), 0.5)
        call_as_error(checker, "2D array is rejected as not a CT volume", segment, str(two_d), str(work / "two_d_out"), 0.5)
        call_as_error(checker, "scalar array is rejected as not a CT volume", segment, str(scalar), str(work / "scalar_out"), 0.5)
        call_as_error(checker, "NPZ archive is rejected as not one array", segment, str(archive), str(work / "archive_out"), 0.5)
        call_as_error(checker, "object array is rejected without pickle loading", segment, str(object_array), str(work / "object_out"), 0.5)
        call_as_error(checker, "NaN threshold is rejected", segment, str(valid), str(work / "nan_out"), float("nan"))
        call_as_error(checker, "infinite threshold is rejected", segment, str(valid), str(work / "inf_out"), float("inf"))
    return checker.done()


if __name__ == "__main__":
    sys.exit(main())
