"""Voxelize an STL surface into a ZYX boolean grid in a target frame.

The mesh is streamed in chunks, optionally transformed, subdivided until every
triangle edge fits within a fraction of the voxel pitch, and its vertices and
centroids are quantized into grid cells.  ``fill=True`` closes the marked
shell morphologically and fills its interior to obtain solid occupancy.
SciPy is imported lazily so that importing this module stays lightweight.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike

import numpy as np

from Components.coordinates import apply_transform

from tif2stl.stl_geometry import (
    read_stl_triangles,
    subdivide_triangles,
    triangle_surface_points,
)


@dataclass(frozen=True)
class VoxelizedSurface:
    """A voxelized STL: ZYX boolean grid plus its placement in the target frame."""

    grid: np.ndarray
    origin_xyz: tuple[float, float, float]
    pitch: float
    triangle_count: int
    surface_points: int
    points_outside: int
    filled: bool

    @property
    def occupied_voxels(self) -> int:
        return int(np.count_nonzero(self.grid))

    @property
    def outside_fraction(self) -> float:
        if self.surface_points == 0:
            return 0.0
        return self.points_outside / self.surface_points


def _fill_shell(shell: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    dilated = ndimage.binary_dilation(shell)
    solid = ndimage.binary_fill_holes(dilated)
    return ndimage.binary_erosion(solid) | shell


def voxelize_stl(
    path: str | PathLike[str],
    *,
    pitch: float,
    transform: np.ndarray | None = None,
    origin_xyz: tuple[float, float, float] | None = None,
    grid_shape_zyx: tuple[int, int, int] | None = None,
    padding_voxels: int = 2,
    fill: bool = True,
    max_edge_factor: float = 0.7,
    chunk_faces: int = 100_000,
    max_grid_voxels: int = 400_000_000,
) -> VoxelizedSurface:
    """Rasterize an STL into a boolean ZYX grid of cell size ``pitch``.

    ``transform`` (4x4, XYZ) maps STL coordinates into the target frame first;
    the grid then quantizes target coordinates as ``floor((p - origin) / pitch)``.
    When ``origin_xyz``/``grid_shape_zyx`` are omitted they are derived from the
    transformed mesh bounds plus ``padding_voxels``.  Points landing outside a
    caller-supplied grid are counted, not fatal — a scanned part may be cropped
    by the CT field of view.
    """

    if not (np.isfinite(pitch) and pitch > 0):
        raise ValueError("pitch must be a positive finite number")
    if not (np.isfinite(max_edge_factor) and 0 < max_edge_factor <= 1.0):
        raise ValueError("max_edge_factor must lie in (0, 1]")
    if padding_voxels < 0:
        raise ValueError("padding_voxels must be nonnegative")
    if (origin_xyz is None) != (grid_shape_zyx is None):
        raise ValueError("origin_xyz and grid_shape_zyx must be supplied together")

    max_edge = max_edge_factor * pitch

    if origin_xyz is None:
        lower = np.full(3, np.inf)
        upper = np.full(3, -np.inf)
        triangle_count = 0
        for chunk in read_stl_triangles(path, chunk_faces=chunk_faces):
            triangle_count += chunk.shape[0]
            vertices = chunk.reshape(-1, 3)
            if transform is not None:
                vertices = apply_transform(vertices, transform)
            lower = np.minimum(lower, vertices.min(axis=0))
            upper = np.maximum(upper, vertices.max(axis=0))
        if triangle_count == 0:
            raise ValueError(f"STL contains no triangles: {path}")
        origin = np.floor(lower / pitch) * pitch - padding_voxels * pitch
        shape_xyz = np.floor((upper - origin) / pitch).astype(np.int64) + 1 + padding_voxels
        grid_shape = (int(shape_xyz[2]), int(shape_xyz[1]), int(shape_xyz[0]))
    else:
        origin = np.asarray(origin_xyz, dtype=np.float64)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError("origin_xyz must contain three finite values")
        grid_shape = tuple(int(value) for value in grid_shape_zyx)
        if len(grid_shape) != 3 or any(value <= 0 for value in grid_shape):
            raise ValueError(f"grid_shape_zyx must be three positive ints, got {grid_shape_zyx}")

    voxel_total = int(np.prod(np.asarray(grid_shape, dtype=np.int64)))
    if voxel_total > max_grid_voxels:
        raise ValueError(
            f"grid of shape {grid_shape} holds {voxel_total} voxels, above the "
            f"max_grid_voxels budget of {max_grid_voxels}"
        )

    grid = np.zeros(grid_shape, dtype=bool)
    shape_xyz_array = np.asarray([grid_shape[2], grid_shape[1], grid_shape[0]])
    triangle_count = 0
    surface_points = 0
    points_outside = 0
    for chunk in read_stl_triangles(path, chunk_faces=chunk_faces):
        triangle_count += chunk.shape[0]
        if transform is not None:
            chunk = apply_transform(chunk.reshape(-1, 3), transform).reshape(-1, 3, 3)
        dense = subdivide_triangles(chunk, max_edge)
        points = triangle_surface_points(dense)
        surface_points += points.shape[0]
        indices = np.floor((points - origin) / pitch).astype(np.int64)
        inside = np.all((indices >= 0) & (indices < shape_xyz_array), axis=1)
        points_outside += int(np.count_nonzero(~inside))
        kept = indices[inside]
        grid[kept[:, 2], kept[:, 1], kept[:, 0]] = True
    if triangle_count == 0:
        raise ValueError(f"STL contains no triangles: {path}")

    if fill:
        grid = _fill_shell(grid)

    return VoxelizedSurface(
        grid=grid,
        origin_xyz=(float(origin[0]), float(origin[1]), float(origin[2])),
        pitch=float(pitch),
        triangle_count=triangle_count,
        surface_points=surface_points,
        points_outside=points_outside,
        filled=bool(fill),
    )
