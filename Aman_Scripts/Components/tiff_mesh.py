"""Memory-conscious conversion of scalar TIFF volumes into indexed PLY meshes.

The project TIFF arrays use NumPy's ``ZYX`` axis order, whereas mesh viewers use
Cartesian ``XYZ`` coordinates.  This module keeps that distinction explicit,
extracts marching-cubes surfaces in overlapping Z slabs, and stitches vertices
on shared slab planes.  It contains no project-specific defect logic.
"""

from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np


class TIFFMeshError(RuntimeError):
    """Raised when a volume cannot safely produce a trustworthy surface mesh."""


@dataclass(frozen=True)
class BoundsZYX:
    """Half-open integer bounds in array order: ``start <= index < stop``."""

    start: tuple[int, int, int]
    stop: tuple[int, int, int]

    @property
    def shape(self) -> tuple[int, int, int]:
        """Return the extent of the bounded region in ZYX order."""

        return tuple(stop - start for start, stop in zip(self.start, self.stop))


@dataclass(frozen=True)
class ForegroundProfile:
    """Threshold occupancy and an estimated surface workload."""

    threshold: float
    foreground_voxels: int
    total_voxels: int
    fraction: float
    bounds: BoundsZYX
    axis_transition_faces: int
    estimated_triangles: int


@dataclass(frozen=True)
class ResourceEstimate:
    """Conservative storage and memory estimates derived from mask transitions."""

    estimated_vertices: int
    estimated_triangles: int
    estimated_ply_bytes: int
    estimated_peak_bytes: int
    required_free_disk_bytes: int


@dataclass(frozen=True)
class MeshChunks:
    """Indexed mesh arrays retained as chunks to avoid an extra concatenation copy."""

    vertices_xyz: tuple[np.ndarray, ...]
    faces: tuple[np.ndarray, ...]
    vertex_count: int
    face_count: int
    bounds_min_xyz: tuple[float, float, float]
    bounds_max_xyz: tuple[float, float, float]
    slabs_processed: int
    seam_vertices_reused: int


@dataclass(frozen=True)
class PLYMetadata:
    """Header counts and measured vertex bounds from this module's binary PLY."""

    path: Path
    vertex_count: int
    face_count: int
    bounds_min_xyz: tuple[float, float, float] | None
    bounds_max_xyz: tuple[float, float, float] | None
    bytes: int


def validate_scalar_volume(volume: np.ndarray) -> tuple[int, int, int]:
    """Validate a finite, numeric, three-dimensional scalar volume.

    The return value is normalized to plain Python integers so it is safe to
    place in JSON manifests.  The check samples non-integer arrays for finite
    values without creating a second full-volume copy.
    """

    if not isinstance(volume, np.ndarray):
        raise TypeError("volume must be a NumPy array or memory map")
    if volume.ndim != 3:
        raise TIFFMeshError(f"expected a 3D ZYX volume, received shape {volume.shape}")
    if any(int(size) < 2 for size in volume.shape):
        raise TIFFMeshError("all volume axes must contain at least two samples")
    if volume.dtype.kind not in "uibf":
        raise TIFFMeshError(f"volume dtype must be numeric, received {volume.dtype}")
    if volume.dtype.kind in "fc":
        for z_start in range(0, volume.shape[0], 32):
            if not np.isfinite(volume[z_start : z_start + 32]).all():
                raise TIFFMeshError("volume contains NaN or infinity")
    return tuple(int(value) for value in volume.shape)


def iter_z_chunks(volume: np.ndarray, depth: int) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(z_start, view)`` pairs without materializing the full volume."""

    validate_scalar_volume(volume)
    if depth < 1:
        raise ValueError("chunk depth must be positive")
    for z_start in range(0, volume.shape[0], depth):
        yield z_start, volume[z_start : min(z_start + depth, volume.shape[0])]


def streaming_integer_histogram(
    volume: np.ndarray, *, chunk_depth: int = 16
) -> tuple[np.ndarray, int]:
    """Count every value in an unsigned/signed integer volume, chunk by chunk.

    The histogram begins at the dtype's representable minimum.  The companion
    integer is that offset, allowing Otsu's bin index to be converted back into
    the original CT intensity scale.
    """

    validate_scalar_volume(volume)
    if volume.dtype.kind not in "ui":
        raise TIFFMeshError("streaming_integer_histogram requires an integer volume")
    info = np.iinfo(volume.dtype)
    bins = int(info.max) - int(info.min) + 1
    if bins > 1_000_000:
        raise TIFFMeshError(f"integer dtype range is too large for an exact histogram: {bins}")
    histogram = np.zeros(bins, dtype=np.uint64)
    offset = int(info.min)
    for _, chunk in iter_z_chunks(volume, chunk_depth):
        shifted = np.asarray(chunk, dtype=np.int64).reshape(-1) - offset
        histogram += np.bincount(shifted, minlength=bins).astype(np.uint64, copy=False)
    return histogram, offset


def otsu_threshold_from_histogram(histogram: np.ndarray, *, offset: int = 0) -> float:
    """Return the deterministic global Otsu threshold represented by a histogram."""

    counts = np.asarray(histogram)
    if counts.ndim != 1 or counts.size < 2 or counts.dtype.kind not in "uif":
        raise ValueError("histogram must be a one-dimensional numeric array with at least two bins")
    if not np.isfinite(counts).all() or np.any(counts < 0):
        raise ValueError("histogram counts must be finite and nonnegative")
    total = float(counts.sum())
    nonzero = np.flatnonzero(counts)
    if total <= 0 or nonzero.size < 2:
        raise TIFFMeshError("Otsu threshold requires at least two populated intensity bins")
    levels = np.arange(counts.size, dtype=np.float64)
    weight_low = np.cumsum(counts, dtype=np.float64)
    weighted_low = np.cumsum(counts * levels, dtype=np.float64)
    weight_high = total - weight_low
    valid = (weight_low > 0) & (weight_high > 0)
    mean_low = np.zeros_like(levels)
    mean_high = np.zeros_like(levels)
    mean_low[valid] = weighted_low[valid] / weight_low[valid]
    mean_high[valid] = (weighted_low[-1] - weighted_low[valid]) / weight_high[valid]
    between = np.full_like(levels, -np.inf)
    between[valid] = weight_low[valid] * weight_high[valid] * (
        mean_low[valid] - mean_high[valid]
    ) ** 2
    index = int(np.argmax(between))
    return float(index + int(offset))


def foreground_profile(
    volume: np.ndarray,
    threshold: float,
    *,
    chunk_depth: int = 16,
    padding: int = 2,
) -> ForegroundProfile:
    """Measure ``volume > threshold`` occupancy, bounds, and mask transitions.

    Strict ``>`` matches marching cubes: samples equal to the isovalue remain on
    the background side.  Axis transitions provide a reproducible, inexpensive
    proxy for the number of triangles before surface extraction begins.
    """

    shape = validate_scalar_volume(volume)
    if not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if padding < 0:
        raise ValueError("padding cannot be negative")
    count = 0
    transitions = 0
    minimum = np.array(shape, dtype=np.int64)
    maximum = np.full(3, -1, dtype=np.int64)
    previous_last: np.ndarray | None = None
    for z_start, chunk in iter_z_chunks(volume, chunk_depth):
        mask = np.asarray(chunk) > threshold
        local_count = int(np.count_nonzero(mask))
        count += local_count
        if local_count:
            z_any = np.any(mask, axis=(1, 2))
            y_any = np.any(mask, axis=(0, 2))
            x_any = np.any(mask, axis=(0, 1))
            z_indices = np.flatnonzero(z_any) + z_start
            y_indices = np.flatnonzero(y_any)
            x_indices = np.flatnonzero(x_any)
            minimum = np.minimum(minimum, (z_indices[0], y_indices[0], x_indices[0]))
            maximum = np.maximum(maximum, (z_indices[-1], y_indices[-1], x_indices[-1]))
        transitions += int(np.count_nonzero(mask[1:] != mask[:-1]))
        transitions += int(np.count_nonzero(mask[:, 1:] != mask[:, :-1]))
        transitions += int(np.count_nonzero(mask[:, :, 1:] != mask[:, :, :-1]))
        if previous_last is not None:
            transitions += int(np.count_nonzero(mask[0] != previous_last))
        previous_last = mask[-1].copy()
    total = int(np.prod(shape, dtype=np.int64))
    if count == 0:
        raise TIFFMeshError("threshold selected no foreground voxels")
    start = np.maximum(minimum - padding, 0)
    stop = np.minimum(maximum + padding + 1, np.asarray(shape))
    bounds = BoundsZYX(
        tuple(int(value) for value in start),
        tuple(int(value) for value in stop),
    )
    return ForegroundProfile(
        threshold=float(threshold),
        foreground_voxels=count,
        total_voxels=total,
        fraction=count / total,
        bounds=bounds,
        axis_transition_faces=transitions,
        estimated_triangles=max(1, 2 * transitions),
    )


def validate_foreground_profile(
    profile: ForegroundProfile,
    *,
    minimum_fraction: float = 1e-5,
    maximum_fraction: float = 0.45,
) -> None:
    """Reject thresholds that are implausible for a sparse metal lattice CT."""

    if not 0 <= minimum_fraction < maximum_fraction <= 1:
        raise ValueError("foreground fraction limits must satisfy 0 <= min < max <= 1")
    if profile.fraction < minimum_fraction:
        raise TIFFMeshError(
            f"foreground fraction {profile.fraction:.6%} is below the safe minimum "
            f"{minimum_fraction:.6%}"
        )
    if profile.fraction > maximum_fraction:
        raise TIFFMeshError(
            f"foreground fraction {profile.fraction:.6%} exceeds the safe maximum "
            f"{maximum_fraction:.6%}"
        )
    if any(size < 2 for size in profile.bounds.shape):
        raise TIFFMeshError(f"foreground bounds are too small for a surface: {profile.bounds}")


def estimate_resources(profile: ForegroundProfile) -> ResourceEstimate:
    """Estimate PLY size and peak memory from observed binary-mask transitions."""

    triangles = int(profile.estimated_triangles)
    vertices = max(3, triangles // 2 + 2)
    header_allowance = 1024
    ply_bytes = header_allowance + 12 * vertices + 13 * triangles
    cropped_voxels = int(np.prod(profile.bounds.shape, dtype=np.int64))
    # Float marching-cubes input, output arrays, Python/NumPy overhead, and a
    # safety margin.  Slab processing normally stays well below this bound.
    peak = 4 * cropped_voxels + 24 * vertices + 20 * triangles + (512 << 20)
    required_disk = max(1 << 30, int(ply_bytes * 1.35))
    return ResourceEstimate(vertices, triangles, ply_bytes, peak, required_disk)


def validate_resources(
    estimate: ResourceEstimate,
    *,
    free_disk_bytes: int,
    available_memory_bytes: int | None = None,
) -> None:
    """Fail before meshing when estimated output cannot be written safely."""

    if free_disk_bytes < 0 or (available_memory_bytes is not None and available_memory_bytes < 0):
        raise ValueError("resource byte counts cannot be negative")
    if free_disk_bytes < estimate.required_free_disk_bytes:
        raise TIFFMeshError(
            f"insufficient free disk: need approximately {estimate.required_free_disk_bytes} "
            f"bytes, found {free_disk_bytes}"
        )
    if available_memory_bytes is not None and available_memory_bytes < min(
        estimate.estimated_peak_bytes, 1 << 30
    ):
        raise TIFFMeshError(
            f"insufficient available memory: estimated need {estimate.estimated_peak_bytes} "
            f"bytes, found {available_memory_bytes}"
        )


def _seam_key(vertex_zyx: np.ndarray) -> tuple[float, float, float]:
    """Create a stable key for a marching-cubes vertex on a shared slab plane."""

    return tuple(float(value) for value in np.round(vertex_zyx, decimals=6))


def extract_surface_slabbed(
    volume: np.ndarray,
    threshold: float,
    bounds: BoundsZYX,
    *,
    slab_depth: int = 64,
    voxel_spacing_xyz: Sequence[float] = (1.0, 1.0, 1.0),
) -> MeshChunks:
    """Extract and stitch a native-resolution marching-cubes surface.

    Each slab owns a disjoint range of Z cells but includes the final sample
    plane required to close those cells.  Vertices repeated on the next slab's
    first plane reuse their prior global indices, eliminating visible seams.
    """

    from skimage import measure

    shape = validate_scalar_volume(volume)
    if slab_depth < 1:
        raise ValueError("slab_depth must be positive")
    spacing = np.asarray(tuple(voxel_spacing_xyz), dtype=np.float64)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("voxel_spacing_xyz must contain three finite positive values")
    if any(start < 0 for start in bounds.start) or any(
        stop > size for stop, size in zip(bounds.stop, shape)
    ) or any(start >= stop for start, stop in zip(bounds.start, bounds.stop)):
        raise ValueError(f"invalid bounds {bounds} for volume shape {shape}")
    z_first, y_first, x_first = bounds.start
    z_stop, y_stop, x_stop = bounds.stop
    if z_stop - z_first < 2 or y_stop - y_first < 2 or x_stop - x_first < 2:
        raise TIFFMeshError("surface bounds must include at least two samples per axis")

    vertex_chunks: list[np.ndarray] = []
    face_chunks: list[np.ndarray] = []
    global_vertex_count = 0
    face_count = 0
    seam_reused = 0
    slabs_processed = 0
    previous_upper: dict[tuple[float, float, float], int] = {}
    bounds_min = np.full(3, np.inf)
    bounds_max = np.full(3, -np.inf)

    # Cells occupy [z_first, z_stop - 1).  A slab ending at cell c includes
    # sample plane c so its final cells have both endpoints.
    for cell_start in range(z_first, z_stop - 1, slab_depth):
        cell_stop = min(cell_start + slab_depth, z_stop - 1)
        block = np.asarray(
            volume[cell_start : cell_stop + 1, y_first:y_stop, x_first:x_stop]
        )
        block_min, block_max = float(np.min(block)), float(np.max(block))
        if not (block_min <= threshold <= block_max) or block_min == block_max:
            previous_upper = {}
            continue
        vertices_zyx, faces, _normals, _values = measure.marching_cubes(
            block, level=float(threshold), allow_degenerate=False
        )
        vertices_zyx += np.asarray((cell_start, y_first, x_first), dtype=np.float32)
        local_to_global = np.empty(len(vertices_zyx), dtype=np.uint64)
        keep = np.ones(len(vertices_zyx), dtype=bool)

        if previous_upper:
            lower_indices = np.flatnonzero(
                np.isclose(vertices_zyx[:, 0], float(cell_start), atol=1e-6)
            )
            for local_index in lower_indices:
                existing = previous_upper.get(_seam_key(vertices_zyx[local_index]))
                if existing is not None:
                    local_to_global[local_index] = existing
                    keep[local_index] = False
                    seam_reused += 1

        new_indices = np.flatnonzero(keep)
        if global_vertex_count + len(new_indices) > np.iinfo(np.uint32).max:
            raise TIFFMeshError("mesh exceeds binary PLY uint32 vertex-index capacity")
        local_to_global[new_indices] = np.arange(
            global_vertex_count,
            global_vertex_count + len(new_indices),
            dtype=np.uint64,
        )

        kept_zyx = vertices_zyx[keep]
        kept_xyz = kept_zyx[:, ::-1].astype(np.float32, copy=False)
        kept_xyz *= spacing.astype(np.float32)
        if len(kept_xyz):
            bounds_min = np.minimum(bounds_min, np.min(kept_xyz, axis=0))
            bounds_max = np.maximum(bounds_max, np.max(kept_xyz, axis=0))
            vertex_chunks.append(np.ascontiguousarray(kept_xyz, dtype="<f4"))

        # Reversing ZYX into XYZ is a reflection; swap two face vertices to
        # preserve the original outward winding direction.
        global_faces = local_to_global[faces[:, (0, 2, 1)]].astype(np.uint32, copy=False)
        face_chunks.append(np.ascontiguousarray(global_faces, dtype="<u4"))

        upper_indices = np.flatnonzero(
            np.isclose(vertices_zyx[:, 0], float(cell_stop), atol=1e-6)
        )
        previous_upper = {
            _seam_key(vertices_zyx[index]): int(local_to_global[index])
            for index in upper_indices
        }
        global_vertex_count += len(new_indices)
        face_count += len(global_faces)
        slabs_processed += 1

    if global_vertex_count == 0 or face_count == 0:
        raise TIFFMeshError("marching cubes produced an empty surface")
    return MeshChunks(
        vertices_xyz=tuple(vertex_chunks),
        faces=tuple(face_chunks),
        vertex_count=int(global_vertex_count),
        face_count=int(face_count),
        bounds_min_xyz=tuple(float(value) for value in bounds_min),
        bounds_max_xyz=tuple(float(value) for value in bounds_max),
        slabs_processed=slabs_processed,
        seam_vertices_reused=seam_reused,
    )


def _validate_mesh_chunks(mesh: MeshChunks) -> None:
    """Check chunk counts, shapes, finiteness, and face-index integrity."""

    if sum(len(chunk) for chunk in mesh.vertices_xyz) != mesh.vertex_count:
        raise TIFFMeshError("vertex chunk lengths do not match vertex_count")
    if sum(len(chunk) for chunk in mesh.faces) != mesh.face_count:
        raise TIFFMeshError("face chunk lengths do not match face_count")
    for vertices in mesh.vertices_xyz:
        if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
            raise TIFFMeshError("vertex chunks must have finite shape (N, 3)")
    for faces in mesh.faces:
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise TIFFMeshError("face chunks must have shape (M, 3)")
        if faces.size and int(np.max(faces)) >= mesh.vertex_count:
            raise TIFFMeshError("face references a nonexistent vertex")


def write_binary_ply(
    path: str | PathLike[str],
    mesh: MeshChunks,
    *,
    create_parents: bool = False,
    comments: Sequence[str] = (),
) -> Path:
    """Atomically write an indexed binary little-endian PLY for MeshLab."""

    _validate_mesh_chunks(mesh)
    destination = Path(path).expanduser().resolve(strict=False)
    if create_parents:
        destination.parent.mkdir(parents=True, exist_ok=True)
    elif not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    clean_comments = [str(item).replace("\n", " ").replace("\r", " ") for item in comments]
    header_lines = [
        "ply",
        "format binary_little_endian 1.0",
        "comment generated by Scripts/Components/tiff_mesh.py",
        *(f"comment {item}" for item in clean_comments),
        f"element vertex {mesh.vertex_count}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {mesh.face_count}",
        "property list uchar uint vertex_indices",
        "end_header",
        "",
    ]
    temporary_name: str | None = None
    destination_mode = destination.stat().st_mode & 0o777 if destination.exists() else 0o644
    face_dtype = np.dtype([("count", "u1"), ("indices", "<u4", (3,))])
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write("\n".join(header_lines).encode("ascii"))
            for vertices in mesh.vertices_xyz:
                handle.write(np.asarray(vertices, dtype="<f4").tobytes(order="C"))
            for faces in mesh.faces:
                records = np.empty(len(faces), dtype=face_dtype)
                records["count"] = 3
                records["indices"] = np.asarray(faces, dtype="<u4")
                handle.write(records.tobytes(order="C"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, destination_mode)
        os.replace(temporary_name, destination)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def inspect_binary_ply(path: str | PathLike[str]) -> PLYMetadata:
    """Stream this module's PLY header, vertex bounds, and triangle records.

    The payload is deliberately validated in bounded chunks so checking a
    maximum-detail mesh does not create a second multi-gigabyte in-memory copy.
    """

    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise IsADirectoryError(source)
    vertex_count: int | None = None
    face_count: int | None = None
    with source.open("rb") as handle:
        first = handle.readline()
        if first != b"ply\n":
            raise TIFFMeshError("file is not a PLY document")
        while True:
            raw = handle.readline()
            if not raw:
                raise TIFFMeshError("PLY header is missing end_header")
            try:
                line = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise TIFFMeshError("PLY header is not ASCII") from exc
            if line == "format binary_little_endian 1.0":
                continue
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[-1])
            elif line.startswith("element face "):
                face_count = int(line.split()[-1])
            elif line == "end_header":
                break
        if vertex_count is None or face_count is None:
            raise TIFFMeshError("PLY header lacks vertex or face counts")
        payload_start = handle.tell()
        expected_bytes = payload_start + 12 * vertex_count + 13 * face_count
        if source.stat().st_size != expected_bytes:
            raise TIFFMeshError(
                f"PLY payload size mismatch: expected {expected_bytes}, "
                f"found {source.stat().st_size}"
            )
        bounds_min = np.full(3, np.inf)
        bounds_max = np.full(3, -np.inf)
        vertices_remaining = vertex_count
        while vertices_remaining:
            count = min(vertices_remaining, 1_000_000)
            vertices = np.fromfile(handle, dtype="<f4", count=count * 3)
            if vertices.size != count * 3:
                raise TIFFMeshError("PLY vertex payload is truncated")
            vertices = vertices.reshape((-1, 3))
            if not np.isfinite(vertices).all():
                raise TIFFMeshError("PLY contains a nonfinite vertex")
            bounds_min = np.minimum(bounds_min, vertices.min(axis=0))
            bounds_max = np.maximum(bounds_max, vertices.max(axis=0))
            vertices_remaining -= count
        face_dtype = np.dtype([("count", "u1"), ("indices", "<u4", (3,))])
        faces_remaining = face_count
        while faces_remaining:
            count = min(faces_remaining, 1_000_000)
            faces = np.fromfile(handle, dtype=face_dtype, count=count)
            if len(faces) != count:
                raise TIFFMeshError("PLY face payload is truncated")
            if np.any(faces["count"] != 3) or int(faces["indices"].max()) >= vertex_count:
                raise TIFFMeshError("PLY contains invalid triangle records")
            faces_remaining -= count
        if handle.read(1):
            raise TIFFMeshError("PLY contains unexpected trailing bytes")
    minimum = None if not vertex_count else tuple(float(value) for value in bounds_min)
    maximum = None if not vertex_count else tuple(float(value) for value in bounds_max)
    return PLYMetadata(
        path=source,
        vertex_count=vertex_count,
        face_count=face_count,
        bounds_min_xyz=minimum,
        bounds_max_xyz=maximum,
        bytes=source.stat().st_size,
    )


def available_memory_bytes() -> int | None:
    """Return an OS estimate of available RAM when the platform exposes one."""

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    if not isinstance(page_size, int) or not isinstance(available_pages, int):
        return None
    return int(page_size * available_pages)
