"""Convert a lattice graph into a triangle mesh and write it as binary STL.

A registered lattice JSON is a graph -- junction positions plus strut endpoint
references -- so mesh viewers such as MeshLab cannot open it directly. Each
strut is swept into a capped cylinder here and the union is written as one
binary STL.

STL stores unindexed triangles with no color and no vertex sharing, so the file
is larger than the equivalent PLY and carries no per-strut identity. Use
``Components.tiff_mesh.write_binary_ply`` when color or size matters.

Importing this module performs no I/O.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path
import struct
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .lattice_graph import LatticeGraph
from .reporting import atomic_write_bytes


STL_TRIANGLE_DTYPE = np.dtype(
    [("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
)
"""Packed 50-byte binary-STL triangle record."""

STL_HEADER_BYTES = 80
MINIMUM_SEGMENTS = 6


class LatticeSTLError(ValueError):
    """Raised when lattice geometry cannot be turned into a valid mesh."""


def _orthonormal_basis(directions: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return two unit vectors spanning the plane normal to each direction."""

    count = len(directions)
    reference = np.zeros((count, 3), dtype=np.float64)
    reference[np.arange(count), np.argmin(np.abs(directions), axis=1)] = 1.0
    first = np.cross(directions, reference)
    norms = np.linalg.norm(first, axis=1, keepdims=True)
    if not np.all(norms > 0.0):
        raise LatticeSTLError("degenerate strut direction produced a zero basis vector")
    first /= norms
    second = np.cross(directions, first)
    return first, second


def strut_endpoints(
    graph: LatticeGraph, *, minimum_length: float = 1e-9
) -> tuple[NDArray[np.float64], NDArray[np.float64], list[int]]:
    """Resolve strut endpoint coordinates, dropping unusable struts.

    Returns start points, end points, and the IDs of struts skipped because an
    endpoint is missing, non-finite, or the two endpoints coincide.
    """

    junctions = graph.junction_by_id()
    starts: list[tuple[float, float, float]] = []
    ends: list[tuple[float, float, float]] = []
    skipped: list[int] = []
    for strut in graph.struts:
        first = junctions.get(strut.junction0)
        second = junctions.get(strut.junction1)
        if first is None or second is None:
            skipped.append(strut.id)
            continue
        start = np.asarray(first.position, dtype=np.float64)
        end = np.asarray(second.position, dtype=np.float64)
        if not (np.isfinite(start).all() and np.isfinite(end).all()):
            skipped.append(strut.id)
            continue
        if float(np.linalg.norm(end - start)) <= minimum_length:
            skipped.append(strut.id)
            continue
        starts.append(tuple(start))
        ends.append(tuple(end))
    if not starts:
        return (
            np.empty((0, 3), dtype=np.float64),
            np.empty((0, 3), dtype=np.float64),
            skipped,
        )
    return (
        np.asarray(starts, dtype=np.float64),
        np.asarray(ends, dtype=np.float64),
        skipped,
    )


def cylinder_triangles(
    starts: NDArray[np.float64],
    ends: NDArray[np.float64],
    radius: float,
    *,
    segments: int = 12,
) -> NDArray[np.float64]:
    """Sweep every start/end pair into a capped cylinder of triangles.

    Returns an ``(N * 4 * segments, 3, 3)`` array of triangle corner points,
    wound counter-clockwise when viewed from outside the surface.
    """

    starts = np.asarray(starts, dtype=np.float64)
    ends = np.asarray(ends, dtype=np.float64)
    if starts.shape != ends.shape or starts.ndim != 2 or starts.shape[1:] != (3,):
        raise LatticeSTLError("starts and ends must be matching (N, 3) arrays")
    if not isinstance(segments, (int, np.integer)) or int(segments) < MINIMUM_SEGMENTS:
        raise LatticeSTLError(f"segments must be an integer >= {MINIMUM_SEGMENTS}")
    if not np.isfinite(radius) or radius <= 0.0:
        raise LatticeSTLError("radius must be finite and positive")
    if len(starts) == 0:
        return np.empty((0, 3, 3), dtype=np.float64)
    if not (np.isfinite(starts).all() and np.isfinite(ends).all()):
        raise LatticeSTLError("endpoints must be finite")

    segments = int(segments)
    directions = ends - starts
    lengths = np.linalg.norm(directions, axis=1, keepdims=True)
    if not np.all(lengths > 0.0):
        raise LatticeSTLError("cylinder endpoints must be distinct")
    directions = directions / lengths

    axis_u, axis_v = _orthonormal_basis(directions)
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    # (N, segments, 3) ring offsets around each strut axis.
    ring = radius * (
        np.cos(angles)[None, :, None] * axis_u[:, None, :]
        + np.sin(angles)[None, :, None] * axis_v[:, None, :]
    )
    lower = starts[:, None, :] + ring
    upper = ends[:, None, :] + ring
    lower_centre = np.broadcast_to(starts[:, None, :], lower.shape)
    upper_centre = np.broadcast_to(ends[:, None, :], upper.shape)

    index = np.arange(segments)
    following = (index + 1) % segments
    faces = np.concatenate(
        (
            np.stack((lower[:, index], lower[:, following], upper[:, index]), axis=2),
            np.stack((lower[:, following], upper[:, following], upper[:, index]), axis=2),
            np.stack((lower_centre, lower[:, following], lower[:, index]), axis=2),
            np.stack((upper_centre, upper[:, index], upper[:, following]), axis=2),
        ),
        axis=1,
    )
    return faces.reshape(-1, 3, 3)


def triangle_normals(triangles: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return unit face normals; degenerate triangles get a zero normal."""

    triangles = np.asarray(triangles, dtype=np.float64)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise LatticeSTLError("triangles must have shape (N, 3, 3)")
    normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    return np.divide(normals, norms, out=np.zeros_like(normals), where=norms > 0.0)


def binary_stl_bytes(triangles: NDArray[np.float64], *, header: str = "") -> bytes:
    """Serialize triangles into the 80-byte-header binary STL layout."""

    triangles = np.asarray(triangles, dtype=np.float64)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise LatticeSTLError("triangles must have shape (N, 3, 3)")
    if triangles.size and not np.isfinite(triangles).all():
        raise LatticeSTLError("triangles must be finite")
    records = np.zeros(len(triangles), dtype=STL_TRIANGLE_DTYPE)
    records["normal"] = triangle_normals(triangles).astype(np.float32)
    records["vertices"] = triangles.astype(np.float32)
    banner = header.replace("\n", " ").replace("\r", " ").encode("ascii", "replace")
    return b"".join(
        (
            banner[:STL_HEADER_BYTES].ljust(STL_HEADER_BYTES, b"\0"),
            struct.pack("<I", len(triangles)),
            records.tobytes(),
        )
    )


def write_binary_stl(
    path: str | PathLike[str],
    triangles: NDArray[np.float64],
    *,
    header: str = "",
    create_parents: bool = True,
) -> Path:
    """Atomically write ``triangles`` to ``path`` as binary STL."""

    return atomic_write_bytes(
        path, binary_stl_bytes(triangles, header=header), create_parents=create_parents
    )


def lattice_to_stl(
    graph: LatticeGraph,
    output_stl: str | PathLike[str],
    *,
    radius: float = 3.0,
    segments: int = 12,
    header: str = "",
) -> dict[str, Any]:
    """Write every usable strut of ``graph`` to ``output_stl`` as tubes."""

    starts, ends, skipped = strut_endpoints(graph)
    if len(starts) == 0:
        raise LatticeSTLError("lattice contains no drawable struts")
    triangles = cylinder_triangles(starts, ends, radius, segments=segments)
    banner = header or (
        f"lattice {len(starts)} struts r={radius} seg={segments} XYZ voxels"
    )
    destination = write_binary_stl(output_stl, triangles, header=banner)
    lower = triangles.reshape(-1, 3).min(axis=0)
    upper = triangles.reshape(-1, 3).max(axis=0)
    return {
        "stl": str(destination),
        "junction_count": len(graph.junctions),
        "strut_count": len(graph.struts),
        "drawn_strut_count": int(len(starts)),
        "skipped_strut_count": len(skipped),
        "skipped_strut_ids": skipped[:20],
        "triangle_count": int(len(triangles)),
        "bytes": destination.stat().st_size,
        "radius_voxels": float(radius),
        "segments": int(segments),
        "bounds_min_xyz": [float(value) for value in lower],
        "bounds_max_xyz": [float(value) for value in upper],
    }
