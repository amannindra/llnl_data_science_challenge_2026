"""Deterministic tube-mesh construction for viewing lattice graphs in 3D.

MeshLab cannot open the project's lattice JSON, so a viewable copy has to be
built as real surface geometry.  Every strut becomes a capped prism whose
cross-section is a regular polygon, which renders as a solid round strut once
MeshLab smooths the normals.

Positions here stay in whatever frame the caller supplies.  The registered
lattice JSONs are already expressed in CT native XYZ voxel units, so the
default radius in :mod:`Aman_Scripts.view_lattice_in_meshlab` is a voxel count.

Only the ``write_*`` functions touch the filesystem; mesh construction is
side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable, Sequence

import numpy as np


MESH_VERTEX_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)

_FACE_DTYPE = np.dtype([("n", "u1"), ("v0", "<i4"), ("v1", "<i4"), ("v2", "<i4")])

MINIMUM_RADIAL_SEGMENTS = 3


@dataclass(frozen=True)
class TubeMesh:
    """One triangulated strut-tube mesh and the parameters that produced it."""

    vertices: np.ndarray
    faces: np.ndarray
    strut_count: int
    radial_segments: int
    radius: float
    capped: bool

    @property
    def vertex_count(self) -> int:
        return int(len(self.vertices))

    @property
    def face_count(self) -> int:
        return int(len(self.faces))


@dataclass(frozen=True)
class ProjectLayer:
    """One file to list in a MeshLab ``.mlp`` project."""

    path: Path
    label: str


def _validate_color(color_rgb: Sequence[int]) -> tuple[int, int, int]:
    color = tuple(int(value) for value in color_rgb)
    if len(color) != 3 or any(value < 0 or value > 255 for value in color):
        raise ValueError("color_rgb must contain three integers in [0, 255]")
    return color


def _perpendicular_basis(directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return two deterministic unit vectors spanning each direction's normal plane.

    The reference axis is chosen per direction so the cross product is never
    taken against a nearly parallel vector, which would produce an unstable or
    zero-length basis for axis-aligned struts.
    """

    reference = np.zeros_like(directions)
    use_x = np.abs(directions[:, 0]) < 0.9
    reference[use_x, 0] = 1.0
    reference[~use_x, 1] = 1.0
    first = np.cross(directions, reference)
    first /= np.linalg.norm(first, axis=1, keepdims=True)
    second = np.cross(directions, first)
    return first, second


def strut_tube_mesh(
    node_positions: np.ndarray,
    edges: np.ndarray,
    *,
    radius: float,
    radial_segments: int = 8,
    color_rgb: Sequence[int] = (170, 176, 186),
    capped: bool = True,
    minimum_length: float = 1e-9,
) -> TubeMesh:
    """Build one capped polygonal tube per edge as a single triangle mesh.

    ``node_positions`` is an ``(N, 3)`` XYZ array and ``edges`` an ``(M, 2)``
    array of endpoint indices.  Edges shorter than ``minimum_length`` are
    dropped rather than emitted as degenerate geometry, so the returned
    ``strut_count`` may be smaller than ``len(edges)``.
    """

    positions = np.asarray(node_positions, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"node_positions must have shape (N, 3), got {positions.shape}")
    if not np.isfinite(positions).all():
        raise ValueError("node_positions must be finite")

    index_pairs = np.asarray(edges)
    if index_pairs.size == 0:
        index_pairs = np.empty((0, 2), dtype=np.int64)
    if index_pairs.ndim != 2 or index_pairs.shape[1] != 2:
        raise ValueError(f"edges must have shape (M, 2), got {index_pairs.shape}")
    if not np.issubdtype(index_pairs.dtype, np.integer):
        raise ValueError("edges must contain integer node indices")
    if len(index_pairs) and (
        index_pairs.min() < 0 or index_pairs.max() >= len(positions)
    ):
        raise ValueError("edges reference node indices outside node_positions")

    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius must be finite and positive")
    segments = int(radial_segments)
    if segments != radial_segments or segments < MINIMUM_RADIAL_SEGMENTS:
        raise ValueError(f"radial_segments must be an integer >= {MINIMUM_RADIAL_SEGMENTS}")
    minimum_length = float(minimum_length)
    if not math.isfinite(minimum_length) or minimum_length <= 0:
        raise ValueError("minimum_length must be finite and positive")
    color = _validate_color(color_rgb)

    start = positions[index_pairs[:, 0]]
    end = positions[index_pairs[:, 1]]
    axis = end - start
    lengths = np.linalg.norm(axis, axis=1)
    keep = lengths >= minimum_length
    start, end, axis, lengths = start[keep], end[keep], axis[keep], lengths[keep]
    strut_count = int(len(lengths))

    ring_vertices = 2 * segments
    per_strut_vertices = ring_vertices + (2 if capped else 0)
    per_strut_faces = 2 * segments + (2 * segments if capped else 0)
    vertices = np.empty(strut_count * per_strut_vertices, dtype=MESH_VERTEX_DTYPE)
    faces = np.empty((strut_count * per_strut_faces, 3), dtype=np.int32)
    if strut_count == 0:
        return TubeMesh(vertices, faces, 0, segments, radius, bool(capped))

    direction = axis / lengths[:, None]
    first, second = _perpendicular_basis(direction)
    angles = 2.0 * math.pi * np.arange(segments) / segments
    # (strut, segment, xyz) offsets around each strut axis.
    offsets = (
        np.cos(angles)[None, :, None] * first[:, None, :]
        + np.sin(angles)[None, :, None] * second[:, None, :]
    ) * radius

    points = np.empty((strut_count, per_strut_vertices, 3), dtype=np.float64)
    points[:, :segments] = start[:, None, :] + offsets
    points[:, segments:ring_vertices] = end[:, None, :] + offsets
    if capped:
        points[:, ring_vertices] = start
        points[:, ring_vertices + 1] = end

    flat = points.reshape(-1, 3)
    vertices["x"] = flat[:, 0]
    vertices["y"] = flat[:, 1]
    vertices["z"] = flat[:, 2]
    vertices["red"] = color[0]
    vertices["green"] = color[1]
    vertices["blue"] = color[2]

    ring = np.arange(segments)
    following = (ring + 1) % segments
    base = (np.arange(strut_count) * per_strut_vertices)[:, None]
    lower, lower_next = base + ring, base + following
    upper, upper_next = base + segments + ring, base + segments + following

    # Outward-facing winding: verified against a +Z strut whose first ring
    # vertex sits at +X, so MeshLab shades the tubes without flipped normals.
    side = np.concatenate(
        [
            np.stack([lower, upper_next, upper], axis=-1),
            np.stack([lower, lower_next, upper_next], axis=-1),
        ],
        axis=1,
    )
    if capped:
        start_center = base + ring_vertices
        end_center = base + ring_vertices + 1
        caps = np.concatenate(
            [
                np.stack(
                    [np.broadcast_to(start_center, lower.shape), lower_next, lower], axis=-1
                ),
                np.stack(
                    [np.broadcast_to(end_center, upper.shape), upper, upper_next], axis=-1
                ),
            ],
            axis=1,
        )
        strut_faces = np.concatenate([side, caps], axis=1)
    else:
        strut_faces = side
    faces[:] = strut_faces.reshape(-1, 3)
    return TubeMesh(vertices, faces, strut_count, segments, radius, bool(capped))


def _atomic_write(destination: Path, chunks: Iterable[bytes]) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            for chunk in chunks:
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def _ply_header(
    vertex_count: int, face_count: int | None, comments: Iterable[str]
) -> bytes:
    sanitized = [str(value).replace("\n", " ").replace("\r", " ") for value in comments]
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        "comment generated by Aman_Scripts/Components/lattice_mesh.py",
        *(f"comment {value}" for value in sanitized),
        f"element vertex {vertex_count}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
    ]
    if face_count is not None:
        lines.append(f"element face {face_count}")
        lines.append("property list uchar int vertex_indices")
    lines += ["end_header", ""]
    return "\n".join(lines).encode("ascii")


def colored_vertices(
    positions: np.ndarray, *, color_rgb: Sequence[int]
) -> np.ndarray:
    """Pack an ``(N, 3)`` XYZ array into a uniformly colored PLY vertex array."""

    array = np.asarray(positions, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"positions must have shape (N, 3), got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("positions must be finite")
    color = _validate_color(color_rgb)
    vertices = np.empty(len(array), dtype=MESH_VERTEX_DTYPE)
    vertices["x"], vertices["y"], vertices["z"] = array[:, 0], array[:, 1], array[:, 2]
    vertices["red"], vertices["green"], vertices["blue"] = color
    return vertices


def write_points_ply(
    path: str | Path,
    vertices: np.ndarray,
    *,
    comments: Iterable[str] = (),
) -> Path:
    """Atomically write a binary little-endian RGB point-cloud PLY."""

    array = np.asarray(vertices)
    if array.dtype != MESH_VERTEX_DTYPE or array.ndim != 1:
        raise ValueError("vertices must be a one-dimensional MESH_VERTEX_DTYPE array")
    return _atomic_write(
        Path(path).expanduser().resolve(),
        (
            _ply_header(len(array), None, comments),
            np.ascontiguousarray(array).tobytes(),
        ),
    )


def write_mesh_ply(
    path: str | Path,
    mesh: TubeMesh,
    *,
    comments: Iterable[str] = (),
) -> Path:
    """Atomically write a binary little-endian RGB triangle-mesh PLY."""

    if not isinstance(mesh, TubeMesh):
        raise TypeError("mesh must be a TubeMesh")
    if mesh.vertices.dtype != MESH_VERTEX_DTYPE or mesh.vertices.ndim != 1:
        raise ValueError("mesh.vertices must be a one-dimensional MESH_VERTEX_DTYPE array")
    if mesh.faces.ndim != 2 or mesh.faces.shape[1] != 3:
        raise ValueError("mesh.faces must have shape (M, 3)")

    destination = Path(path).expanduser().resolve()
    header = _ply_header(mesh.vertex_count, mesh.face_count, comments)
    face_records = np.empty(mesh.face_count, dtype=_FACE_DTYPE)
    face_records["n"] = 3
    face_records["v0"] = mesh.faces[:, 0]
    face_records["v1"] = mesh.faces[:, 1]
    face_records["v2"] = mesh.faces[:, 2]
    return _atomic_write(
        destination,
        (
            header,
            np.ascontiguousarray(mesh.vertices).tobytes(),
            face_records.tobytes(),
        ),
    )


def write_meshlab_project(path: str | Path, layers: Sequence[ProjectLayer]) -> Path:
    """Write a MeshLab ``.mlp`` project referencing sibling geometry files.

    MeshLab resolves ``filename`` relative to the project, so every layer must
    already sit in the project's own directory.

    A ``.mlp`` must be opened from MeshLab's *File -> Open Project* menu.  The
    desktop file association routes every path through the mesh importer, which
    only knows mesh extensions and reports a project file as unsupported.
    """

    destination = Path(path).expanduser().resolve()
    if not layers:
        raise ValueError("at least one layer is required")
    names: list[str] = []
    for layer in layers:
        resolved = Path(layer.path).expanduser().resolve()
        if resolved.parent != destination.parent:
            raise ValueError(
                f"layer {resolved} must live beside the project file {destination}"
            )
        names.append(resolved.name)

    lines = ["<!DOCTYPE MeshLabDocument>", "<MeshLabProject>", " <MeshGroup>"]
    for layer, name in zip(layers, names):
        label = str(layer.label).replace('"', "'")
        lines.append(f'  <MLMesh label="{label}" filename="{name}" visible="1">')
        lines.append("   <MLMatrix44>")
        lines.append("1 0 0 0 ")
        lines.append("0 1 0 0 ")
        lines.append("0 0 1 0 ")
        lines.append("0 0 0 1 ")
        lines.append("</MLMatrix44>")
        lines.append("  </MLMesh>")
    lines += [" </MeshGroup>", " <RasterGroup/>", "</MeshLabProject>", ""]
    return _atomic_write(destination, ("\n".join(lines).encode("utf-8"),))
