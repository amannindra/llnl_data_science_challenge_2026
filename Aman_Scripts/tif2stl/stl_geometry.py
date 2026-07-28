"""Streaming STL triangle access and deterministic surface densification.

Coordinates follow the repository convention: STL vertices are ``(x, y, z)``.
Importing this module performs no I/O and writes nothing.
"""

from __future__ import annotations

import struct
from os import PathLike
from pathlib import Path
from typing import Iterator

import numpy as np

from Components.asset_io import AssetNotMaterializedError, detect_lfs_pointer


_BINARY_HEADER_BYTES = 84
_BINARY_RECORD = np.dtype([
    ("normal", "<f4", (3,)),
    ("vertices", "<f4", (3, 3)),
    ("attributes", "<u2"),
])


def _materialized(path: str | PathLike[str]) -> Path:
    pointer = detect_lfs_pointer(path)
    if pointer is not None:
        raise AssetNotMaterializedError(
            f"Git-LFS asset is not materialized: {pointer.path}"
        )
    return Path(path).expanduser().resolve(strict=False)


def _binary_face_count(path: Path, size: int) -> int | None:
    if size < _BINARY_HEADER_BYTES:
        return None
    with path.open("rb") as handle:
        header = handle.read(_BINARY_HEADER_BYTES)
    face_count = struct.unpack("<I", header[80:84])[0]
    if _BINARY_HEADER_BYTES + 50 * face_count == size:
        return face_count
    return None


def _validated_chunk(chunk: np.ndarray, path: Path) -> np.ndarray:
    if not np.isfinite(chunk).all():
        raise ValueError(f"nonfinite STL vertex coordinates in {path}")
    return chunk


def _iter_binary(path: Path, face_count: int, chunk_faces: int) -> Iterator[np.ndarray]:
    if face_count == 0:
        return
    faces = np.memmap(
        path, mode="r", offset=_BINARY_HEADER_BYTES, dtype=_BINARY_RECORD,
        shape=(face_count,),
    )
    for begin in range(0, face_count, chunk_faces):
        chunk = faces[begin:begin + chunk_faces]["vertices"].astype(np.float64)
        yield _validated_chunk(chunk, path)


def _iter_ascii(path: Path, chunk_faces: int) -> Iterator[np.ndarray]:
    pending: list[list[float]] = []
    complete: list[list[list[float]]] = []
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 4 and parts[0].lower() == "vertex":
                try:
                    pending.append([float(value) for value in parts[1:]])
                except ValueError as exc:
                    raise ValueError(
                        f"invalid ASCII STL vertex in {path}: {line.strip()}"
                    ) from exc
            elif parts and parts[0].lower() == "endfacet":
                if len(pending) != 3:
                    raise ValueError(
                        f"ASCII STL facet with {len(pending)} vertices in {path}"
                    )
                complete.append(pending)
                pending = []
                if len(complete) >= chunk_faces:
                    yield _validated_chunk(np.asarray(complete, dtype=np.float64), path)
                    complete = []
    if pending:
        raise ValueError(f"ASCII STL ends inside an open facet in {path}")
    if complete:
        yield _validated_chunk(np.asarray(complete, dtype=np.float64), path)


def read_stl_triangles(
    path: str | PathLike[str],
    *,
    chunk_faces: int = 100_000,
) -> Iterator[np.ndarray]:
    """Yield ``(n, 3, 3)`` float64 XYZ triangle chunks from an STL file.

    Binary encoding is detected exactly (``84 + 50 * face_count`` bytes);
    everything else is parsed as ASCII.  LFS pointers, missing paths, and
    nonfinite vertices are rejected.
    """

    if chunk_faces <= 0:
        raise ValueError("chunk_faces must be positive")
    asset = _materialized(path)
    face_count = _binary_face_count(asset, asset.stat().st_size)
    if face_count is not None:
        return _iter_binary(asset, face_count, chunk_faces)
    return _iter_ascii(asset, chunk_faces)


def stl_enclosed_volume(
    path: str | PathLike[str],
    *,
    chunk_faces: int = 200_000,
) -> float:
    """Exact enclosed volume of a watertight STL via the divergence theorem.

    The result is the absolute signed-tetrahedron sum, in cubic STL units.
    Open or self-intersecting meshes yield an approximation, not a guarantee.
    """

    total = 0.0
    for chunk in read_stl_triangles(path, chunk_faces=chunk_faces):
        v0, v1, v2 = chunk[:, 0], chunk[:, 1], chunk[:, 2]
        total += float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum())
    return abs(total) / 6.0


def subdivide_triangles(
    triangles: np.ndarray,
    max_edge: float,
    *,
    max_triangles: int = 50_000_000,
    max_rounds: int = 32,
) -> np.ndarray:
    """Uniformly split triangles until every edge is at most ``max_edge``.

    Each oversized triangle becomes four via edge midpoints, so the output
    covers the identical surface.  Deterministic; raises before exceeding
    ``max_triangles`` intermediate triangles.
    """

    if not (np.isfinite(max_edge) and max_edge > 0):
        raise ValueError("max_edge must be a positive finite number")
    current = np.asarray(triangles, dtype=np.float64)
    if current.ndim != 3 or current.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (n, 3, 3), got {current.shape}")
    if not np.isfinite(current).all():
        raise ValueError("triangles contain nonfinite coordinates")
    for _ in range(max_rounds):
        if current.shape[0] == 0:
            return current
        edges = np.stack([
            np.linalg.norm(current[:, 1] - current[:, 0], axis=1),
            np.linalg.norm(current[:, 2] - current[:, 1], axis=1),
            np.linalg.norm(current[:, 0] - current[:, 2], axis=1),
        ], axis=1)
        oversized = edges.max(axis=1) > max_edge
        if not oversized.any():
            return current
        keep = current[~oversized]
        split = current[oversized]
        mid01 = (split[:, 0] + split[:, 1]) / 2.0
        mid12 = (split[:, 1] + split[:, 2]) / 2.0
        mid20 = (split[:, 2] + split[:, 0]) / 2.0
        children = np.concatenate([
            np.stack([split[:, 0], mid01, mid20], axis=1),
            np.stack([mid01, split[:, 1], mid12], axis=1),
            np.stack([mid20, mid12, split[:, 2]], axis=1),
            np.stack([mid01, mid12, mid20], axis=1),
        ])
        if keep.shape[0] + children.shape[0] > max_triangles:
            raise ValueError(
                f"subdivision would exceed {max_triangles} triangles; "
                "raise max_triangles or coarsen max_edge"
            )
        current = np.concatenate([keep, children])
    raise ValueError(f"subdivision did not converge within {max_rounds} rounds")


def triangle_surface_points(triangles: np.ndarray) -> np.ndarray:
    """Return the vertices and centroids of ``(n, 3, 3)`` triangles as ``(m, 3)``."""

    tris = np.asarray(triangles, dtype=np.float64)
    if tris.ndim != 3 or tris.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (n, 3, 3), got {tris.shape}")
    if tris.shape[0] == 0:
        return np.empty((0, 3), dtype=np.float64)
    return np.concatenate([tris.reshape(-1, 3), tris.mean(axis=1)])
