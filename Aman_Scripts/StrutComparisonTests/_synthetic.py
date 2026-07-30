"""Small deterministic synthetic assets used by the strut comparison tests."""

from __future__ import annotations

from pathlib import Path
import struct
from typing import Iterable

import numpy as np


def segment_geometry(
    shape_zyx: tuple[int, int, int] = (41, 41, 41),
    start_xyz: tuple[float, float, float] = (6.0, 20.0, 20.0),
    end_xyz: tuple[float, float, float] = (34.0, 20.0, 20.0),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return voxel XYZ positions, segment fraction and distance to segment."""

    z, y, x = np.indices(shape_zyx, dtype=np.float64)
    xyz = np.stack((x, y, z), axis=-1)
    start = np.asarray(start_xyz, dtype=np.float64)
    end = np.asarray(end_xyz, dtype=np.float64)
    direction = end - start
    length_squared = float(direction @ direction)
    if length_squared == 0.0:
        raise ValueError("synthetic segment endpoints must differ")
    raw_fraction = np.einsum("...i,i->...", xyz - start, direction) / length_squared
    fraction = np.clip(raw_fraction, 0.0, 1.0)
    closest = start + fraction[..., None] * direction
    distance = np.linalg.norm(xyz - closest, axis=-1)
    return xyz, raw_fraction, distance


def cylinder_volume(
    *,
    shape_zyx: tuple[int, int, int] = (41, 41, 41),
    start_xyz: tuple[float, float, float] = (6.0, 20.0, 20.0),
    end_xyz: tuple[float, float, float] = (34.0, 20.0, 20.0),
    radius: float = 2.0,
    value: int = 200,
    background: int = 0,
    removed_fraction_ranges: Iterable[tuple[float, float]] = (),
    dtype: np.dtype | type = np.uint16,
) -> np.ndarray:
    """Create a bright finite cylinder, optionally deleting axial ranges."""

    _, fraction, distance = segment_geometry(shape_zyx, start_xyz, end_xyz)
    material = (fraction >= 0.0) & (fraction <= 1.0) & (distance <= radius)
    for lower, upper in removed_fraction_ranges:
        material &= ~((fraction >= float(lower)) & (fraction <= float(upper)))
    volume = np.full(shape_zyx, background, dtype=dtype)
    volume[material] = value
    return volume


def add_endpoint_blobs(
    volume: np.ndarray,
    *,
    endpoints_xyz: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (6.0, 20.0, 20.0),
        (34.0, 20.0, 20.0),
    ),
    radius: float = 4.0,
    value: int = 200,
) -> np.ndarray:
    """Return a copy with spherical junction-like blobs at both endpoints."""

    z, y, x = np.indices(volume.shape, dtype=np.float64)
    xyz = np.stack((x, y, z), axis=-1)
    result = volume.copy()
    for endpoint in endpoints_xyz:
        distances = np.linalg.norm(xyz - np.asarray(endpoint), axis=-1)
        result[distances <= radius] = value
    return result


def add_speckle_noise(
    volume: np.ndarray,
    *,
    count: int,
    value: int = 200,
    seed: int = 12345,
) -> np.ndarray:
    """Return a copy with a deterministic number of bright random voxels."""

    result = volume.copy()
    generator = np.random.default_rng(seed)
    flat = generator.choice(result.size, size=count, replace=False)
    result.reshape(-1)[flat] = value
    return result


def write_binary_stl(path: Path, triangles_xyz: np.ndarray) -> Path:
    """Write a minimal binary STL fixture without external mesh dependencies."""

    triangles = np.asarray(triangles_xyz, dtype=np.float32)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise ValueError("triangles_xyz must have shape (n, 3, 3)")
    header = b"strut-comparison-test".ljust(80, b"\0")
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(triangles)))
        for triangle in triangles:
            handle.write(np.zeros(3, dtype="<f4").tobytes())
            handle.write(triangle.astype("<f4", copy=False).tobytes())
            handle.write(struct.pack("<H", 0))
    return path


def radial_surface_triangles(
    *,
    x_positions: Iterable[float] = (8.0, 14.0, 20.0, 26.0, 32.0),
    center_yz: tuple[float, float] = (20.0, 20.0),
    radius: float = 2.0,
) -> np.ndarray:
    """Create tiny tangent triangles along a straight cylinder-like surface."""

    y, z = center_yz
    triangles = []
    for x in x_positions:
        triangles.append(
            [[x - 0.25, y + radius, z - 0.25],
             [x + 0.25, y + radius, z - 0.25],
             [x, y + radius, z + 0.25]]
        )
    return np.asarray(triangles, dtype=np.float64)


def cylinder_surface_points(
    *,
    start_xyz: tuple[float, float, float] = (6.0, 20.0, 20.0),
    end_xyz: tuple[float, float, float] = (34.0, 20.0, 20.0),
    radius: float = 2.0,
    axial_step: float = 0.5,
    radial_samples: int = 16,
) -> np.ndarray:
    """Sample a deterministic cylindrical surface around an arbitrary segment."""

    start = np.asarray(start_xyz, dtype=np.float64)
    end = np.asarray(end_xyz, dtype=np.float64)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length == 0.0:
        raise ValueError("surface endpoints must differ")
    unit = direction / length
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(reference @ unit)) > 0.8:
        reference = np.array([0.0, 1.0, 0.0])
    radial0 = np.cross(unit, reference)
    radial0 /= np.linalg.norm(radial0)
    radial1 = np.cross(unit, radial0)
    fractions = np.linspace(0.0, 1.0, max(2, int(np.ceil(length / axial_step)) + 1))
    angles = np.linspace(0.0, 2.0 * np.pi, radial_samples, endpoint=False)
    centers = start + fractions[:, None] * direction
    ring = (
        np.cos(angles)[:, None] * radial0
        + np.sin(angles)[:, None] * radial1
    ) * radius
    return (centers[:, None, :] + ring[None, :, :]).reshape(-1, 3)
