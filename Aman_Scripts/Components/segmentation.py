"""Pure, reusable helpers for numeric-volume thresholding and binary masks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np


class SegmentationError(ValueError):
    """Raised when a volume, threshold, mask, or output dtype is invalid."""


@dataclass(frozen=True)
class VolumeSummary:
    """Validation metadata for a numeric array."""

    shape: tuple[int, ...]
    dtype: str
    ndim: int
    size: int
    finite_count: int
    nonfinite_count: int


@dataclass(frozen=True)
class MaskSummary:
    """Normalized binary-mask counts; foreground semantics are explicit."""

    shape: tuple[int, ...]
    source_dtype: str
    foreground_count: int
    background_count: int
    foreground_fraction: float
    source_values: tuple[float | int | bool, ...]


def _numeric_array(array: Any, context: str) -> np.ndarray:
    result = np.asanyarray(array)
    if not (np.issubdtype(result.dtype, np.number) or np.issubdtype(result.dtype, np.bool_)):
        raise SegmentationError(f"{context} must have a numeric or boolean dtype, got {result.dtype}")
    if np.issubdtype(result.dtype, np.complexfloating):
        raise SegmentationError(f"{context} must be real-valued, got {result.dtype}")
    return result


def _output_dtype(dtype: Any) -> np.dtype[Any]:
    try:
        resolved = np.dtype(dtype)
    except (TypeError, ValueError) as exc:
        raise SegmentationError(f"invalid mask output dtype {dtype!r}") from exc
    if not (np.issubdtype(resolved, np.integer) or np.issubdtype(resolved, np.bool_)):
        raise SegmentationError("mask output dtype must be integer or boolean")
    return resolved


def validate_numeric_volume(
    volume: Any,
    *,
    require_3d: bool = True,
    allow_empty: bool = False,
    require_finite: bool = False,
) -> VolumeSummary:
    """Validate a real numeric array and return deterministic metadata.

    Validation never copies or mutates the input.  Non-finite voxels are allowed
    by default because threshold comparison naturally maps NaN to background;
    callers that need quantitative intensity statistics can opt into strictness.
    """

    array = _numeric_array(volume, "volume")
    if require_3d and array.ndim != 3:
        raise SegmentationError(f"volume must be 3D, got shape {array.shape}")
    if not allow_empty and array.size == 0:
        raise SegmentationError("volume must not be empty")
    if np.issubdtype(array.dtype, np.inexact):
        finite_count = int(np.count_nonzero(np.isfinite(array)))
    else:
        finite_count = int(array.size)
    nonfinite_count = int(array.size) - finite_count
    if require_finite and nonfinite_count:
        raise SegmentationError(f"volume contains {nonfinite_count} non-finite voxel(s)")
    return VolumeSummary(
        tuple(int(value) for value in array.shape), str(array.dtype), int(array.ndim),
        int(array.size), finite_count, nonfinite_count,
    )


def threshold_mask(
    volume: Any,
    threshold: Any,
    *,
    output_dtype: Any = np.uint8,
    require_3d: bool = False,
) -> np.ndarray:
    """Return ``volume >= threshold`` as a new binary array.

    Equality is foreground, matching Task 1.  NaN compares false and therefore
    becomes background.  The input is never modified.
    """

    array = _numeric_array(volume, "volume")
    if require_3d and array.ndim != 3:
        raise SegmentationError(f"volume must be 3D, got shape {array.shape}")
    try:
        cutoff = float(threshold)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SegmentationError("threshold must be a finite real number") from exc
    if not math.isfinite(cutoff):
        raise SegmentationError("threshold must be a finite real number")
    dtype = _output_dtype(output_dtype)
    return np.asarray(array >= cutoff, dtype=dtype)


def normalize_mask(
    mask: Any,
    *,
    output_dtype: Any = np.uint8,
    foreground_values: Iterable[Any] | None = None,
    require_3d: bool = False,
) -> np.ndarray:
    """Normalize a mask to literal 0/1 without mutating the source.

    By default every finite nonzero value is foreground, covering bool, 0/1,
    and the project's 0/255 TIFF encoding.  ``foreground_values`` switches to
    exact membership semantics for labeled masks.  NaN is always background.
    """

    array = _numeric_array(mask, "mask")
    if require_3d and array.ndim != 3:
        raise SegmentationError(f"mask must be 3D, got shape {array.shape}")
    dtype = _output_dtype(output_dtype)
    if foreground_values is None:
        selected = array != 0
        if np.issubdtype(array.dtype, np.inexact):
            selected = selected & np.isfinite(array)
    else:
        values = tuple(foreground_values)
        if not values:
            raise SegmentationError("foreground_values must not be empty")
        selected = np.isin(array, values)
        if np.issubdtype(array.dtype, np.inexact):
            selected = selected & np.isfinite(array)
    return np.asarray(selected, dtype=dtype)


def summarize_mask(
    mask: Any,
    *,
    foreground_values: Iterable[Any] | None = None,
    require_3d: bool = False,
    max_source_values: int = 256,
) -> MaskSummary:
    """Validate, normalize, and summarize a small or already-binary mask.

    The unique-value cap prevents accidental, misleading summaries of raw CT
    intensity arrays passed where a mask was expected.
    """

    array = _numeric_array(mask, "mask")
    if require_3d and array.ndim != 3:
        raise SegmentationError(f"mask must be 3D, got shape {array.shape}")
    if max_source_values < 1:
        raise SegmentationError("max_source_values must be at least 1")
    values = np.unique(array)
    if values.size > max_source_values:
        raise SegmentationError(
            f"mask has {values.size} unique values; expected at most {max_source_values}"
        )
    normalized = normalize_mask(array, foreground_values=foreground_values)
    foreground = int(np.count_nonzero(normalized))
    total = int(normalized.size)
    source_values = tuple(value.item() for value in values)
    return MaskSummary(
        tuple(int(value) for value in array.shape), str(array.dtype), foreground,
        total - foreground, foreground / total if total else 0.0, source_values,
    )


def validate_binary_mask(
    mask: Any,
    *,
    allowed_encodings: tuple[tuple[Any, ...], ...] = ((0, 1), (0, 255), (False, True)),
    require_3d: bool = True,
    allow_empty: bool = False,
) -> MaskSummary:
    """Require a conventional binary encoding and return its mask summary.

    A constant all-background or all-foreground mask is valid when its value is
    contained in one of the declared encodings.
    """

    array = _numeric_array(mask, "mask")
    if require_3d and array.ndim != 3:
        raise SegmentationError(f"mask must be 3D, got shape {array.shape}")
    if not allow_empty and array.size == 0:
        raise SegmentationError("mask must not be empty")
    unique = tuple(value.item() for value in np.unique(array))
    if np.issubdtype(array.dtype, np.inexact) and not np.all(np.isfinite(array)):
        raise SegmentationError("binary mask must not contain NaN or infinity")
    if not any(set(unique).issubset(set(encoding)) for encoding in allowed_encodings):
        raise SegmentationError(f"mask values {unique!r} do not match an allowed binary encoding")
    return summarize_mask(array)


def apply_mask(volume: Any, mask: Any, *, fill_value: Any = 0) -> np.ndarray:
    """Return a new array with background voxels replaced by ``fill_value``."""

    array = _numeric_array(volume, "volume")
    binary = normalize_mask(mask, output_dtype=bool)
    if array.shape != binary.shape:
        raise SegmentationError(
            f"volume shape {array.shape} does not match mask shape {binary.shape}"
        )
    return np.where(binary, array, fill_value)

