#!/usr/bin/env python3
"""Deterministic adversarial checks for ``Components.segmentation``."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Scripts.Components.segmentation import (  # noqa: E402
    SegmentationError,
    apply_mask,
    normalize_mask,
    summarize_mask,
    threshold_mask,
    validate_binary_mask,
    validate_numeric_volume,
)


class Checker:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        passed = bool(condition)
        self.results.append({"name": name, "passed": passed, "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    def raises(self, name: str, exception: type[BaseException], function) -> None:
        try:
            function()
        except exception:
            self.check(name, True)
        except Exception as exc:  # noqa: BLE001 - report wrong exception
            self.check(name, False, f"wrong exception {type(exc).__name__}: {exc}")
        else:
            self.check(name, False, "no exception")

    def finish(self) -> int:
        passed = sum(bool(item["passed"]) for item in self.results)
        summary = {"suite": "segmentation", "passed": passed, "failed": len(self.results) - passed,
                   "total": len(self.results), "results": self.results}
        print(json.dumps(summary, sort_keys=True))
        return 0 if passed == len(self.results) and len(self.results) >= 12 else 1


def main() -> int:
    checks = Checker()

    values = np.array([-1.0, 0.499999, 0.5, 0.500001, np.nan], dtype=np.float64)
    original = values.copy()
    mask = threshold_mask(values, 0.5)
    checks.check("threshold uses inclusive >= semantics", mask.tolist() == [0, 0, 1, 1, 0])
    checks.check("threshold output defaults to uint8", mask.dtype == np.uint8)
    checks.check("thresholding never mutates the source", np.array_equal(values, original, equal_nan=True))
    checks.check("boolean output dtype is supported", threshold_mask(values, 0.5, output_dtype=bool).dtype == np.bool_)

    integers = np.array([-2, -1, 0, 1, 2], dtype=np.int16)
    checks.check("integer volumes accept fractional thresholds",
                 threshold_mask(integers, -0.5).tolist() == [0, 0, 1, 1, 1])
    infinities = np.array([-np.inf, 0.0, np.inf])
    checks.check("finite threshold handles infinite voxels deterministically",
                 threshold_mask(infinities, 0).tolist() == [0, 1, 1])
    checks.raises("NaN threshold is rejected", SegmentationError,
                  lambda: threshold_mask(values, np.nan))
    checks.raises("infinite threshold is rejected", SegmentationError,
                  lambda: threshold_mask(values, np.inf))
    checks.raises("complex-valued volume is rejected", SegmentationError,
                  lambda: threshold_mask(np.array([1 + 2j]), 0))
    checks.raises("floating mask output dtype is rejected", SegmentationError,
                  lambda: threshold_mask(values, 0, output_dtype=np.float32))
    checks.raises("optional 3D requirement rejects vectors", SegmentationError,
                  lambda: threshold_mask(values, 0, require_3d=True))

    encoded = np.array([[[0, 255], [255, 0]]], dtype=np.uint8)
    normalized = normalize_mask(encoded)
    checks.check("0/255 mask normalizes to literal 0/1", normalized.tolist() == [[[0, 1], [1, 0]]])
    checks.check("normalization returns a fresh array", not np.shares_memory(encoded, normalized))
    signed = np.array([-3.0, 0.0, 2.0, np.nan])
    checks.check("default normalization is finite-nonzero foreground",
                 normalize_mask(signed).tolist() == [1, 0, 1, 0])
    labels = np.array([0, 1, 2, 3, 2])
    checks.check("explicit label selection is exact",
                 normalize_mask(labels, foreground_values=(2, 3)).tolist() == [0, 0, 1, 1, 1])
    checks.raises("empty foreground label selection is rejected", SegmentationError,
                  lambda: normalize_mask(labels, foreground_values=()))
    checks.raises("nonnumeric masks are rejected", SegmentationError,
                  lambda: normalize_mask(np.array(["background", "foreground"])))

    volume = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    volume_summary = validate_numeric_volume(volume)
    checks.check("3D volume validation reports shape and size",
                 volume_summary.shape == (2, 3, 4) and volume_summary.size == 24)
    nonfinite_summary = validate_numeric_volume(np.array([[[1.0, np.nan, np.inf]]]))
    checks.check("volume validation counts non-finite voxels",
                 nonfinite_summary.finite_count == 1 and nonfinite_summary.nonfinite_count == 2)
    checks.raises("strict finite validation rejects NaN/inf", SegmentationError,
                  lambda: validate_numeric_volume(np.array([[[np.nan]]]), require_finite=True))
    checks.raises("3D volume validation rejects 2D arrays", SegmentationError,
                  lambda: validate_numeric_volume(np.zeros((3, 3))))
    checks.raises("volume validation rejects empty arrays by default", SegmentationError,
                  lambda: validate_numeric_volume(np.empty((0, 2, 2))))
    empty_summary = validate_numeric_volume(np.empty((0, 2, 2)), allow_empty=True)
    checks.check("empty volume can be allowed explicitly", empty_summary.size == 0)

    mask_summary = validate_binary_mask(encoded)
    checks.check("binary mask validation accepts project 0/255 encoding",
                 mask_summary.foreground_count == 2 and mask_summary.background_count == 2)
    all_foreground = validate_binary_mask(np.full((1, 2, 2), 255, dtype=np.uint8))
    checks.check("constant valid binary masks are accepted", all_foreground.foreground_fraction == 1.0)
    checks.raises("binary validation rejects arbitrary labels", SegmentationError,
                  lambda: validate_binary_mask(np.array([[[0, 2]]], dtype=np.uint8)))
    checks.raises("binary validation rejects non-finite values", SegmentationError,
                  lambda: validate_binary_mask(np.array([[[0.0, np.nan]]])))
    checks.raises("binary validation enforces 3D by default", SegmentationError,
                  lambda: validate_binary_mask(np.array([[0, 1]])))

    summary = summarize_mask(encoded)
    checks.check("mask summary reports source values", summary.source_values == (0, 255))
    checks.raises("mask summary catches raw high-cardinality arrays", SegmentationError,
                  lambda: summarize_mask(np.arange(20), max_source_values=4))

    masked = apply_mask(np.array([1, 2, 3]), np.array([0, 255, 0]), fill_value=-1)
    checks.check("apply_mask respects normalized mask semantics", masked.tolist() == [-1, 2, -1])
    checks.raises("apply_mask rejects shape mismatch", SegmentationError,
                  lambda: apply_mask(np.ones((2, 2)), np.ones((2, 3))))

    rng = np.random.default_rng(20260724)
    random_volume = rng.normal(size=(9, 8, 7)).astype(np.float32)
    random_threshold = 0.173
    checks.check("random fixture exactly matches independent NumPy ground truth",
                 np.array_equal(threshold_mask(random_volume, random_threshold),
                                (random_volume >= random_threshold).astype(np.uint8)))
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())

