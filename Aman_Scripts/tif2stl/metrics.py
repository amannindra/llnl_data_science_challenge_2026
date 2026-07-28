"""Pure overlap metrics between two aligned boolean ZYX voxel masks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OverlapMetrics:
    """Voxel-count agreement between a reference mask A and a candidate mask B."""

    a_voxels: int
    b_voxels: int
    intersection_voxels: int
    union_voxels: int
    dice: float
    iou: float
    a_in_b_fraction: float
    b_in_a_fraction: float


def _as_bool(mask: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(mask)
    if array.dtype.kind not in "biuf":
        raise ValueError(f"{name} must be numeric or boolean, got dtype {array.dtype}")
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise ValueError(f"{name} contains nonfinite values")
    return array.astype(bool, copy=False)


def mask_overlap(mask_a: np.ndarray, mask_b: np.ndarray) -> OverlapMetrics:
    """Compute Dice/IoU/containment between two same-shape masks.

    Two empty masks are defined as perfectly agreeing (all ratios 1.0); one
    empty mask against a nonempty one scores 0.0.
    """

    a = _as_bool(mask_a, "mask_a")
    b = _as_bool(mask_b, "mask_b")
    if a.shape != b.shape:
        raise ValueError(f"mask shapes differ: {a.shape} vs {b.shape}")
    a_count = int(np.count_nonzero(a))
    b_count = int(np.count_nonzero(b))
    intersection = int(np.count_nonzero(a & b))
    union = a_count + b_count - intersection
    if a_count == 0 and b_count == 0:
        dice = iou = a_in_b = b_in_a = 1.0
    else:
        dice = 2.0 * intersection / (a_count + b_count)
        iou = intersection / union if union else 0.0
        a_in_b = intersection / a_count if a_count else 0.0
        b_in_a = intersection / b_count if b_count else 0.0
    return OverlapMetrics(
        a_voxels=a_count,
        b_voxels=b_count,
        intersection_voxels=intersection,
        union_voxels=union,
        dice=float(dice),
        iou=float(iou),
        a_in_b_fraction=float(a_in_b),
        b_in_a_fraction=float(b_in_a),
    )


def mask_bounds_zyx(mask: np.ndarray) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Half-open ``(start, stop)`` index bounds of the foreground, or ``None``."""

    array = _as_bool(mask, "mask")
    if not array.any():
        return None
    start = []
    stop = []
    for axis in range(array.ndim):
        other = tuple(index for index in range(array.ndim) if index != axis)
        profile = np.any(array, axis=other)
        indices = np.flatnonzero(profile)
        start.append(int(indices[0]))
        stop.append(int(indices[-1]) + 1)
    return tuple(start), tuple(stop)


def fraction_inside_mask(
    mask_zyx: np.ndarray,
    points_xyz: np.ndarray,
    *,
    origin_xyz: tuple[float, float, float],
    pitch: float,
) -> float:
    """Fraction of XYZ points whose grid cell is foreground in a ZYX mask.

    Cells are ``floor((point - origin) / pitch)``; points outside the grid
    count as misses.  Used to rank candidate orientations, so it must stay
    total and deterministic.
    """

    mask = _as_bool(mask_zyx, "mask_zyx")
    if mask.ndim != 3:
        raise ValueError(f"mask_zyx must be 3D, got {mask.ndim}D")
    if not (np.isfinite(pitch) and pitch > 0):
        raise ValueError("pitch must be a positive finite number")
    points = np.asarray(points_xyz, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0:
        raise ValueError(f"points_xyz must have shape (n>=1, 3), got {points.shape}")
    if not np.isfinite(points).all():
        raise ValueError("points_xyz contains nonfinite coordinates")
    origin = np.asarray(origin_xyz, dtype=np.float64)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("origin_xyz must contain three finite values")
    indices = np.floor((points - origin) / pitch).astype(np.int64)
    shape_xyz = np.asarray([mask.shape[2], mask.shape[1], mask.shape[0]])
    inside = np.all((indices >= 0) & (indices < shape_xyz), axis=1)
    if not inside.any():
        return 0.0
    kept = indices[inside]
    hits = mask[kept[:, 2], kept[:, 1], kept[:, 0]]
    return float(np.count_nonzero(hits)) / float(points.shape[0])


def window_slices_zyx(
    points_xyz: np.ndarray,
    *,
    origin_xyz: tuple[float, float, float],
    pitch: float,
    shape_zyx: tuple[int, int, int],
    padding_cells: int = 2,
) -> tuple[slice, slice, slice]:
    """ZYX slices covering the grid cells spanned by XYZ points, padded, clamped."""

    if padding_cells < 0:
        raise ValueError("padding_cells must be nonnegative")
    if not (np.isfinite(pitch) and pitch > 0):
        raise ValueError("pitch must be a positive finite number")
    points = np.asarray(points_xyz, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0:
        raise ValueError(f"points_xyz must have shape (n>=1, 3), got {points.shape}")
    if not np.isfinite(points).all():
        raise ValueError("points_xyz contains nonfinite coordinates")
    origin = np.asarray(origin_xyz, dtype=np.float64)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("origin_xyz must contain three finite values")
    shape = tuple(int(value) for value in shape_zyx)
    if len(shape) != 3 or any(value <= 0 for value in shape):
        raise ValueError(f"shape_zyx must be three positive ints, got {shape_zyx}")
    indices = np.floor((points - origin) / pitch).astype(np.int64)
    slices = []
    for axis in range(3):  # z, y, x
        column = indices[:, 2 - axis]
        start = int(np.clip(column.min() - padding_cells, 0, shape[axis] - 1))
        stop = int(np.clip(column.max() + padding_cells + 1, start + 1, shape[axis]))
        slices.append(slice(start, stop))
    return tuple(slices)


def per_slab_overlap(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    *,
    slab_depth: int = 32,
) -> list[dict[str, object]]:
    """Dice per Z slab for two aligned 3D masks, as CSV-ready row dicts."""

    if slab_depth <= 0:
        raise ValueError("slab_depth must be positive")
    a = _as_bool(mask_a, "mask_a")
    b = _as_bool(mask_b, "mask_b")
    if a.shape != b.shape:
        raise ValueError(f"mask shapes differ: {a.shape} vs {b.shape}")
    if a.ndim != 3:
        raise ValueError(f"per_slab_overlap requires 3D masks, got {a.ndim}D")
    rows: list[dict[str, object]] = []
    for z_start in range(0, a.shape[0], slab_depth):
        z_stop = min(z_start + slab_depth, a.shape[0])
        slab = mask_overlap(a[z_start:z_stop], b[z_start:z_stop])
        rows.append({
            "z_start": z_start,
            "z_stop": z_stop,
            "ct_voxels": slab.a_voxels,
            "stl_voxels": slab.b_voxels,
            "intersection_voxels": slab.intersection_voxels,
            "dice": round(slab.dice, 6),
        })
    return rows
