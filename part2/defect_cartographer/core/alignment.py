"""Quantitative JSON-to-CT axis and centerline alignment diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import permutations
from typing import Any

import numpy as np
from skimage.filters import threshold_li, threshold_otsu

from .geometry import endpoints_for_struts


IDENTITY_TRANSFORM = np.eye(4, dtype=float)


@dataclass(frozen=True)
class AlignmentResult:
    """Serializable alignment evidence and reliability decision."""

    reliable: bool
    selected_permutation: tuple[int, int, int]
    selected_mapping: str
    residual_transform: list[list[float]]
    residual_correction_applied: bool
    threshold_otsu: float
    threshold_li: float
    centerline_occupancy: float
    material_found_fraction: float
    median_material_distance_vox: float
    p90_material_distance_vox: float
    p95_material_distance_vox: float
    median_material_distance_um: float
    p90_material_distance_um: float
    sample_struts: int
    sample_stations: int
    stop_criteria: dict[str, float]
    axis_scores: dict[str, dict[str, float]]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_thresholds(sample: np.ndarray) -> tuple[float, float]:
    """Estimate two established global thresholds from sampled CT intensities."""

    sample = np.asarray(sample)
    if sample.size == 0:
        raise ValueError("Cannot estimate a threshold from an empty sample")
    return float(threshold_otsu(sample)), float(threshold_li(sample))


def _centerline_integer_points(
    graph: dict[str, Any],
    strut_ids: np.ndarray,
    permutation: tuple[int, int, int],
    stations: int = 9,
) -> np.ndarray:
    _, starts, ends = endpoints_for_struts(
        graph,
        strut_ids=strut_ids,
        permutation=permutation,
    )
    parameters = np.linspace(0.15, 0.85, stations)
    points = (
        starts[:, None, :] * (1.0 - parameters[None, :, None])
        + ends[:, None, :] * parameters[None, :, None]
    )
    return np.rint(points).astype(np.int64).reshape(-1, 3)


def _valid_points(points: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    return np.all((points >= 0) & (points < np.asarray(shape)), axis=1)


def score_axis_permutations(
    volume: np.ndarray,
    graph: dict[str, Any],
    strut_ids: np.ndarray,
) -> dict[str, dict[str, float]]:
    """Score each axis permutation by intensity on expected centerlines."""

    scores: dict[str, dict[str, float]] = {}
    for permutation in permutations(range(3)):
        points = _centerline_integer_points(graph, strut_ids, permutation)
        valid = _valid_points(points, volume.shape)
        points = points[valid]
        if not len(points):
            values = np.asarray([], dtype=float)
            median = mean = p90 = float("-inf")
        else:
            values = np.asarray(
                volume[points[:, 0], points[:, 1], points[:, 2]],
                dtype=np.float32,
            )
            median = float(np.median(values))
            mean = float(np.mean(values))
            p90 = float(np.quantile(values, 0.9))
        scores[",".join(map(str, permutation))] = {
            "valid_stations": int(len(points)),
            "median_intensity": median,
            "mean_intensity": mean,
            "p90_intensity": p90,
        }
    return scores


def neighborhood_offsets(radius: int) -> tuple[np.ndarray, np.ndarray]:
    """Return cube offsets and Euclidean distances up to a search radius."""

    if radius < 0:
        raise ValueError("Search radius cannot be negative")
    offsets = np.asarray(
        [
            (z, y, x)
            for z in range(-radius, radius + 1)
            for y in range(-radius, radius + 1)
            for x in range(-radius, radius + 1)
        ],
        dtype=np.int64,
    )
    distances = np.linalg.norm(offsets, axis=1)
    return offsets, distances


def nearest_material_distances(
    volume: np.ndarray,
    points: np.ndarray,
    threshold: float,
    search_radius: int,
    chunk_size: int = 300,
) -> np.ndarray:
    """Measure nearest thresholded material to each centerline station."""

    integer_points = np.rint(points).astype(np.int64)
    offsets, distances = neighborhood_offsets(search_radius)
    output: list[np.ndarray] = []
    shape = np.asarray(volume.shape)
    for start in range(0, len(integer_points), chunk_size):
        base = integer_points[start : start + chunk_size]
        candidates = base[:, None, :] + offsets[None, :, :]
        valid = np.all((candidates >= 0) & (candidates < shape), axis=2)
        values = np.zeros(valid.shape, dtype=volume.dtype)
        row, offset_index = np.where(valid)
        positions = candidates[row, offset_index]
        values[row, offset_index] = volume[
            positions[:, 0], positions[:, 1], positions[:, 2]
        ]
        material = valid & (values >= threshold)
        nearest = np.where(material, distances[None, :], np.inf).min(axis=1)
        output.append(nearest)
    return np.concatenate(output) if output else np.asarray([], dtype=float)


def diagnose_alignment(
    volume: np.ndarray,
    graph: dict[str, Any],
    intensity_sample: np.ndarray,
    *,
    seed: int,
    sample_struts: int,
    search_radius: int,
    voxel_spacing_um: tuple[float, float, float],
) -> AlignmentResult:
    """Select the axis order and apply a conservative alignment stop gate."""

    rng = np.random.default_rng(seed)
    available = np.asarray([int(s["id"]) for s in graph["struts"]], dtype=int)
    selected = rng.choice(
        available,
        size=min(sample_struts, len(available)),
        replace=False,
    )
    otsu, li = estimate_thresholds(intensity_sample)
    scores = score_axis_permutations(volume, graph, selected)
    best_key = max(scores, key=lambda key: scores[key]["median_intensity"])
    best_permutation = tuple(int(item) for item in best_key.split(","))

    points = _centerline_integer_points(graph, selected, best_permutation)
    valid = _valid_points(points, volume.shape)
    points = points[valid]
    center_values = np.asarray(
        volume[points[:, 0], points[:, 1], points[:, 2]],
        dtype=np.float32,
    )
    distances = nearest_material_distances(
        volume,
        points,
        otsu,
        search_radius=search_radius,
    )
    finite = distances[np.isfinite(distances)]
    if not len(finite):
        median = p90 = p95 = float("inf")
    else:
        median, p90, p95 = (
            float(np.quantile(finite, quantile)) for quantile in (0.5, 0.9, 0.95)
        )

    material_found = float(np.isfinite(distances).mean()) if len(distances) else 0.0
    centerline_occupancy = (
        float((center_values >= otsu).mean()) if len(center_values) else 0.0
    )
    limits = {
        "minimum_material_found_fraction": 0.85,
        "maximum_median_distance_vox": 2.0,
        "maximum_p90_distance_vox": 4.0,
    }
    reliable = bool(
        material_found >= limits["minimum_material_found_fraction"]
        and median <= limits["maximum_median_distance_vox"]
        and p90 <= limits["maximum_p90_distance_vox"]
    )
    mean_spacing = float(np.mean(voxel_spacing_um))
    return AlignmentResult(
        reliable=reliable,
        selected_permutation=best_permutation,
        selected_mapping="JSON (x,y,z) -> CT array (z,y,x)"
        if best_permutation == (2, 1, 0)
        else f"JSON axes permuted as {best_permutation}",
        residual_transform=IDENTITY_TRANSFORM.tolist(),
        residual_correction_applied=False,
        threshold_otsu=otsu,
        threshold_li=li,
        centerline_occupancy=centerline_occupancy,
        material_found_fraction=material_found,
        median_material_distance_vox=median,
        p90_material_distance_vox=p90,
        p95_material_distance_vox=p95,
        median_material_distance_um=median * mean_spacing,
        p90_material_distance_um=p90 * mean_spacing,
        sample_struts=int(len(selected)),
        sample_stations=int(len(points)),
        stop_criteria=limits,
        axis_scores=scores,
        note=(
            "Registered positions already encode specimen tilt; no residual transform "
            "was justified by this diagnostic. Missing/broken struts are expected to "
            "reduce material support."
        ),
    )
