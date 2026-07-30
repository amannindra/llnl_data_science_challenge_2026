"""Map monolithic STL surface geometry onto registered lattice strut IDs.

The STL does not contain semantic strut identifiers.  This module builds a
native-CT centerline atlas from the registered JSON graph, streams every source
triangle (its three vertices and centroid), and associates those real surface
samples with the nearest axial strut bin.  No triangle or CT downsampling is
performed and no whole-volume STL mask is allocated.

Comparing coverage from ``0.stl`` and ``0.5.stl`` is an identity/calibration
step only.  It prevents boundary tessellation from being mistaken for an
intentional omission; the physical inspection still compares ``0.5.stl`` with
the TIFF.
"""

from __future__ import annotations

import math
from os import PathLike
from typing import Any, Mapping, Sequence

import numpy as np

from .coordinates import apply_transform
from .lattice_graph import LatticeGraph
from tif2stl.stl_geometry import read_stl_triangles


class CADStrutMappingError(ValueError):
    """Raised when STL surface evidence cannot be mapped safely to graph IDs."""


def build_registered_centerline_atlas(
    graph: LatticeGraph,
    *,
    axial_bins: int = 45,
    endpoint_exclusion_fraction: float = 0.10,
) -> dict[str, Any]:
    """Return fixed axial stations for every registered source strut."""

    if axial_bins < 3:
        raise CADStrutMappingError("axial_bins must be at least 3")
    if not (0.0 <= endpoint_exclusion_fraction < 0.5):
        raise CADStrutMappingError("endpoint_exclusion_fraction must lie in [0, 0.5)")
    junctions = graph.junction_by_id()
    strut_ids = np.asarray([strut.id for strut in graph.struts], dtype=np.int64)
    if len(strut_ids) != len(np.unique(strut_ids)):
        raise CADStrutMappingError("source strut IDs must be unique")
    endpoints0 = np.empty((len(graph.struts), 3), dtype=np.float64)
    endpoints1 = np.empty_like(endpoints0)
    for index, strut in enumerate(graph.struts):
        try:
            endpoints0[index] = junctions[strut.junction0].position
            endpoints1[index] = junctions[strut.junction1].position
        except KeyError as exc:
            raise CADStrutMappingError(
                f"strut {strut.id} references missing junction {exc.args[0]}"
            ) from exc
    lengths = np.linalg.norm(endpoints1 - endpoints0, axis=1)
    if not np.isfinite(lengths).all() or np.any(lengths <= 0.0):
        raise CADStrutMappingError("registered graph contains a zero/nonfinite strut")
    local = (np.arange(axial_bins, dtype=np.float64) + 0.5) / axial_bins
    fractions = endpoint_exclusion_fraction + (
        1.0 - 2.0 * endpoint_exclusion_fraction
    ) * local
    centers = (
        endpoints0[:, None, :]
        + fractions[None, :, None] * (endpoints1 - endpoints0)[:, None, :]
    )
    return {
        "strut_ids": strut_ids,
        "endpoint0_xyz": endpoints0,
        "endpoint1_xyz": endpoints1,
        "length_voxels": lengths,
        "axial_fractions": fractions,
        "centers_xyz": centers,
        "axial_bins": int(axial_bins),
        "endpoint_exclusion_fraction": float(endpoint_exclusion_fraction),
    }


def identify_skin_embedded_struts(
    design_graph: LatticeGraph,
    *,
    skin_normal_axis: int = 2,
    tolerance: float = 1e-8,
) -> np.ndarray:
    """Return source IDs whose two endpoints lie in either solid-skin plane.

    The paper's skins are normal to design Z.  A member wholly contained in a
    skin face cannot be distinguished independently in CT, even though its
    source record must remain in the output for provenance.
    """

    if skin_normal_axis not in (0, 1, 2):
        raise CADStrutMappingError("skin_normal_axis must be 0, 1, or 2")
    if not (np.isfinite(tolerance) and tolerance >= 0.0):
        raise CADStrutMappingError("tolerance must be finite and nonnegative")
    junctions = design_graph.junction_by_id()
    coordinates = np.asarray(
        [junction.position[skin_normal_axis] for junction in design_graph.junctions],
        dtype=np.float64,
    )
    if coordinates.size == 0:
        raise CADStrutMappingError("design graph has no junction coordinates")
    lower, upper = float(coordinates.min()), float(coordinates.max())
    embedded = []
    for strut in design_graph.struts:
        try:
            first = junctions[strut.junction0].position[skin_normal_axis]
            second = junctions[strut.junction1].position[skin_normal_axis]
        except KeyError as exc:
            raise CADStrutMappingError(
                f"strut {strut.id} references missing junction {exc.args[0]}"
            ) from exc
        in_lower = abs(first - lower) <= tolerance and abs(second - lower) <= tolerance
        in_upper = abs(first - upper) <= tolerance and abs(second - upper) <= tolerance
        if in_lower or in_upper:
            embedded.append(strut.id)
    return np.asarray(sorted(embedded), dtype=np.int64)


def _validated_transform(transform: np.ndarray) -> np.ndarray:
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise CADStrutMappingError("stl_to_ct_transform must be a finite 4x4 matrix")
    if not np.allclose(matrix[3], (0.0, 0.0, 0.0, 1.0), atol=1e-12, rtol=0.0):
        raise CADStrutMappingError("stl_to_ct_transform must be affine")
    return matrix


def sample_stl_surface_against_atlas(
    path: str | PathLike[str],
    stl_to_ct_transform: np.ndarray,
    atlas: Mapping[str, Any],
    *,
    association_radii_voxels: Sequence[float] = (8.0, 9.0, 10.0),
    chunk_faces: int = 100_000,
    workers: int = 1,
    retain_nearest_points: bool = False,
) -> dict[str, Any]:
    """Stream all STL triangles and accumulate per-edge/bin surface support.

    Every triangle contributes its three original vertices and its centroid.
    Vertices are not deduplicated because duplicate source records still carry
    legitimate surface evidence and deduplication would cause a large memory
    spike.  Coverage itself is Boolean, so duplicates cannot inflate it.
    """

    from scipy.spatial import cKDTree

    matrix = _validated_transform(stl_to_ct_transform)
    radii = np.asarray(tuple(float(value) for value in association_radii_voxels))
    if radii.ndim != 1 or radii.size == 0 or not np.isfinite(radii).all() or np.any(radii <= 0):
        raise CADStrutMappingError("association radii must be positive finite values")
    if np.any(np.diff(radii) <= 0):
        raise CADStrutMappingError("association radii must be strictly increasing")
    if chunk_faces < 1:
        raise CADStrutMappingError("chunk_faces must be positive")
    centers = np.asarray(atlas["centers_xyz"], dtype=np.float64)
    if centers.ndim != 3 or centers.shape[2] != 3:
        raise CADStrutMappingError("atlas centers_xyz must have shape (struts,bins,3)")
    strut_count, axial_bins, _ = centers.shape
    flattened_centers = np.ascontiguousarray(centers.reshape(-1, 3))
    tree = cKDTree(flattened_centers, leafsize=32, compact_nodes=True, balanced_tree=True)
    coverage = np.zeros((strut_count * axial_bins, len(radii)), dtype=bool)
    nearest_distance = np.full(strut_count * axial_bins, np.inf, dtype=np.float32)
    nearest_point = (
        np.full((strut_count * axial_bins, 3), np.nan, dtype=np.float32)
        if retain_nearest_points else None
    )
    triangle_count = 0
    surface_sample_count = 0
    maximum_radius = float(radii[-1])

    for triangles in read_stl_triangles(path, chunk_faces=chunk_faces):
        triangle_count += int(triangles.shape[0])
        transformed = apply_transform(
            triangles.reshape(-1, 3), matrix
        ).reshape(-1, 3, 3)
        samples = np.concatenate(
            (transformed.reshape(-1, 3), transformed.mean(axis=1)), axis=0
        )
        surface_sample_count += int(samples.shape[0])
        try:
            distances, indices = tree.query(
                samples, k=1, distance_upper_bound=maximum_radius, workers=workers
            )
        except TypeError:  # pragma: no cover - old SciPy compatibility
            distances, indices = tree.query(
                samples, k=1, distance_upper_bound=maximum_radius
            )
        valid = np.isfinite(distances) & (indices < flattened_centers.shape[0])
        if not np.any(valid):
            continue
        selected_indices = indices[valid].astype(np.int64, copy=False)
        selected_distances = distances[valid].astype(np.float64, copy=False)
        selected_points = samples[valid]
        for radius_index, radius in enumerate(radii):
            within = selected_distances <= radius
            if np.any(within):
                np.logical_or.at(coverage[:, radius_index], selected_indices[within], True)

        # Keep the closest real STL surface sample for each axial station.  Sort
        # by station and then distance, so the first row in every group is the
        # deterministic winner for this chunk.
        order = np.lexsort((selected_distances, selected_indices))
        ordered_indices = selected_indices[order]
        first = np.concatenate(([True], ordered_indices[1:] != ordered_indices[:-1]))
        candidate_indices = ordered_indices[first]
        candidate_distances = selected_distances[order][first]
        candidate_points = selected_points[order][first]
        improves = candidate_distances < nearest_distance[candidate_indices]
        if np.any(improves):
            destinations = candidate_indices[improves]
            nearest_distance[destinations] = candidate_distances[improves]
            if nearest_point is not None:
                nearest_point[destinations] = candidate_points[improves]

    if triangle_count == 0:
        raise CADStrutMappingError(f"STL contains no triangles: {path}")
    result: dict[str, Any] = {
        "path": str(path),
        "triangle_count": triangle_count,
        "surface_sample_count": surface_sample_count,
        "association_radii_voxels": radii,
        "coverage": coverage.reshape(strut_count, axial_bins, len(radii)),
        "nearest_surface_distance": nearest_distance.reshape(strut_count, axial_bins),
    }
    if nearest_point is not None:
        result["nearest_surface_point_xyz"] = nearest_point.reshape(
            strut_count, axial_bins, 3
        )
    return result


def infer_specimen_cad_omissions(
    complete_surface: Mapping[str, Any],
    specimen_surface: Mapping[str, Any],
    strut_ids: Sequence[int],
    *,
    maximum_removed_fraction: float = 0.05,
    minimum_cluster_gap: float = 0.10,
    minimum_split_score: float = 0.20,
) -> dict[str, Any]:
    """Separate unchanged and intentionally omitted STL edges by a clear gap.

    The omitted count is not supplied or forced.  The split is the largest
    admissible gap in the median complete-minus-specimen axial coverage drop.
    Broad high-cluster limits only reject nonsensical mappings/orientations.
    """

    complete = np.asarray(complete_surface["coverage"], dtype=bool)
    specimen = np.asarray(specimen_surface["coverage"], dtype=bool)
    ids = np.asarray(strut_ids, dtype=np.int64)
    if complete.shape != specimen.shape or complete.ndim != 3:
        raise CADStrutMappingError(
            f"coverage shapes differ: complete {complete.shape}, specimen {specimen.shape}"
        )
    if complete.shape[0] != len(ids):
        raise CADStrutMappingError("strut_ids length does not match coverage rows")
    if not (0.0 < maximum_removed_fraction < 0.5):
        raise CADStrutMappingError("maximum_removed_fraction must lie in (0, 0.5)")
    complete_fraction = complete.mean(axis=1)
    specimen_fraction = specimen.mean(axis=1)
    drops_by_radius = complete_fraction - specimen_fraction
    median_drop = np.median(drops_by_radius, axis=1)
    order = np.argsort(median_drop, kind="stable")
    values = median_drop[order]
    count = len(values)
    minimum_high_count = max(3, int(math.ceil(0.0001 * count)))
    maximum_high_count = max(minimum_high_count, int(math.floor(maximum_removed_fraction * count)))
    candidates: list[tuple[float, int]] = []
    for high_count in range(minimum_high_count, maximum_high_count + 1):
        split_index = count - high_count
        if split_index <= 0 or split_index >= count:
            continue
        gap = float(values[split_index] - values[split_index - 1])
        threshold = float((values[split_index] + values[split_index - 1]) / 2.0)
        if threshold >= minimum_split_score:
            candidates.append((gap, split_index))
    if not candidates:
        raise CADStrutMappingError("no admissible CAD-omission cluster split was found")
    gap, split_index = max(candidates, key=lambda item: (item[0], item[1]))
    if gap < minimum_cluster_gap:
        raise CADStrutMappingError(
            f"largest CAD-omission cluster gap {gap:.6f} is below {minimum_cluster_gap}"
        )
    threshold = float((values[split_index] + values[split_index - 1]) / 2.0)
    removed = median_drop > threshold
    per_radius_removed = drops_by_radius > threshold
    agreement = per_radius_removed.mean(axis=1)
    ambiguous = removed & (agreement < (2.0 / 3.0))
    if np.any(ambiguous):
        raise CADStrutMappingError(
            f"{int(np.count_nonzero(ambiguous))} removal candidates are unstable across radii"
        )
    return {
        "strut_ids": ids,
        "complete_coverage_fraction_by_radius": complete_fraction,
        "specimen_coverage_fraction_by_radius": specimen_fraction,
        "coverage_drop_by_radius": drops_by_radius,
        "median_coverage_drop": median_drop,
        "split_threshold": threshold,
        "cluster_gap": float(gap),
        "removed_mask": removed,
        "removed_strut_ids": ids[removed],
        "removed_count": int(np.count_nonzero(removed)),
        "radius_agreement": agreement,
    }


__all__ = [
    "CADStrutMappingError",
    "build_registered_centerline_atlas",
    "infer_specimen_cad_omissions",
    "identify_skin_embedded_struts",
    "sample_stl_surface_against_atlas",
]
