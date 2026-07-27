"""Explicit coordinate-order conversions and homogeneous XYZ transforms."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray


def _points_with_three_coordinates(points: ArrayLike, *, name: str) -> NDArray[np.generic]:
    array = np.asarray(points)
    if array.ndim == 0 or array.shape[-1] != 3:
        raise ValueError(f"{name} must have shape (..., 3); received {array.shape}")
    return array


def xyz_to_zyx(points_xyz: ArrayLike) -> NDArray[np.generic]:
    """Convert geometry coordinates ``(..., x, y, z)`` to array order ZYX."""

    points = _points_with_three_coordinates(points_xyz, name="points_xyz")
    return points[..., ::-1].copy()


def zyx_to_xyz(indices_zyx: ArrayLike) -> NDArray[np.generic]:
    """Convert NumPy indices ``(..., z, y, x)`` to geometry order XYZ."""

    indices = _points_with_three_coordinates(indices_zyx, name="indices_zyx")
    return indices[..., ::-1].copy()


def rotation_matrix_xyz(
    angles_xyz: Sequence[float],
    *,
    degrees: bool = False,
) -> NDArray[np.float64]:
    """Return ``Rz @ Ry @ Rx`` for fixed-axis X, Y, then Z rotations."""

    angles = np.asarray(angles_xyz, dtype=np.float64)
    if angles.shape != (3,) or not np.isfinite(angles).all():
        raise ValueError("angles_xyz must contain three finite values")
    if degrees:
        angles = np.deg2rad(angles)
    x_angle, y_angle, z_angle = angles
    cx, cy, cz = np.cos(angles)
    sx, sy, sz = np.sin(angles)
    rotate_x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    rotate_y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    rotate_z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    return rotate_z @ rotate_y @ rotate_x


def homogeneous_matrix(
    *,
    rotation: ArrayLike | None = None,
    translation: ArrayLike | None = None,
    scale: float | Sequence[float] = 1.0,
) -> NDArray[np.float64]:
    """Build a 4x4 transform for XYZ column vectors.

    For a three-value scale, scaling occurs along the local axes before the
    rotation: ``linear = rotation @ diag(scale)``.  Translation is then added.
    """

    rotate = np.eye(3) if rotation is None else np.asarray(rotation, dtype=np.float64)
    if rotate.shape != (3, 3) or not np.isfinite(rotate).all():
        raise ValueError("rotation must be a finite 3x3 matrix")

    scales = np.asarray(scale, dtype=np.float64)
    if scales.ndim == 0:
        scales = np.repeat(scales, 3)
    if scales.shape != (3,) or not np.isfinite(scales).all() or np.any(scales == 0):
        raise ValueError("scale must be one finite nonzero value or three such values")

    offset = np.zeros(3) if translation is None else np.asarray(translation, dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise ValueError("translation must contain three finite values")

    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotate @ np.diag(scales)
    matrix[:3, 3] = offset
    return matrix


def _validated_matrix(matrix: ArrayLike) -> NDArray[np.float64]:
    transform = np.asarray(matrix, dtype=np.float64)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError("transform must be a finite 4x4 matrix")
    return transform


def apply_transform(points_xyz: ArrayLike, matrix: ArrayLike) -> NDArray[np.float64]:
    """Apply a homogeneous transform to one or many XYZ points."""

    points = _points_with_three_coordinates(points_xyz, name="points_xyz").astype(
        np.float64, copy=False
    )
    transform = _validated_matrix(matrix)
    flat = points.reshape(-1, 3)
    ones = np.ones((len(flat), 1), dtype=np.float64)
    projected = np.concatenate((flat, ones), axis=1) @ transform.T
    weights = projected[:, 3]
    if np.any(np.isclose(weights, 0.0)):
        raise ValueError("transform maps at least one point to zero homogeneous weight")
    result = projected[:, :3] / weights[:, None]
    return result.reshape(points.shape)


def invert_transform(matrix: ArrayLike) -> NDArray[np.float64]:
    """Return the inverse of a finite, nonsingular homogeneous transform."""

    return np.linalg.inv(_validated_matrix(matrix))


def compose_transforms(*matrices: ArrayLike) -> NDArray[np.float64]:
    """Compose transforms in the order they are applied to points.

    ``compose_transforms(first, second)`` yields a matrix equivalent to applying
    ``first`` and then ``second`` with :func:`apply_transform`.
    """

    result = np.eye(4, dtype=np.float64)
    for matrix in matrices:
        result = _validated_matrix(matrix) @ result
    return result
