"""Rigid/similarity registration of lattice JSON geometry to a CT TIFF.

The CT scan may be tilted because of acquisition or user setup error.  This
module estimates a rotation, translation, and anisotropic scale from the
principal axes of the lattice junction cloud and a sampled CT foreground cloud.
It never changes strut connectivity; only junction ``position`` values are
transformed.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from collections.abc import Iterable, Iterator
from typing import Any, Mapping, Sequence

import numpy as np
import tifffile
from scipy.spatial import cKDTree

from Aman_Scripts.Components.asset_io import inspect_tiff, load_json
from Aman_Scripts.Components.coordinates import apply_transform, homogeneous_matrix, rotation_matrix_xyz
from Aman_Scripts.Components.reporting import write_json


class RegistrationError(ValueError):
    """Raised when registration inputs cannot produce a valid fit."""


def _finite_vector(value: Sequence[float] | None, name: str) -> np.ndarray:
    if value is None:
        raise RegistrationError(f"{name} is required")
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise RegistrationError(f"{name} must contain three finite values")
    return array


class _TiffPages:
    """Re-iterable, lazy page source so large CT stacks stay disk-backed."""

    def __init__(self, path: str, count: int):
        self.path, self.count = path, count

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator[np.ndarray]:
        with tifffile.TiffFile(self.path) as tif:
            for page in tif.series[0].pages:
                yield np.asarray(page.asarray())


def _otsu_threshold(pages: Iterable[np.ndarray]) -> float:
    try:
        first_page = next(iter(pages))
    except StopIteration as exc:
        raise RegistrationError("CT TIFF contains no pages") from exc
    minimum = min(float(np.nanmin(page)) for page in pages)
    maximum = max(float(np.nanmax(page)) for page in pages)
    if not np.isfinite(minimum) or not np.isfinite(maximum) or minimum == maximum:
        raise RegistrationError("CT intensities must contain at least two finite values")
    if np.issubdtype(first_page.dtype, np.integer) and maximum - minimum + 1 <= 1_000_000:
        lower, upper = int(minimum), int(maximum)
        counts = np.zeros(upper - lower + 1, dtype=np.float64)
        for page in pages:
            finite = page[np.isfinite(page)]
            counts += np.bincount(finite.astype(np.int64) - lower, minlength=counts.size)
        levels = np.arange(lower, upper + 1, dtype=np.float64)
    else:
        levels = np.linspace(minimum, maximum, 4096, dtype=np.float64)
        counts = np.zeros(levels.size, dtype=np.float64)
        for page in pages:
            finite = page[np.isfinite(page)]
            counts += np.histogram(finite, bins=levels.size, range=(minimum, maximum))[0]
    populated = counts > 0
    if populated.sum() < 2:
        raise RegistrationError("Otsu threshold requires at least two populated intensity bins")
    total = counts.sum()
    cumulative = np.cumsum(counts)
    weighted = np.cumsum(counts * levels)
    high = total - cumulative
    valid = (cumulative > 0) & (high > 0)
    between = np.full(counts.size, -np.inf)
    low_mean = np.divide(weighted, cumulative, out=np.zeros_like(weighted), where=valid)
    high_mean = np.divide(weighted[-1] - weighted, high, out=np.zeros_like(weighted), where=valid)
    between[valid] = cumulative[valid] * high[valid] * (low_mean[valid] - high_mean[valid]) ** 2
    return float(levels[int(np.argmax(between))])


def _read_pages(path: str) -> tuple[_TiffPages, tuple[int, int, int], str]:
    metadata = inspect_tiff(path)
    if len(metadata.shape) != 3:
        raise RegistrationError(f"CT TIFF must be 3D; got shape={metadata.shape}")
    with tifffile.TiffFile(metadata.path) as tif:
        page_count = len(tif.series[0].pages)
        if page_count != metadata.shape[0] or tif.series[0].pages[0].ndim != 2:
            raise RegistrationError("CT TIFF must be a stack of 2D pages in ZYX order")
    return _TiffPages(metadata.path, page_count), tuple(int(item) for item in metadata.shape), str(metadata.dtype)


def _sample_foreground(pages: Iterable[np.ndarray], max_points: int, threshold: float) -> np.ndarray:
    if max_points < 16:
        raise RegistrationError("max_points must be at least 16")
    page_count = len(pages) if hasattr(pages, "__len__") else 1
    per_page = max(1, max_points // page_count)
    chunks: list[np.ndarray] = []
    for z, page in enumerate(pages):
        coords_yx = np.argwhere(np.isfinite(page) & (page >= threshold))
        if coords_yx.size == 0:
            continue
        step = max(1, int(math.ceil(len(coords_yx) / per_page)))
        coords_yx = coords_yx[::step]
        xyz = np.column_stack((coords_yx[:, 1], coords_yx[:, 0], np.full(len(coords_yx), z)))
        chunks.append(xyz.astype(np.float64, copy=False))
    if not chunks:
        raise RegistrationError("CT threshold produced no foreground voxels")
    points = np.concatenate(chunks, axis=0)
    if len(points) > max_points:
        points = points[::int(math.ceil(len(points) / max_points))][:max_points]
    return points


def _source_points(payload: Mapping[str, Any]) -> np.ndarray:
    records = payload.get("junctions")
    if not isinstance(records, list) or len(records) < 3:
        raise RegistrationError("JSON must contain at least three junction records")
    try:
        points = np.asarray([record["position"] for record in records], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistrationError("every junction must contain a numeric position") from exc
    if points.shape[1:] != (3,) or not np.isfinite(points).all():
        raise RegistrationError("junction positions must have shape (N, 3) and be finite")
    return np.unique(points, axis=0)


def _principal_fit(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    source_center, target_center = source.mean(axis=0), target.mean(axis=0)
    source_centered, target_centered = source - source_center, target - target_center
    source_cov = np.cov(source_centered, rowvar=False)
    target_cov = np.cov(target_centered, rowvar=False)
    source_values, source_axes = np.linalg.eigh(source_cov)
    target_values, target_axes = np.linalg.eigh(target_cov)
    source_order, target_order = np.argsort(source_values)[::-1], np.argsort(target_values)[::-1]
    source_axes, target_axes = source_axes[:, source_order], target_axes[:, target_order]
    source_std = np.sqrt(np.maximum(source_values[source_order], 1e-12))
    target_std = np.sqrt(np.maximum(target_values[target_order], 1e-12))
    tree = cKDTree(target)
    best: tuple[float, np.ndarray, np.ndarray, np.ndarray] | None = None
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            basis = np.zeros((3, 3))
            for source_axis, target_axis in enumerate(permutation):
                basis[target_axis, source_axis] = signs[source_axis]
            if np.linalg.det(basis) < 0:
                continue
            rotation = target_axes @ basis @ source_axes.T
            scales = target_std[list(permutation)] / source_std
            linear = rotation @ np.diag(scales)
            translation = target_center - linear @ source_center
            transformed = source @ linear.T + translation
            score = float(np.median(tree.query(transformed, k=1)[0]))
            candidate = (score, rotation, scales, translation)
            if best is None or score < best[0]:
                best = candidate
    if best is None:
        raise RegistrationError("could not find a proper rotation between point clouds")
    return best[1], best[2], best[3], best[0]


def register_payload(
    payload: Mapping[str, Any],
    pages: Iterable[np.ndarray],
    volume_shape: tuple[int, int, int],
    *,
    mode: str = "auto",
    translation_xyz: Sequence[float] | None = None,
    rotation_xyz_degrees: Sequence[float] | None = None,
    scale_xyz: Sequence[float] | None = None,
    threshold: float | None = None,
    max_points: int = 20_000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if mode not in {"auto", "manual"}:
        raise RegistrationError("mode must be 'auto' or 'manual'")
    source = _source_points(payload)
    if threshold is None:
        threshold = _otsu_threshold(pages)
    if not np.isfinite(threshold):
        raise RegistrationError("threshold must be finite")
    target = _sample_foreground(pages, int(max_points), float(threshold))
    if mode == "auto":
        rotation, scales, translation, score = _principal_fit(source, target)
        method = "PCA principal-axis similarity fit (tilt-aware)"
    else:
        translation = _finite_vector(translation_xyz, "translation_xyz")
        angles = _finite_vector(rotation_xyz_degrees, "rotation_xyz_degrees")
        scales = _finite_vector(scale_xyz, "scale_xyz")
        if np.any(scales == 0):
            raise RegistrationError("scale_xyz values must be nonzero")
        rotation = rotation_matrix_xyz(angles, degrees=True)
        transformed = source @ (rotation @ np.diag(scales)).T + translation
        score = float(np.median(cKDTree(target).query(transformed, k=1)[0]))
        method = "manual XYZ translation/rotation/scale"
    matrix = homogeneous_matrix(rotation=rotation, translation=translation, scale=scales)
    result = dict(payload)
    result["junctions"] = []
    for record in payload["junctions"]:
        updated = dict(record)
        updated["position"] = apply_transform(record["position"], matrix).tolist()
        result["junctions"].append(updated)
    result["registration"] = {
        "schema_version": "ct-json-registration.v1",
        "method": method,
        "source_coordinate_order": "XYZ",
        "ct_coordinate_order": "ZYX array, registered as XYZ voxel coordinates",
        "tilt_acknowledged": True,
        "threshold": float(threshold),
        "estimated_rotation_matrix_xyz": rotation.tolist(),
        "scale_xyz": scales.tolist(),
        "translation_xyz": translation.tolist(),
        "transform_xyz_homogeneous": matrix.tolist(),
        "median_nearest_foreground_distance_voxels": score,
        "ct_shape_zyx": list(volume_shape),
        "sampled_foreground_points": int(len(target)),
    }
    return result, result["registration"]


def register_json_to_tiff(
    json_filepath: str,
    tiff_filepath: str,
    output_filepath: str,
    *,
    mode: str = "auto",
    translation_xyz: Sequence[float] | None = None,
    rotation_xyz_degrees: Sequence[float] | None = None,
    scale_xyz: Sequence[float] | None = None,
    threshold: float | None = None,
    max_points: int = 20_000,
) -> tuple[Path, dict[str, Any]]:
    payload = load_json(json_filepath)
    pages, shape, _ = _read_pages(tiff_filepath)
    registered, report = register_payload(
        payload, pages, shape, mode=mode, translation_xyz=translation_xyz,
        rotation_xyz_degrees=rotation_xyz_degrees, scale_xyz=scale_xyz,
        threshold=threshold, max_points=max_points,
    )
    destination = Path(output_filepath)
    if destination.suffix.lower() != ".json":
        destination = destination.with_suffix(destination.suffix + ".json" if destination.suffix else ".json")
    return write_json(destination, registered, create_parents=True), report
