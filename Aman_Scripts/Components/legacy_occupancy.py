"""Preserved, unvalidated JSON-guided centerline occupancy diagnostic.

This module exists for backward compatibility with ``analyze_json.py``.  It is
not the planned TIFF defect detector: it cannot identify endpoint disconnects,
clips samples at the field-of-view boundary, and previously over-called 20.98%
of struts as missing on the real scan.  New inspection work must not treat its
candidate labels as ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .lattice_graph import LatticeGraph
from .segmentation import validate_numeric_volume


@dataclass(frozen=True)
class LegacyOccupancyResult:
    strut_ids: np.ndarray
    junction0_ids: np.ndarray
    junction1_ids: np.ndarray
    midpoints_xyz: np.ndarray
    occupancy: np.ndarray
    candidate_missing: np.ndarray
    material_threshold: float
    missing_cutoff: float


def otsu_threshold(values: Any, *, bins: int = 256) -> float:
    """Return a finite Otsu split for a one-dimensional numeric sample."""

    sample = np.asarray(values)
    if sample.size == 0 or not np.issubdtype(sample.dtype, np.number):
        raise ValueError("Otsu sample must be a nonempty numeric array")
    finite = np.asarray(sample[np.isfinite(sample)], dtype=np.float64)
    if finite.size == 0:
        raise ValueError("Otsu sample has no finite values")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    if float(finite.min()) == float(finite.max()):
        return float(finite[0])
    histogram, edges = np.histogram(finite, bins=bins)
    probability = histogram.astype(float) / histogram.sum()
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(probability)
    mean = np.cumsum(probability * centers)
    total = mean[-1]
    denominator = weight * (1 - weight)
    between = np.full_like(denominator, -np.inf, dtype=float)
    valid = denominator > 0
    between[valid] = (total * weight[valid] - mean[valid]) ** 2 / denominator[valid]
    return float(centers[int(np.argmax(between))])


def sphere_offsets(radius: int) -> tuple[tuple[int, int, int], ...]:
    """Return deterministic integer XYZ offsets inside an inclusive sphere."""

    if isinstance(radius, bool) or int(radius) != radius or radius < 0:
        raise ValueError("radius must be a nonnegative integer")
    radius = int(radius)
    return tuple(
        (dx, dy, dz)
        for dx in range(-radius, radius + 1)
        for dy in range(-radius, radius + 1)
        for dz in range(-radius, radius + 1)
        if dx * dx + dy * dy + dz * dz <= radius * radius
    )


def centerline_occupancy(
    volume_zyx: Any,
    graph: LatticeGraph,
    *,
    material_threshold: float | None = None,
    threshold_sample_stride: int = 30,
    n_samples: int = 25,
    radius: int = 2,
    missing_cutoff: float = 0.3,
) -> LegacyOccupancyResult:
    """Apply the historical max-in-sphere centerline heuristic.

    Graph positions are XYZ while ``volume_zyx`` is indexed ZYX.  Endpoints are
    excluded by sampling from 15% through 85% of each strut, exactly matching
    the prior script's core semantics.
    """

    volume = np.asanyarray(volume_zyx)
    validate_numeric_volume(volume, require_3d=True, allow_empty=False)
    try:
        sample_count = float(n_samples)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("n_samples must be an integer of at least 2") from exc
    if (
        isinstance(n_samples, bool) or not math.isfinite(sample_count)
        or not sample_count.is_integer() or sample_count < 2
    ):
        raise ValueError("n_samples must be an integer of at least 2")
    n_samples = int(sample_count)
    try:
        stride = float(threshold_sample_stride)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("threshold_sample_stride must be a positive integer") from exc
    if (
        isinstance(threshold_sample_stride, bool) or not math.isfinite(stride)
        or not stride.is_integer() or stride < 1
    ):
        raise ValueError("threshold_sample_stride must be a positive integer")
    threshold_sample_stride = int(stride)
    try:
        cutoff = float(missing_cutoff)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("missing_cutoff must be in [0, 1]") from exc
    if not math.isfinite(cutoff) or not 0 <= cutoff <= 1:
        raise ValueError("missing_cutoff must be in [0, 1]")
    if material_threshold is None:
        threshold = otsu_threshold(np.asarray(volume[::threshold_sample_stride]).ravel())
    else:
        threshold = float(material_threshold)
        if not math.isfinite(threshold):
            raise ValueError("material_threshold must be finite")

    positions = {junction.id: np.asarray(junction.position, dtype=float) for junction in graph.junctions}
    struts = graph.struts
    left = np.asarray([positions[strut.junction0] for strut in struts], dtype=float)
    right = np.asarray([positions[strut.junction1] for strut in struts], dtype=float)
    parameters = np.linspace(0.15, 0.85, n_samples)
    points = left[:, None, :] * (1 - parameters)[None, :, None] + right[:, None, :] * parameters[None, :, None]
    x_center = np.rint(points[..., 0]).astype(int)
    y_center = np.rint(points[..., 1]).astype(int)
    z_center = np.rint(points[..., 2]).astype(int)
    z_size, y_size, x_size = volume.shape
    best = np.array(
        volume[
            np.clip(z_center, 0, z_size - 1),
            np.clip(y_center, 0, y_size - 1),
            np.clip(x_center, 0, x_size - 1),
        ],
        copy=True,
    )
    for dx, dy, dz in sphere_offsets(radius):
        x_index = np.clip(x_center + dx, 0, x_size - 1)
        y_index = np.clip(y_center + dy, 0, y_size - 1)
        z_index = np.clip(z_center + dz, 0, z_size - 1)
        np.maximum(best, volume[z_index, y_index, x_index], out=best)
    occupancy = np.mean(best > threshold, axis=1)
    return LegacyOccupancyResult(
        strut_ids=np.asarray([strut.id for strut in struts], dtype=np.int64),
        junction0_ids=np.asarray([strut.junction0 for strut in struts], dtype=np.int64),
        junction1_ids=np.asarray([strut.junction1 for strut in struts], dtype=np.int64),
        midpoints_xyz=0.5 * (left + right),
        occupancy=occupancy,
        candidate_missing=occupancy < cutoff,
        material_threshold=threshold,
        missing_cutoff=cutoff,
    )
