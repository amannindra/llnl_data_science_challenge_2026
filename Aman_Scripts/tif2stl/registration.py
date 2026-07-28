"""Similarity registration between corresponding XYZ point sets.

The project's registered lattice JSON stores junction positions directly in CT
voxel coordinates, while the design JSON stores the same junction ids in
dimensionless lattice units.  Fitting design -> registered therefore recovers
the design-to-CT similarity transform (Umeyama closed form).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from Components.coordinates import apply_transform, homogeneous_matrix
from Components.lattice_graph import LatticeGraph


@dataclass(frozen=True)
class SimilarityFit:
    """A fitted ``target ~= scale * rotation @ source + translation`` transform."""

    matrix: np.ndarray
    rotation: np.ndarray
    scale: float
    translation: np.ndarray
    rms_error: float
    max_error: float
    point_count: int

    @property
    def rotation_angle_degrees(self) -> float:
        cosine = (float(np.trace(self.rotation)) - 1.0) / 2.0
        return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _validated_points(points: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"{name} must have shape (n, 3), got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains nonfinite coordinates")
    return array


def similarity_transform(
    source_xyz: np.ndarray,
    target_xyz: np.ndarray,
    *,
    with_scale: bool = True,
) -> SimilarityFit:
    """Least-squares similarity fit mapping ``source_xyz`` onto ``target_xyz``.

    Umeyama's closed-form solution with reflection correction.  Requires at
    least three non-degenerate (non-collinear) correspondences.
    """

    source = _validated_points(source_xyz, "source_xyz")
    target = _validated_points(target_xyz, "target_xyz")
    if source.shape[0] != target.shape[0]:
        raise ValueError(
            f"point counts differ: {source.shape[0]} source vs {target.shape[0]} target"
        )
    count = source.shape[0]
    if count < 3:
        raise ValueError(f"at least 3 correspondences are required, got {count}")

    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_centered = source - source_mean
    target_centered = target - target_mean
    covariance = target_centered.T @ source_centered / count
    source_variance = float((source_centered ** 2).sum()) / count
    if source_variance <= 0.0:
        raise ValueError("source points are coincident; similarity is undefined")

    left, singular_values, right_transposed = np.linalg.svd(covariance)
    if np.linalg.matrix_rank(covariance, tol=1e-12 * max(singular_values[0], 1.0)) < 2:
        raise ValueError("correspondences are degenerate (rank < 2); cannot fit rotation")
    correction = np.eye(3)
    if np.linalg.det(left @ right_transposed) < 0.0:
        correction[2, 2] = -1.0
    rotation = left @ correction @ right_transposed
    if with_scale:
        scale = float((singular_values * np.diag(correction)).sum() / source_variance)
        if scale <= 0.0:
            raise ValueError(f"fitted scale is non-positive ({scale}); inputs are inconsistent")
    else:
        scale = 1.0
    translation = target_mean - scale * rotation @ source_mean
    matrix = homogeneous_matrix(rotation=rotation, translation=translation, scale=scale)

    residuals = apply_transform(source, matrix) - target
    distances = np.linalg.norm(residuals, axis=1)
    return SimilarityFit(
        matrix=matrix,
        rotation=rotation,
        scale=scale,
        translation=np.asarray(translation, dtype=np.float64),
        rms_error=float(np.sqrt(np.mean(distances ** 2))),
        max_error=float(distances.max()),
        point_count=count,
    )


def paired_junction_positions(
    graph_a: LatticeGraph,
    graph_b: LatticeGraph,
) -> tuple[np.ndarray, np.ndarray]:
    """Positions of junctions sharing an id in both graphs, ordered by id.

    The project's design and registered JSONs carry identical id sequences, so
    this normally returns all 10,206 records; damaged files simply pair fewer.
    """

    positions_a = {junction.id: junction.position for junction in graph_a.junctions}
    positions_b = {junction.id: junction.position for junction in graph_b.junctions}
    shared_ids = sorted(positions_a.keys() & positions_b.keys())
    if len(shared_ids) < 3:
        raise ValueError(
            f"only {len(shared_ids)} junction ids are shared; at least 3 are required"
        )
    source = np.asarray([positions_a[jid] for jid in shared_ids], dtype=np.float64)
    target = np.asarray([positions_b[jid] for jid in shared_ids], dtype=np.float64)
    return source, target


def stl_to_design_matrix(
    *,
    mm_per_design_unit: float,
    stl_center_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
    design_center_xyz: tuple[float, float, float] = (9.0, 9.0, 9.0),
    rotation: np.ndarray | None = None,
) -> np.ndarray:
    """Map STL millimetres to design lattice units about the lattice centre.

    ``design = rotation @ ((stl - stl_center) / mm_per_design_unit) + design_center``.
    The 9x9x9 design lattice spans 0..18 units with its centre at (9, 9, 9);
    the shipped STLs are modelled around the origin.  ``rotation`` expresses the
    modelling-frame orientation difference (e.g. the STL's build plates sit on
    its Y axis while the scanned part's plates lie on the CT Z axis); physical
    part tilt lives in the design->CT registration instead.
    """

    if not (np.isfinite(mm_per_design_unit) and mm_per_design_unit > 0):
        raise ValueError("mm_per_design_unit must be a positive finite number")
    center = np.asarray(stl_center_xyz, dtype=np.float64)
    design_center = np.asarray(design_center_xyz, dtype=np.float64)
    if center.shape != (3,) or not np.isfinite(center).all():
        raise ValueError("stl_center_xyz must contain three finite values")
    if design_center.shape != (3,) or not np.isfinite(design_center).all():
        raise ValueError("design_center_xyz must contain three finite values")
    rotate = np.eye(3) if rotation is None else np.asarray(rotation, dtype=np.float64)
    if rotate.shape != (3, 3) or not np.isfinite(rotate).all():
        raise ValueError("rotation must be a finite 3x3 matrix")
    scale = 1.0 / mm_per_design_unit
    return homogeneous_matrix(
        rotation=rotate,
        translation=design_center - scale * (rotate @ center),
        scale=scale,
    )


def proper_cube_rotations() -> tuple[tuple[str, np.ndarray], ...]:
    """The 24 proper (det +1) signed axis permutations, identity first.

    Each name reads as the design-axis composition: ``+x+z-y`` means
    ``(design_x, design_y, design_z) = (+stl_x, +stl_z, -stl_y)``.  Used to
    resolve modelling-frame orientation between an STL and the lattice design
    when both are near-cubic and bounding boxes cannot disambiguate axes.
    """

    from itertools import permutations, product

    axes = "xyz"
    candidates: list[tuple[str, np.ndarray]] = []
    for permutation in permutations(range(3)):
        for signs in product((1.0, -1.0), repeat=3):
            matrix = np.zeros((3, 3), dtype=np.float64)
            for row, (column, sign) in enumerate(zip(permutation, signs)):
                matrix[row, column] = sign
            if np.linalg.det(matrix) < 0.0:
                continue
            name = "".join(
                f"{'+' if sign > 0 else '-'}{axes[column]}"
                for column, sign in zip(permutation, signs)
            )
            candidates.append((name, matrix))
    candidates.sort(key=lambda item: item[0] != "+x+y+z")
    return tuple(candidates)
