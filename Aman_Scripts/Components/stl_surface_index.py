"""Memory-bounded spatial queries over a transformed STL surface.

The full mesh is retained: this module does not decimate, subdivide, voxelize,
or otherwise replace STL triangles.  Triangles are transformed into target XYZ
coordinates once and indexed by centroid.  A radius-bucketed collection of
``scipy.spatial.cKDTree`` instances avoids the pathological query radius that a
few very large plate triangles would impose on a single centroid tree.

Segment queries sample native XYZ positions along a finite centerline.  Tree
hits are conservative candidates only.  Every returned hit passes an exact
point-to-triangle distance check, and the returned surface point is the closest
point on that original triangle.  The result's compressed arrays preserve all
per-bin triangle matches without constructing a whole-volume STL voxel mask.

Importing this module performs no I/O.  SciPy is imported lazily while an index
is built.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .asset_io import inspect_stl
from .coordinates import apply_transform
from tif2stl.stl_geometry import read_stl_triangles


_DEFAULT_MAX_INDEX_BYTES = 1_500_000_000
_ESTIMATED_BYTES_PER_TRIANGLE = 128
_INDEX_FIXED_ALLOWANCE_BYTES = 32 << 20


def _readonly(array: NDArray[Any]) -> NDArray[Any]:
    """Mark an owned result array read-only and return it."""

    array.setflags(write=False)
    return array


def _xyz(value: ArrayLike, *, name: str) -> NDArray[np.float64]:
    point = np.asarray(value, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{name} must contain exactly three finite XYZ values")
    return point


def _affine_transform(value: ArrayLike | None) -> NDArray[np.float64]:
    if value is None:
        matrix = np.eye(4, dtype=np.float64)
    else:
        matrix = np.asarray(value, dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError("transform must be a finite 4x4 matrix")
        matrix = matrix.copy()
    if not np.allclose(matrix[3], (0.0, 0.0, 0.0, 1.0), rtol=0.0, atol=1e-12):
        raise ValueError(
            "transform must be affine with last row [0, 0, 0, 1]; "
            "projective transforms do not preserve planar STL triangles"
        )
    if abs(float(np.linalg.det(matrix[:3, :3]))) <= np.finfo(np.float64).eps:
        raise ValueError("transform must have a nonsingular 3x3 linear part")
    return matrix


def _positive_integer(value: Any, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a positive integer")
    try:
        integer = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if not math.isfinite(numeric) or numeric != integer or integer <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return integer


def _closest_points_on_triangles(
    point_xyz: NDArray[np.float64],
    triangles_xyz: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return exact closest points and squared distances to many triangles.

    Interior projections onto nondegenerate faces are compared with closest
    points on all three closed edges.  The edge tests also make degenerate
    triangles well-defined instead of dropping them from the original mesh.
    """

    triangles = np.asarray(triangles_xyz, dtype=np.float64)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise ValueError(f"triangles_xyz must have shape (n, 3, 3), got {triangles.shape}")
    if triangles.shape[0] == 0:
        return (
            np.empty((0, 3), dtype=np.float64),
            np.empty(0, dtype=np.float64),
        )

    point = _xyz(point_xyz, name="point_xyz")
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]

    def closest_on_edges(
        begin: NDArray[np.float64], end: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        direction = end - begin
        denominator = np.einsum("ij,ij->i", direction, direction)
        numerator = np.einsum("ij,ij->i", point - begin, direction)
        fraction = np.divide(
            numerator,
            denominator,
            out=np.zeros_like(numerator),
            where=denominator > 0.0,
        )
        np.clip(fraction, 0.0, 1.0, out=fraction)
        return begin + fraction[:, None] * direction

    edge_ab = closest_on_edges(a, b)
    edge_bc = closest_on_edges(b, c)
    edge_ca = closest_on_edges(c, a)

    ab = b - a
    ac = c - a
    normal = np.cross(ab, ac)
    normal_squared = np.einsum("ij,ij->i", normal, normal)
    plane_fraction = np.divide(
        np.einsum("ij,ij->i", a - point, normal),
        normal_squared,
        out=np.zeros_like(normal_squared),
        where=normal_squared > 0.0,
    )
    projected = point + plane_fraction[:, None] * normal

    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    relative = projected - a
    d20 = np.einsum("ij,ij->i", relative, ab)
    d21 = np.einsum("ij,ij->i", relative, ac)
    barycentric_denominator = d00 * d11 - d01 * d01
    bary_v = np.divide(
        d11 * d20 - d01 * d21,
        barycentric_denominator,
        out=np.zeros_like(d20),
        where=barycentric_denominator != 0.0,
    )
    bary_w = np.divide(
        d00 * d21 - d01 * d20,
        barycentric_denominator,
        out=np.zeros_like(d20),
        where=barycentric_denominator != 0.0,
    )
    bary_u = 1.0 - bary_v - bary_w
    # The tolerance only absorbs floating-point error at a shared edge.  It is
    # many orders of magnitude below a native CT voxel.
    barycentric_tolerance = 64.0 * np.finfo(np.float64).eps
    projection_inside = (
        (normal_squared > 0.0)
        & (bary_u >= -barycentric_tolerance)
        & (bary_v >= -barycentric_tolerance)
        & (bary_w >= -barycentric_tolerance)
    )

    candidates = np.stack((edge_ab, edge_bc, edge_ca, projected), axis=0)
    delta = candidates - point
    squared = np.einsum("knj,knj->kn", delta, delta)
    squared[3, ~projection_inside] = np.inf
    best = np.argmin(squared, axis=0)
    columns = np.arange(triangles.shape[0])
    closest = candidates[best, columns]
    distances_squared = squared[best, columns]
    # Small negative values cannot occur mathematically, but clipping protects
    # downstream square roots if a future implementation uses dot identities.
    np.maximum(distances_squared, 0.0, out=distances_squared)
    return closest, distances_squared


@dataclass(frozen=True, slots=True)
class _RadiusBucket:
    """One disjoint triangle-radius group and its centroid index."""

    triangle_indices: NDArray[np.int64]
    maximum_radius: float
    tree: Any


@dataclass(frozen=True, slots=True)
class SegmentSurfaceQuery:
    """Immutable exact STL-surface evidence along one finite XYZ segment.

    Matches use compressed-row storage.  For axial bin ``i``, corresponding
    entries occupy ``bin_offsets[i]:bin_offsets[i + 1]`` in
    ``triangle_indices``, ``surface_distances``, and ``surface_points_xyz``.
    A triangle can occur in several bins because each bin is a separate local
    surface query.
    """

    start_xyz: tuple[float, float, float]
    end_xyz: tuple[float, float, float]
    radius: float
    endpoint_exclusion_fraction: float
    axial_bin_width: float
    axial_fractions: NDArray[np.float64]
    bin_centers_xyz: NDArray[np.float64]
    bin_counts: NDArray[np.int64]
    bin_offsets: NDArray[np.int64]
    triangle_indices: NDArray[np.int64]
    surface_distances: NDArray[np.float64]
    surface_points_xyz: NDArray[np.float64]
    nearest_surface_distances: NDArray[np.float64]
    nearest_surface_points_xyz: NDArray[np.float64]
    unique_triangle_indices: NDArray[np.int64]

    @property
    def axial_bin_counts(self) -> NDArray[np.int64]:
        """Alias emphasizing that ``bin_counts`` follows the segment axis."""

        return self.bin_counts

    @property
    def axial_bin_count(self) -> int:
        return int(self.bin_counts.size)

    @property
    def matched_triangle_count(self) -> int:
        """Number of distinct original STL triangles seen in any axial bin."""

        return int(self.unique_triangle_indices.size)

    def bin_slice(self, bin_index: int) -> slice:
        """Return the flattened match slice for one zero-based axial bin."""

        if isinstance(bin_index, (bool, np.bool_)):
            raise TypeError("bin_index must be an integer")
        index = int(bin_index)
        if index != bin_index or not 0 <= index < self.axial_bin_count:
            raise IndexError(
                f"bin_index {bin_index!r} outside [0, {self.axial_bin_count})"
            )
        return slice(int(self.bin_offsets[index]), int(self.bin_offsets[index + 1]))


@dataclass(frozen=True, slots=True)
class SegmentNearestSurfaceQuery:
    """Immutable nearest STL-surface evidence along one finite XYZ segment.

    There is exactly one original STL triangle, closest surface point, and
    exact point-to-triangle distance per axial bin.  The centroid search is
    deliberately bounded by ``candidates_per_bucket``; distances reported for
    those candidates are geometrically exact, while an adversarial mesh with
    many very large overlapping triangles may require a larger candidate count
    to guarantee that the globally nearest triangle entered the candidate set.
    Radius bucketing substantially reduces that centroid-ranking failure mode.
    """

    start_xyz: tuple[float, float, float]
    end_xyz: tuple[float, float, float]
    endpoint_exclusion_fraction: float
    axial_bin_width: float
    candidates_per_bucket: int
    axial_fractions: NDArray[np.float64]
    bin_centers_xyz: NDArray[np.float64]
    nearest_surface_distances: NDArray[np.float64]
    nearest_surface_points_xyz: NDArray[np.float64]
    triangle_indices: NDArray[np.int64]

    @property
    def axial_bin_count(self) -> int:
        return int(self.axial_fractions.size)


@dataclass(frozen=True, slots=True)
class STLSurfaceIndex:
    """All transformed STL triangles plus a conservative spatial index.

    Use :meth:`from_stl` rather than instantiating the dataclass directly.
    Stored triangles are float32 because binary STL source coordinates already
    have float32 precision.  Transformation arithmetic and all exact distance
    checks use float64.
    """

    path: Path
    transform: NDArray[np.float64]
    triangles_xyz: NDArray[np.float32]
    triangle_centroid_radii: NDArray[np.float32]
    bounds_min_xyz: tuple[float, float, float]
    bounds_max_xyz: tuple[float, float, float]
    estimated_index_bytes: int
    _buckets: tuple[_RadiusBucket, ...]

    @classmethod
    def from_stl(
        cls,
        path: str | PathLike[str],
        *,
        transform: ArrayLike | None = None,
        chunk_faces: int = 100_000,
        base_radius: float = 2.0,
        leafsize: int = 32,
        max_triangles: int = 10_000_000,
        max_index_bytes: int = _DEFAULT_MAX_INDEX_BYTES,
    ) -> "STLSurfaceIndex":
        """Load every STL triangle, transform it, and build centroid trees.

        ``base_radius`` is expressed in transformed XYZ units (native CT voxels
        for this project).  Triangle bounding radii are grouped into doubling
        buckets.  Each query expands a bucket's centroid radius only by that
        bucket's largest member, so unusually large plate triangles do not
        force a global search through millions of small lattice triangles.

        ``max_index_bytes`` is a conservative preflight budget, not a promise
        about SciPy allocator overhead.  No temporary file or persistent cache
        is created.
        """

        chunk_faces = _positive_integer(chunk_faces, name="chunk_faces")
        leafsize = _positive_integer(leafsize, name="leafsize")
        max_triangles = _positive_integer(max_triangles, name="max_triangles")
        max_index_bytes = _positive_integer(max_index_bytes, name="max_index_bytes")
        if not (np.isfinite(base_radius) and base_radius > 0.0):
            raise ValueError("base_radius must be a positive finite number")
        matrix = _affine_transform(transform)

        metadata = inspect_stl(path)
        triangle_count = int(metadata.triangles)
        if triangle_count == 0:
            raise ValueError(f"STL contains no triangles: {metadata.path}")
        if triangle_count > max_triangles:
            raise ValueError(
                f"STL contains {triangle_count:,} triangles, above the "
                f"max_triangles budget of {max_triangles:,}"
            )
        estimate = (
            triangle_count * _ESTIMATED_BYTES_PER_TRIANGLE
            + _INDEX_FIXED_ALLOWANCE_BYTES
        )
        if estimate > max_index_bytes:
            raise ValueError(
                f"estimated STL index size {estimate:,} bytes exceeds "
                f"max_index_bytes={max_index_bytes:,}"
            )

        triangles = np.empty((triangle_count, 3, 3), dtype=np.float32)
        centroids = np.empty((triangle_count, 3), dtype=np.float32)
        radii = np.empty(triangle_count, dtype=np.float32)
        lower = np.full(3, np.inf, dtype=np.float64)
        upper = np.full(3, -np.inf, dtype=np.float64)
        offset = 0
        for chunk in read_stl_triangles(metadata.path, chunk_faces=chunk_faces):
            transformed = apply_transform(chunk.reshape(-1, 3), matrix).reshape(-1, 3, 3)
            stop = offset + transformed.shape[0]
            if stop > triangle_count:
                raise ValueError(
                    "STL yielded more triangles than its inspected metadata; "
                    "the file may have changed while it was being read"
                )
            centers = transformed.mean(axis=1)
            chunk_radii = np.linalg.norm(transformed - centers[:, None, :], axis=2).max(axis=1)
            triangles[offset:stop] = transformed
            centroids[offset:stop] = centers
            radii[offset:stop] = chunk_radii
            lower = np.minimum(lower, transformed.reshape(-1, 3).min(axis=0))
            upper = np.maximum(upper, transformed.reshape(-1, 3).max(axis=0))
            offset = stop
        if offset != triangle_count:
            raise ValueError(
                f"STL yielded {offset:,} triangles after metadata reported "
                f"{triangle_count:,}; the file may have changed while it was read"
            )
        if not np.isfinite(radii).all():
            raise ValueError("transformed STL produced nonfinite triangle radii")

        # Import lazily so lightweight schema/help operations do not require
        # SciPy merely to import this module.
        from scipy.spatial import cKDTree

        scaled = np.maximum(radii.astype(np.float64) / float(base_radius), 1.0)
        bucket_ids = np.ceil(np.log2(scaled)).astype(np.int64)
        buckets: list[_RadiusBucket] = []
        for bucket_id in range(int(bucket_ids.max()) + 1):
            indices = np.flatnonzero(bucket_ids == bucket_id).astype(np.int64, copy=False)
            if indices.size == 0:
                continue
            # cKDTree requires float64 for these source coordinates.  Passing a
            # contiguous array with copy_data=False lets the tree retain this
            # one allocation rather than making another full centroid copy.
            tree_data = np.ascontiguousarray(centroids[indices], dtype=np.float64)
            tree = cKDTree(
                tree_data,
                leafsize=leafsize,
                compact_nodes=True,
                balanced_tree=True,
                copy_data=False,
            )
            _readonly(indices)
            buckets.append(
                _RadiusBucket(indices, float(radii[indices].max()), tree)
            )

        _readonly(matrix)
        _readonly(triangles)
        _readonly(radii)
        return cls(
            path=Path(metadata.path),
            transform=matrix,
            triangles_xyz=triangles,
            triangle_centroid_radii=radii,
            bounds_min_xyz=tuple(float(value) for value in lower),
            bounds_max_xyz=tuple(float(value) for value in upper),
            estimated_index_bytes=int(estimate),
            _buckets=tuple(buckets),
        )

    @property
    def triangle_count(self) -> int:
        return int(self.triangles_xyz.shape[0])

    @property
    def radius_bucket_count(self) -> int:
        return len(self._buckets)

    def triangles_for(self, triangle_indices: ArrayLike) -> NDArray[np.float32]:
        """Return a read-only copy of selected transformed original triangles."""

        raw = np.asarray(triangle_indices)
        if raw.ndim != 1 or raw.dtype.kind not in "iu":
            raise ValueError("triangle_indices must be a one-dimensional integer array")
        indices = raw.astype(np.int64, copy=False)
        if indices.size and (indices.min() < 0 or indices.max() >= self.triangle_count):
            raise IndexError("triangle_indices contains an index outside the STL")
        return _readonly(self.triangles_xyz[indices].copy())

    def query_segment_nearest(
        self,
        start_xyz: ArrayLike,
        end_xyz: ArrayLike,
        *,
        axial_step: float = 1.0,
        endpoint_exclusion_fraction: float = 0.10,
        candidates_per_bucket: int = 32,
        workers: int = 1,
    ) -> SegmentNearestSurfaceQuery:
        """Return one nearest indexed STL-surface match per axial station.

        The method queries ``candidates_per_bucket`` nearest centroids from
        *every* triangle-radius bucket.  It then computes true Euclidean
        point-to-triangle distances, rather than using centroid distance as the
        measurement, and selects the closest original triangle globally across
        the candidate buckets.  This is much cheaper than enumerating every
        triangle in a wide corridor for thousands of lattice edges.

        Axial centers are at most ``axial_step`` apart.  The first and last
        ``endpoint_exclusion_fraction`` of the original segment are omitted to
        suppress shared-junction and build-plate geometry.  Ties are resolved
        by the smallest original triangle index for deterministic results.
        """

        start = _xyz(start_xyz, name="start_xyz")
        end = _xyz(end_xyz, name="end_xyz")
        if not (np.isfinite(axial_step) and axial_step > 0.0):
            raise ValueError("axial_step must be a positive finite number")
        if not (
            np.isfinite(endpoint_exclusion_fraction)
            and 0.0 <= endpoint_exclusion_fraction < 0.5
        ):
            raise ValueError("endpoint_exclusion_fraction must lie in [0, 0.5)")
        candidates_per_bucket = _positive_integer(
            candidates_per_bucket, name="candidates_per_bucket"
        )
        workers = _positive_integer(workers, name="workers")

        direction = end - start
        segment_length = float(np.linalg.norm(direction))
        if segment_length <= np.finfo(np.float64).eps:
            raise ValueError("start_xyz and end_xyz must define a nonzero segment")
        usable_fraction = 1.0 - 2.0 * float(endpoint_exclusion_fraction)
        usable_length = segment_length * usable_fraction
        bin_count = max(1, int(math.ceil(usable_length / float(axial_step))))
        # This fixed safety limit mirrors query_segment's default and prevents
        # an accidental microscopic step from allocating an unbounded result.
        if bin_count > 100_000:
            raise ValueError(
                f"segment requires {bin_count:,} axial bins; increase axial_step"
            )
        local_fractions = (np.arange(bin_count, dtype=np.float64) + 0.5) / bin_count
        axial_fractions = (
            float(endpoint_exclusion_fraction) + usable_fraction * local_fractions
        )
        centers = start + axial_fractions[:, None] * direction
        bin_width = usable_length / bin_count

        # Each list remains small: at most candidates_per_bucket entries for
        # each radius bucket.  Buckets are disjoint, so IDs cannot be duplicated
        # across them, but sorting below also provides deterministic order.
        per_bin_candidates: list[list[NDArray[np.int64]]] = [
            [] for _ in range(bin_count)
        ]
        for bucket in self._buckets:
            candidate_count = min(candidates_per_bucket, bucket.triangle_indices.size)
            try:
                _, local_indices = bucket.tree.query(
                    centers, k=candidate_count, workers=workers
                )
            except TypeError:  # pragma: no cover - compatibility with old SciPy
                _, local_indices = bucket.tree.query(centers, k=candidate_count)
            local_indices = np.asarray(local_indices, dtype=np.int64)
            if local_indices.ndim == 1:
                local_indices = local_indices[:, None]
            for bin_index in range(bin_count):
                per_bin_candidates[bin_index].append(
                    bucket.triangle_indices[local_indices[bin_index]]
                )

        nearest_distances = np.empty(bin_count, dtype=np.float64)
        nearest_points = np.empty((bin_count, 3), dtype=np.float64)
        nearest_indices = np.empty(bin_count, dtype=np.int64)
        for bin_index, candidate_groups in enumerate(per_bin_candidates):
            candidates = np.concatenate(candidate_groups)
            # A sorted unique set makes tie handling independent of cKDTree's
            # internal ordering for equidistant centroids.
            candidates = np.unique(candidates)
            candidate_triangles = self.triangles_xyz[candidates].astype(
                np.float64, copy=False
            )
            closest, squared = _closest_points_on_triangles(
                centers[bin_index], candidate_triangles
            )
            # lexsort's final key is primary: exact squared distance first,
            # then the stable original triangle ID.
            best = int(np.lexsort((candidates, squared))[0])
            nearest_distances[bin_index] = math.sqrt(float(squared[best]))
            nearest_points[bin_index] = closest[best]
            nearest_indices[bin_index] = candidates[best]

        for result_array in (
            axial_fractions,
            centers,
            nearest_distances,
            nearest_points,
            nearest_indices,
        ):
            _readonly(result_array)
        return SegmentNearestSurfaceQuery(
            start_xyz=tuple(float(value) for value in start),
            end_xyz=tuple(float(value) for value in end),
            endpoint_exclusion_fraction=float(endpoint_exclusion_fraction),
            axial_bin_width=float(bin_width),
            candidates_per_bucket=candidates_per_bucket,
            axial_fractions=axial_fractions,
            bin_centers_xyz=centers,
            nearest_surface_distances=nearest_distances,
            nearest_surface_points_xyz=nearest_points,
            triangle_indices=nearest_indices,
        )

    def query_segment(
        self,
        start_xyz: ArrayLike,
        end_xyz: ArrayLike,
        *,
        radius: float,
        axial_step: float = 1.0,
        endpoint_exclusion_fraction: float = 0.0,
        max_axial_bins: int = 100_000,
        exact_chunk_triangles: int = 100_000,
        workers: int = 1,
    ) -> SegmentSurfaceQuery:
        """Query exact STL-surface support along a finite XYZ segment.

        Axial bin centers are spaced no farther apart than ``axial_step``.
        ``endpoint_exclusion_fraction`` removes that fraction at *each* end;
        it must lie in ``[0, 0.5)``.  At every remaining center, this method
        returns every original triangle whose surface lies within ``radius``.

        The centroid trees only produce a conservative superset.  A triangle's
        centroid bounding radius guarantees no true hit is lost, including for
        a large triangle whose centroid is far from the segment.  Exact
        point-to-triangle checks are processed in bounded chunks.
        """

        start = _xyz(start_xyz, name="start_xyz")
        end = _xyz(end_xyz, name="end_xyz")
        if not (np.isfinite(radius) and radius > 0.0):
            raise ValueError("radius must be a positive finite number")
        if not (np.isfinite(axial_step) and axial_step > 0.0):
            raise ValueError("axial_step must be a positive finite number")
        if not (
            np.isfinite(endpoint_exclusion_fraction)
            and 0.0 <= endpoint_exclusion_fraction < 0.5
        ):
            raise ValueError("endpoint_exclusion_fraction must lie in [0, 0.5)")
        max_axial_bins = _positive_integer(max_axial_bins, name="max_axial_bins")
        exact_chunk_triangles = _positive_integer(
            exact_chunk_triangles, name="exact_chunk_triangles"
        )
        workers = _positive_integer(workers, name="workers")

        direction = end - start
        segment_length = float(np.linalg.norm(direction))
        if segment_length <= np.finfo(np.float64).eps:
            raise ValueError("start_xyz and end_xyz must define a nonzero segment")
        usable_fraction = 1.0 - 2.0 * float(endpoint_exclusion_fraction)
        usable_length = segment_length * usable_fraction
        bin_count = max(1, int(math.ceil(usable_length / float(axial_step))))
        if bin_count > max_axial_bins:
            raise ValueError(
                f"segment requires {bin_count:,} axial bins, above "
                f"max_axial_bins={max_axial_bins:,}"
            )
        local_fractions = (np.arange(bin_count, dtype=np.float64) + 0.5) / bin_count
        axial_fractions = (
            float(endpoint_exclusion_fraction) + usable_fraction * local_fractions
        )
        centers = start + axial_fractions[:, None] * direction
        bin_width = usable_length / bin_count

        per_bin_indices: list[list[NDArray[np.int64]]] = [
            [] for _ in range(bin_count)
        ]
        per_bin_distances: list[list[NDArray[np.float64]]] = [
            [] for _ in range(bin_count)
        ]
        per_bin_points: list[list[NDArray[np.float64]]] = [
            [] for _ in range(bin_count)
        ]
        radius_squared = float(radius) ** 2
        distance_tolerance = max(1e-12, radius_squared * 1e-12)

        for bucket in self._buckets:
            search_radius = float(radius) + bucket.maximum_radius
            try:
                candidate_lists = bucket.tree.query_ball_point(
                    centers, search_radius, workers=workers
                )
            except TypeError:  # pragma: no cover - compatibility with old SciPy
                candidate_lists = bucket.tree.query_ball_point(centers, search_radius)
            for bin_index, local_candidates in enumerate(candidate_lists):
                if not local_candidates:
                    continue
                local_indices = np.asarray(local_candidates, dtype=np.int64)
                global_indices = bucket.triangle_indices[local_indices]
                for begin in range(0, global_indices.size, exact_chunk_triangles):
                    selected = global_indices[begin:begin + exact_chunk_triangles]
                    candidate_triangles = self.triangles_xyz[selected].astype(
                        np.float64, copy=False
                    )
                    closest, squared = _closest_points_on_triangles(
                        centers[bin_index], candidate_triangles
                    )
                    accepted = squared <= radius_squared + distance_tolerance
                    if not np.any(accepted):
                        continue
                    per_bin_indices[bin_index].append(selected[accepted])
                    per_bin_distances[bin_index].append(np.sqrt(squared[accepted]))
                    per_bin_points[bin_index].append(closest[accepted])

        counts = np.zeros(bin_count, dtype=np.int64)
        offsets = np.zeros(bin_count + 1, dtype=np.int64)
        nearest_distances = np.full(bin_count, np.inf, dtype=np.float64)
        nearest_points = np.full((bin_count, 3), np.nan, dtype=np.float64)
        flattened_indices: list[NDArray[np.int64]] = []
        flattened_distances: list[NDArray[np.float64]] = []
        flattened_points: list[NDArray[np.float64]] = []
        for bin_index in range(bin_count):
            if not per_bin_indices[bin_index]:
                offsets[bin_index + 1] = offsets[bin_index]
                continue
            indices = np.concatenate(per_bin_indices[bin_index])
            distances = np.concatenate(per_bin_distances[bin_index])
            points = np.concatenate(per_bin_points[bin_index], axis=0)
            order = np.argsort(indices, kind="stable")
            indices = indices[order]
            distances = distances[order]
            points = points[order]
            counts[bin_index] = indices.size
            offsets[bin_index + 1] = offsets[bin_index] + indices.size
            nearest = int(np.argmin(distances))
            nearest_distances[bin_index] = distances[nearest]
            nearest_points[bin_index] = points[nearest]
            flattened_indices.append(indices)
            flattened_distances.append(distances)
            flattened_points.append(points)

        if flattened_indices:
            triangle_indices = np.concatenate(flattened_indices).astype(np.int64, copy=False)
            surface_distances = np.concatenate(flattened_distances).astype(
                np.float64, copy=False
            )
            surface_points = np.concatenate(flattened_points, axis=0).astype(
                np.float64, copy=False
            )
            unique_indices = np.unique(triangle_indices)
        else:
            triangle_indices = np.empty(0, dtype=np.int64)
            surface_distances = np.empty(0, dtype=np.float64)
            surface_points = np.empty((0, 3), dtype=np.float64)
            unique_indices = np.empty(0, dtype=np.int64)

        for result_array in (
            axial_fractions,
            centers,
            counts,
            offsets,
            triangle_indices,
            surface_distances,
            surface_points,
            nearest_distances,
            nearest_points,
            unique_indices,
        ):
            _readonly(result_array)
        return SegmentSurfaceQuery(
            start_xyz=tuple(float(value) for value in start),
            end_xyz=tuple(float(value) for value in end),
            radius=float(radius),
            endpoint_exclusion_fraction=float(endpoint_exclusion_fraction),
            axial_bin_width=float(bin_width),
            axial_fractions=axial_fractions,
            bin_centers_xyz=centers,
            bin_counts=counts,
            bin_offsets=offsets,
            triangle_indices=triangle_indices,
            surface_distances=surface_distances,
            surface_points_xyz=surface_points,
            nearest_surface_distances=nearest_distances,
            nearest_surface_points_xyz=nearest_points,
            unique_triangle_indices=unique_indices,
        )


__all__ = [
    "STLSurfaceIndex",
    "SegmentNearestSurfaceQuery",
    "SegmentSurfaceQuery",
]
