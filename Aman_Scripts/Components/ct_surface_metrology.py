"""Memory-bounded sub-voxel CT surface sampling and rigid refinement.

The registered JSON supplies a useful initial frame, but it is not independent
evidence that CAD surfaces coincide with CT material.  This module samples real
STL surface area, finds local ISO-50 intensity crossings in the native TIFF,
and estimates only a small rigid correction.  It never creates a full-volume
STL mask or CT surface mesh.
"""

from __future__ import annotations

import math
from os import PathLike
from typing import Any, Sequence

import numpy as np

from .coordinates import apply_transform
from tif2stl.stl_geometry import read_stl_triangles


def _points_xyz(values: np.ndarray | Sequence[Sequence[float]], name: str) -> np.ndarray:
    points = np.asarray(values, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError(f"{name} must have finite shape (n, 3)")
    return points


def _unit_vectors(values: np.ndarray | Sequence[Sequence[float]], name: str) -> np.ndarray:
    vectors = _points_xyz(values, name)
    lengths = np.linalg.norm(vectors, axis=1)
    if np.any(lengths <= np.finfo(np.float64).eps):
        raise ValueError(f"{name} contains a zero vector")
    return vectors / lengths[:, None]


def _finite_matrix4(matrix: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    result = np.asarray(matrix, dtype=np.float64)
    if result.shape != (4, 4) or not np.isfinite(result).all():
        raise ValueError("transform must be a finite 4x4 matrix")
    if not np.allclose(result[3], (0.0, 0.0, 0.0, 1.0), atol=1e-12, rtol=0.0):
        raise ValueError("transform must be affine")
    return result


def trilinear_sample(
    volume_zyx: np.ndarray,
    points_xyz: np.ndarray | Sequence[Sequence[float]],
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a ZYX volume at floating XYZ points without copying the volume."""

    volume = np.asarray(volume_zyx)
    if volume.ndim != 3 or volume.dtype.kind not in "uif":
        raise ValueError("volume_zyx must be a numeric 3D array")
    points = _points_xyz(points_xyz, "points_xyz")
    values = np.full(len(points), np.nan, dtype=np.float64)
    if not len(points):
        return values, np.zeros(0, dtype=bool)
    lower = np.floor(points).astype(np.int64)
    shape_xyz = np.asarray(volume.shape[::-1], dtype=np.int64)
    valid = np.all(lower >= 0, axis=1) & np.all(lower + 1 < shape_xyz, axis=1)
    if not np.any(valid):
        return values, valid
    selected = points[valid]
    base = lower[valid]
    fraction = selected - base
    x0, y0, z0 = base[:, 0], base[:, 1], base[:, 2]
    fx, fy, fz = fraction[:, 0], fraction[:, 1], fraction[:, 2]
    sampled = np.zeros(len(selected), dtype=np.float64)
    for dz in (0, 1):
        wz = (1.0 - fz) if dz == 0 else fz
        for dy in (0, 1):
            wy = (1.0 - fy) if dy == 0 else fy
            for dx in (0, 1):
                wx = (1.0 - fx) if dx == 0 else fx
                sampled += (
                    wz * wy * wx
                    * np.asarray(volume[z0 + dz, y0 + dy, x0 + dx], dtype=np.float64)
                )
    values[valid] = sampled
    return values, valid


def local_iso50_crossings(
    volume_zyx: np.ndarray,
    surface_points_xyz: np.ndarray,
    surface_normals_xyz: np.ndarray,
    *,
    search_distance_voxels: float = 3.0,
    step_voxels: float = 0.5,
    minimum_end_contrast: float = 1000.0,
) -> dict[str, Any]:
    """Find the nearest local half-contrast crossing along each surface normal.

    The two profile ends estimate the local air/material plateaus.  Their
    midpoint is the local ISO-50 level, so beam-hardening changes in absolute
    intensity do not require a different global threshold.  Normal direction
    may be reversed; either monotonic crossing direction is accepted.
    """

    points = _points_xyz(surface_points_xyz, "surface_points_xyz")
    normals = _unit_vectors(surface_normals_xyz, "surface_normals_xyz")
    if points.shape != normals.shape:
        raise ValueError("surface points and normals must share shape")
    if not np.isfinite(search_distance_voxels) or search_distance_voxels <= 0.0:
        raise ValueError("search_distance_voxels must be positive")
    if not np.isfinite(step_voxels) or step_voxels <= 0.0:
        raise ValueError("step_voxels must be positive")
    if step_voxels > search_distance_voxels:
        raise ValueError("step_voxels cannot exceed search distance")
    if not np.isfinite(minimum_end_contrast) or minimum_end_contrast < 0.0:
        raise ValueError("minimum_end_contrast must be nonnegative")
    count_each_side = int(math.ceil(search_distance_voxels / step_voxels))
    offsets = np.linspace(
        -search_distance_voxels,
        search_distance_voxels,
        2 * count_each_side + 1,
        dtype=np.float64,
    )
    query = points[:, None, :] + offsets[None, :, None] * normals[:, None, :]
    sampled, in_bounds = trilinear_sample(volume_zyx, query.reshape(-1, 3))
    profiles = sampled.reshape(len(points), len(offsets))
    profile_bounds = in_bounds.reshape(len(points), len(offsets)).all(axis=1)
    crossing = np.full(len(points), np.nan, dtype=np.float64)
    local_level = np.full(len(points), np.nan, dtype=np.float64)
    end_contrast = np.full(len(points), np.nan, dtype=np.float64)
    valid = np.zeros(len(points), dtype=bool)
    for index, profile in enumerate(profiles):
        if not profile_bounds[index] or not np.isfinite(profile).all():
            continue
        end_width = min(3, max(1, len(offsets) // 4))
        first_level = float(np.median(profile[:end_width]))
        last_level = float(np.median(profile[-end_width:]))
        contrast = abs(first_level - last_level)
        level = 0.5 * (first_level + last_level)
        local_level[index] = level
        end_contrast[index] = contrast
        if contrast < minimum_end_contrast:
            continue
        centered = profile - level
        candidates = np.flatnonzero(
            (centered[:-1] == 0.0)
            | (centered[1:] == 0.0)
            | (centered[:-1] * centered[1:] < 0.0)
        )
        if not candidates.size:
            continue
        estimates = []
        for candidate in candidates:
            first_value = centered[candidate]
            second_value = centered[candidate + 1]
            denominator = second_value - first_value
            fraction = 0.0 if denominator == 0.0 else -first_value / denominator
            estimates.append(offsets[candidate] + fraction * (
                offsets[candidate + 1] - offsets[candidate]
            ))
        chosen = float(min(estimates, key=lambda item: (abs(item), item)))
        crossing[index] = chosen
        valid[index] = True
    return {
        "offsets_voxels": offsets,
        "profiles": profiles,
        "crossing_offset_voxels": crossing,
        "local_iso50_level": local_level,
        "end_contrast": end_contrast,
        "valid": valid,
        "in_bounds": profile_bounds,
    }


def _triangle_area(triangles: np.ndarray) -> np.ndarray:
    return 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )


def sample_stl_surface_by_area(
    path: str | PathLike[str],
    transform: np.ndarray,
    *,
    sample_count: int = 30_000,
    chunk_faces: int = 100_000,
) -> dict[str, np.ndarray | int | float]:
    """Return deterministic area-uniform STL points and normals in CT XYZ."""

    matrix = _finite_matrix4(transform)
    if not isinstance(sample_count, int) or sample_count < 100:
        raise ValueError("sample_count must be an integer >= 100")
    if not isinstance(chunk_faces, int) or chunk_faces < 1:
        raise ValueError("chunk_faces must be positive")
    total_area = 0.0
    triangle_count = 0
    for triangles in read_stl_triangles(path, chunk_faces=chunk_faces):
        areas = _triangle_area(triangles)
        total_area += float(areas.sum())
        triangle_count += int(len(triangles))
    if not np.isfinite(total_area) or total_area <= 0.0 or triangle_count == 0:
        raise ValueError("STL has no finite positive-area surface")
    targets = (np.arange(sample_count, dtype=np.float64) + 0.5) * total_area / sample_count
    points = np.empty((sample_count, 3), dtype=np.float64)
    normals = np.empty_like(points)
    target_index = 0
    accumulated = 0.0
    golden = (math.sqrt(5.0) - 1.0) / 2.0
    silver = math.sqrt(2.0) - 1.0
    for triangles in read_stl_triangles(path, chunk_faces=chunk_faces):
        areas = _triangle_area(triangles)
        cumulative = accumulated + np.cumsum(areas)
        stop = int(np.searchsorted(targets, cumulative[-1], side="right"))
        if stop > target_index:
            local_targets = targets[target_index:stop]
            indices = np.searchsorted(cumulative, local_targets, side="left")
            selected = triangles[indices]
            sequence = np.arange(target_index, stop, dtype=np.float64) + 0.5
            first = np.mod(sequence * golden, 1.0)
            second = np.mod(sequence * silver, 1.0)
            root = np.sqrt(first)
            weights = np.stack((1.0 - root, root * (1.0 - second), root * second), axis=1)
            points[target_index:stop] = np.einsum("ni,nij->nj", weights, selected)
            raw_normals = np.cross(
                selected[:, 1] - selected[:, 0], selected[:, 2] - selected[:, 0]
            )
            normals[target_index:stop] = _unit_vectors(raw_normals, "triangle normals")
            target_index = stop
        accumulated = float(cumulative[-1])
    if target_index != sample_count:
        raise RuntimeError(f"sampled {target_index} of {sample_count} requested STL points")
    transformed_points = apply_transform(points, matrix)
    normal_matrix = np.linalg.inv(matrix[:3, :3])
    transformed_normals = _unit_vectors(normals @ normal_matrix, "transformed normals")
    return {
        "points_xyz": transformed_points,
        "normals_xyz": transformed_normals,
        "sample_count": sample_count,
        "triangle_count": triangle_count,
        "surface_area_stl_units_squared": total_area,
    }


def rigid_correction_matrix(
    rotation_vector_radians: Sequence[float],
    translation_xyz_voxels: Sequence[float],
    pivot_xyz: Sequence[float],
) -> np.ndarray:
    """Build an affine correction rotating around ``pivot_xyz`` then translating."""

    from scipy.spatial.transform import Rotation

    rotation_vector = np.asarray(rotation_vector_radians, dtype=np.float64)
    translation = np.asarray(translation_xyz_voxels, dtype=np.float64)
    pivot = np.asarray(pivot_xyz, dtype=np.float64)
    if rotation_vector.shape != (3,) or not np.isfinite(rotation_vector).all():
        raise ValueError("rotation vector must contain three finite radians")
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ValueError("translation must contain three finite voxel values")
    if pivot.shape != (3,) or not np.isfinite(pivot).all():
        raise ValueError("pivot must contain three finite XYZ values")
    rotation = Rotation.from_rotvec(rotation_vector).as_matrix()
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = pivot + translation - rotation @ pivot
    return matrix


def _apply_rigid_to_normals(normals_xyz: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return _unit_vectors(normals_xyz @ matrix[:3, :3].T, "corrected normals")


def _crossing_summary(crossings: dict[str, Any]) -> dict[str, Any]:
    valid = np.asarray(crossings["valid"], dtype=bool)
    values = np.asarray(crossings["crossing_offset_voxels"], dtype=np.float64)[valid]
    if not len(values):
        return {
            "sample_count": len(valid), "valid_count": 0, "valid_fraction": 0.0,
            "median_signed_offset_voxels": None, "median_absolute_offset_voxels": None,
            "p90_absolute_offset_voxels": None, "robust_sigma_voxels": None,
        }
    median = float(np.median(values))
    absolute = np.abs(values)
    robust_sigma = float(1.4826 * np.median(np.abs(values - median)))
    return {
        "sample_count": len(valid),
        "valid_count": int(len(values)),
        "valid_fraction": float(np.mean(valid)),
        "median_signed_offset_voxels": median,
        "median_absolute_offset_voxels": float(np.median(absolute)),
        "p90_absolute_offset_voxels": float(np.quantile(absolute, 0.90)),
        "robust_sigma_voxels": robust_sigma,
    }


def _common_crossing_comparison(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    baseline_valid = np.asarray(baseline["valid"], dtype=bool)
    candidate_valid = np.asarray(candidate["valid"], dtype=bool)
    if baseline_valid.shape != candidate_valid.shape:
        raise ValueError("crossing populations differ")
    common = baseline_valid & candidate_valid
    baseline_values = np.asarray(baseline["crossing_offset_voxels"], dtype=np.float64)
    candidate_values = np.asarray(candidate["crossing_offset_voxels"], dtype=np.float64)
    if not np.any(common):
        return {
            "common_valid_count": 0,
            "common_fraction_of_baseline_valid": 0.0,
            "before_median_absolute_voxels": None,
            "after_median_absolute_voxels": None,
            "before_p90_absolute_voxels": None,
            "after_p90_absolute_voxels": None,
        }
    before = np.abs(baseline_values[common])
    after = np.abs(candidate_values[common])
    return {
        "common_valid_count": int(np.count_nonzero(common)),
        "common_fraction_of_baseline_valid": float(
            np.count_nonzero(common) / max(1, np.count_nonzero(baseline_valid))
        ),
        "before_median_absolute_voxels": float(np.median(before)),
        "after_median_absolute_voxels": float(np.median(after)),
        "before_p90_absolute_voxels": float(np.quantile(before, 0.90)),
        "after_p90_absolute_voxels": float(np.quantile(after, 0.90)),
    }


def refine_rigid_registration(
    volume_zyx: np.ndarray,
    surface_points_xyz: np.ndarray,
    surface_normals_xyz: np.ndarray,
    *,
    maximum_iterations: int = 6,
    search_distance_voxels: float = 3.0,
    step_voxels: float = 0.5,
    minimum_end_contrast: float = 1000.0,
    maximum_translation_voxels: float = 2.0,
    maximum_rotation_degrees: float = 0.5,
    minimum_valid_fraction: float = 0.20,
) -> dict[str, Any]:
    """Refine a small rigid transform with separate selection and audit sets."""

    points = _points_xyz(surface_points_xyz, "surface_points_xyz")
    normals = _unit_vectors(surface_normals_xyz, "surface_normals_xyz")
    if points.shape != normals.shape or len(points) < 100:
        raise ValueError("registration requires at least 100 paired surface points/normals")
    if not isinstance(maximum_iterations, int) or maximum_iterations < 1:
        raise ValueError("maximum_iterations must be positive")
    if maximum_translation_voxels <= 0.0 or maximum_rotation_degrees <= 0.0:
        raise ValueError("registration correction limits must be positive")
    if not 0.0 < minimum_valid_fraction <= 1.0:
        raise ValueError("minimum_valid_fraction must lie in (0, 1]")
    population_index = np.arange(len(points))
    held_out = population_index % 5 == 0
    selection = population_index % 5 == 1
    train = ~(held_out | selection)
    if np.count_nonzero(held_out) < 20:
        raise ValueError("registration held-out set is too small")
    pivot = np.median(points, axis=0)
    current_correction = np.eye(4, dtype=np.float64)
    best_correction = np.eye(4, dtype=np.float64)
    corrected_points = points.copy()
    corrected_normals = normals.copy()
    before_selection = local_iso50_crossings(
        volume_zyx, points[selection], normals[selection],
        search_distance_voxels=search_distance_voxels,
        step_voxels=step_voxels,
        minimum_end_contrast=minimum_end_contrast,
    )
    before_held_out = local_iso50_crossings(
        volume_zyx, points[held_out], normals[held_out],
        search_distance_voxels=search_distance_voxels,
        step_voxels=step_voxels,
        minimum_end_contrast=minimum_end_contrast,
    )
    before_selection_summary = _crossing_summary(before_selection)
    if before_selection_summary["valid_fraction"] < minimum_valid_fraction:
        raise RuntimeError("selection CT surface crossing coverage is insufficient")
    best_selection_score = float("inf")
    best_selection_comparison = None
    best_iteration = 0
    optimization_converged = False
    history = []
    for iteration in range(maximum_iterations):
        crossing = local_iso50_crossings(
            volume_zyx, corrected_points[train], corrected_normals[train],
            search_distance_voxels=search_distance_voxels,
            step_voxels=step_voxels,
            minimum_end_contrast=minimum_end_contrast,
        )
        valid = np.asarray(crossing["valid"], dtype=bool)
        offsets = np.asarray(crossing["crossing_offset_voxels"], dtype=np.float64)
        if float(np.mean(valid)) < minimum_valid_fraction or np.count_nonzero(valid) < 50:
            raise RuntimeError("too few CT surface crossings for independent registration")
        selected_points = corrected_points[train][valid]
        selected_normals = corrected_normals[train][valid]
        selected_offsets = offsets[valid]
        center = float(np.median(selected_offsets))
        mad = float(np.median(np.abs(selected_offsets - center)))
        robust_scale = max(0.1, 1.4826 * mad)
        keep = np.abs(selected_offsets - center) <= max(1.0, 3.0 * robust_scale)
        selected_points = selected_points[keep]
        selected_normals = selected_normals[keep]
        selected_offsets = selected_offsets[keep]
        relative = selected_points - pivot
        system = np.concatenate(
            (np.cross(relative, selected_normals), selected_normals), axis=1
        )
        residual_scale = max(0.1, 1.4826 * float(np.median(np.abs(
            selected_offsets - np.median(selected_offsets)
        ))))
        weights = 1.0 / np.maximum(1.0, np.abs(selected_offsets) / (1.5 * residual_scale))
        weighted_system = system * np.sqrt(weights)[:, None]
        weighted_target = selected_offsets * np.sqrt(weights)
        update, _residuals, rank, singular = np.linalg.lstsq(
            weighted_system, weighted_target, rcond=None
        )
        if rank < 6:
            raise RuntimeError("CT surface normals do not constrain all six rigid parameters")
        rotation_update = update[:3]
        translation_update = update[3:]
        rotation_norm = float(np.linalg.norm(rotation_update))
        translation_norm = float(np.linalg.norm(translation_update))
        maximum_step_rotation = math.radians(0.10)
        if rotation_norm > maximum_step_rotation:
            rotation_update *= maximum_step_rotation / rotation_norm
        if translation_norm > 0.35:
            translation_update *= 0.35 / translation_norm
        step_matrix = rigid_correction_matrix(rotation_update, translation_update, pivot)
        current_correction = step_matrix @ current_correction
        corrected_points = apply_transform(points, current_correction)
        corrected_normals = _apply_rigid_to_normals(normals, current_correction)
        selection_crossings = local_iso50_crossings(
            volume_zyx, corrected_points[selection], corrected_normals[selection],
            search_distance_voxels=search_distance_voxels,
            step_voxels=step_voxels,
            minimum_end_contrast=minimum_end_contrast,
        )
        selection_summary = _crossing_summary(selection_crossings)
        comparison = _common_crossing_comparison(
            before_selection, selection_crossings
        )
        before_median = comparison["before_median_absolute_voxels"]
        after_median = comparison["after_median_absolute_voxels"]
        before_p90 = comparison["before_p90_absolute_voxels"]
        after_p90 = comparison["after_p90_absolute_voxels"]
        eligible_candidate = bool(
            before_median is not None
            and after_median is not None
            and before_p90 is not None
            and after_p90 is not None
            and comparison["common_fraction_of_baseline_valid"] >= 0.90
            and selection_summary["valid_fraction"]
            >= before_selection_summary["valid_fraction"] - 0.02
            and after_median <= before_median - 0.005
            and after_p90 <= before_p90 + 0.02
        )
        candidate_score = (
            float(after_median + 0.10 * after_p90)
            if eligible_candidate else float("inf")
        )
        if candidate_score < best_selection_score:
            best_selection_score = candidate_score
            best_correction = current_correction.copy()
            best_selection_comparison = comparison
            best_iteration = iteration + 1
        record = {
            "iteration": iteration + 1,
            "valid_crossing_fraction": float(np.mean(valid)),
            "used_crossing_count": int(len(selected_offsets)),
            "median_signed_crossing_voxels": float(np.median(selected_offsets)),
            "rotation_step_degrees": math.degrees(float(np.linalg.norm(rotation_update))),
            "translation_step_voxels": float(np.linalg.norm(translation_update)),
            "normal_system_condition": float(
                np.inf if singular[-1] == 0.0 else singular[0] / singular[-1]
            ),
            "selection_valid_fraction": selection_summary["valid_fraction"],
            "selection_common_comparison": comparison,
            "selection_candidate_eligible": eligible_candidate,
        }
        history.append(record)
        if (
            np.linalg.norm(rotation_update) < math.radians(0.001)
            and np.linalg.norm(translation_update) < 0.01
        ):
            optimization_converged = True
            break
    from scipy.spatial.transform import Rotation

    correction = best_correction
    correction_accepted = best_iteration > 0
    selection_reason = (
        f"validation-selected iteration {best_iteration}"
        if correction_accepted
        else "no validation candidate improved common-valid median without tail loss"
    )
    corrected_points = apply_transform(points, correction)
    corrected_normals = _apply_rigid_to_normals(normals, correction)
    rotation_degrees = math.degrees(float(Rotation.from_matrix(
        correction[:3, :3]
    ).magnitude()))
    translation_at_pivot = apply_transform(pivot[None, :], correction)[0] - pivot
    translation_norm = float(np.linalg.norm(translation_at_pivot))
    if rotation_degrees > maximum_rotation_degrees + 1e-9:
        raise RuntimeError(
            f"independent correction rotation {rotation_degrees:.4f} deg exceeds "
            f"{maximum_rotation_degrees:.4f} deg"
        )
    if translation_norm > maximum_translation_voxels + 1e-9:
        raise RuntimeError(
            f"independent correction translation {translation_norm:.4f} vox exceeds "
            f"{maximum_translation_voxels:.4f} vox"
        )
    after_held_out = local_iso50_crossings(
        volume_zyx, corrected_points[held_out], corrected_normals[held_out],
        search_distance_voxels=search_distance_voxels,
        step_voxels=step_voxels,
        minimum_end_contrast=minimum_end_contrast,
    )
    before_summary = _crossing_summary(before_held_out)
    after_summary = _crossing_summary(after_held_out)
    if after_summary["valid_fraction"] < minimum_valid_fraction:
        raise RuntimeError("held-out CT surface crossing coverage is insufficient")
    held_out_comparison = _common_crossing_comparison(
        before_held_out, after_held_out
    )
    if correction_accepted and (
        held_out_comparison["common_fraction_of_baseline_valid"] < 0.90
        or held_out_comparison["after_median_absolute_voxels"]
        > held_out_comparison["before_median_absolute_voxels"]
        or held_out_comparison["after_p90_absolute_voxels"]
        > held_out_comparison["before_p90_absolute_voxels"] + 0.05
    ):
        correction = np.eye(4, dtype=np.float64)
        correction_accepted = False
        selection_reason = "validation candidate rejected by untouched held-out audit"
        rotation_degrees = 0.0
        translation_at_pivot = np.zeros(3, dtype=np.float64)
        translation_norm = 0.0
        after_summary = before_summary
        held_out_comparison = _common_crossing_comparison(
            before_held_out, before_held_out
        )
    return {
        "correction_matrix": correction,
        "pivot_xyz_voxels": pivot,
        "rotation_degrees": rotation_degrees,
        "translation_xyz_voxels": translation_at_pivot,
        "translation_magnitude_voxels": translation_norm,
        "before_held_out": before_summary,
        "after_held_out": after_summary,
        "held_out_common_comparison": held_out_comparison,
        "before_selection": before_selection_summary,
        "best_selection_common_comparison": best_selection_comparison,
        "selected_iteration": best_iteration if correction_accepted else 0,
        "correction_accepted": correction_accepted,
        "selection_reason": selection_reason,
        "registration_uncertainty_voxels": max(
            0.25,
            float(after_summary["robust_sigma_voxels"] or 0.0),
        ),
        "iteration_history": history,
        "train_sample_count": int(np.count_nonzero(train)),
        "selection_sample_count": int(np.count_nonzero(selection)),
        "held_out_sample_count": int(np.count_nonzero(held_out)),
        "converged": optimization_converged,
        "method": "local-ISO50 robust point-to-plane rigid refinement",
    }


__all__ = [
    "local_iso50_crossings",
    "refine_rigid_registration",
    "rigid_correction_matrix",
    "sample_stl_surface_by_area",
    "trilinear_sample",
]
