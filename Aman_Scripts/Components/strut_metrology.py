"""Compact native-resolution measurements for one CAD-expected lattice strut."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from scipy import ndimage

from .ct_surface_metrology import trilinear_sample


def _xyz(value: Sequence[float], name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain three finite XYZ values")
    return result


def _cross_section_frame(
    endpoint0_xyz: Sequence[float], endpoint1_xyz: Sequence[float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    first = _xyz(endpoint0_xyz, "endpoint0_xyz")
    second = _xyz(endpoint1_xyz, "endpoint1_xyz")
    delta = second - first
    length = float(np.linalg.norm(delta))
    if length <= np.finfo(np.float64).eps:
        raise ValueError("strut endpoints must be distinct")
    direction = delta / length
    reference = np.zeros(3, dtype=np.float64)
    reference[int(np.argmin(np.abs(direction)))] = 1.0
    first_axis = np.cross(direction, reference)
    first_axis /= np.linalg.norm(first_axis)
    second_axis = np.cross(direction, first_axis)
    second_axis /= np.linalg.norm(second_axis)
    return first, second, direction, np.stack((first_axis, second_axis)), length


def _radius_profile(
    expected_radius_voxels: float | Sequence[float], station_count: int
) -> np.ndarray:
    raw = np.asarray(expected_radius_voxels, dtype=np.float64)
    if raw.ndim == 0:
        result = np.repeat(float(raw), station_count)
    elif raw.ndim == 1 and len(raw) >= 2:
        result = np.interp(
            np.linspace(0.0, 1.0, station_count),
            np.linspace(0.0, 1.0, len(raw)),
            raw,
        )
    else:
        raise ValueError("expected_radius_voxels must be a scalar or vector with >=2 values")
    if not np.isfinite(result).all() or np.any(result <= 0.0):
        raise ValueError("expected radius values must be finite and positive")
    return result


def _longest_false_run(profile: np.ndarray) -> int:
    missing = ~np.asarray(profile, dtype=bool)
    padded = np.concatenate(([False], missing, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(changes[1::2] - changes[::2], initial=0))


def _otsu_level(values: np.ndarray, bins: int = 128) -> float | None:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size < 16:
        return None
    lower, upper = np.quantile(finite, (0.01, 0.99))
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        return None
    histogram, edges = np.histogram(finite, bins=bins, range=(lower, upper))
    centers = 0.5 * (edges[:-1] + edges[1:])
    counts = histogram.astype(np.float64)
    cumulative_count = np.cumsum(counts)
    cumulative_sum = np.cumsum(counts * centers)
    total_count = cumulative_count[-1]
    total_sum = cumulative_sum[-1]
    denominator = cumulative_count * (total_count - cumulative_count)
    score = np.zeros_like(denominator)
    valid = denominator > 0.0
    score[valid] = (
        total_sum * cumulative_count[valid]
        - cumulative_sum[valid] * total_count
    ) ** 2 / denominator[valid]
    if not np.any(valid):
        return None
    return float(centers[int(np.argmax(score))])


def _select_seeded_material_component(
    values: np.ndarray,
    valid: np.ndarray,
    local_uv: np.ndarray,
    grid_shape: tuple[int, int],
    radial_grid: np.ndarray,
    expected_radius: float,
    minimum_local_contrast: float,
) -> dict[str, Any]:
    """Isolate material connected to a small seed around the CAD centerline."""

    measurement_disk = radial_grid <= expected_radius + 2.0
    usable = valid & measurement_disk & np.isfinite(values)
    if np.count_nonzero(usable) < 16:
        return {"reason": "invalid_sampling_geometry"}
    low, high = np.quantile(values[usable], (0.10, 0.90))
    contrast = float(high - low)
    if not np.isfinite(contrast) or contrast < minimum_local_contrast:
        return {"reason": "insufficient_local_contrast", "contrast": contrast}
    level = _otsu_level(values[usable])
    if level is None:
        return {"reason": "insufficient_local_contrast", "contrast": contrast}
    material = usable & (values >= level)
    labels, label_count = ndimage.label(
        material.reshape(grid_shape), structure=np.ones((3, 3), dtype=np.uint8)
    )
    labels = labels.ravel()
    # Association may tolerate a center shift up to one expected radius, but
    # never searches the full crop for arbitrary nearby material.
    seed = radial_grid <= max(1.0, expected_radius)
    candidates = np.unique(labels[seed & material])
    candidates = candidates[candidates > 0]
    if not candidates.size:
        return {
            "reason": "no_material_component_at_cad_axis",
            "contrast": contrast,
            "level": float(level),
        }
    ranked = []
    for label_id in candidates:
        component = labels == label_id
        ranked.append((int(np.count_nonzero(component & seed)),
                       int(np.count_nonzero(component)), int(label_id)))
    _seed_count, _area, selected_id = max(ranked)
    component = labels == selected_id
    weights = np.clip((values - level) / max(contrast, 1.0), 0.0, 1.0)
    weights[~component] = 0.0
    weight_sum = float(weights.sum())
    if weight_sum <= 0.0:
        return {"reason": "insufficient_cross_section_material"}
    centroid = np.sum(local_uv * weights[:, None], axis=0) / weight_sum
    expected_pixel_count = max(1, int(np.count_nonzero(radial_grid <= expected_radius)))
    return {
        "reason": "component_selected",
        "contrast": contrast,
        "level": float(level),
        "component": component,
        "centroid_uv": centroid,
        "area_fraction": float(np.count_nonzero(component) / expected_pixel_count),
    }


def _radial_crossings(
    volume_zyx: np.ndarray,
    center_xyz: np.ndarray,
    axes_uv: np.ndarray,
    expected_radius: float,
    *,
    ray_count: int,
    radial_step_voxels: float,
    search_margin_voxels: float,
    minimum_local_contrast: float,
    surface_level: float | None = None,
) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * math.pi, ray_count, endpoint=False)
    directions = (
        np.cos(angles)[:, None] * axes_uv[0][None, :]
        + np.sin(angles)[:, None] * axes_uv[1][None, :]
    )
    maximum_radius = expected_radius + search_margin_voxels
    radii = np.arange(0.0, maximum_radius + 0.5 * radial_step_voxels, radial_step_voxels)
    query = center_xyz[None, None, :] + directions[:, None, :] * radii[None, :, None]
    sampled, valid = trilinear_sample(volume_zyx, query.reshape(-1, 3))
    profiles = sampled.reshape(ray_count, len(radii))
    bounds = valid.reshape(ray_count, len(radii)).all(axis=1)
    crossings = np.full(ray_count, np.nan, dtype=np.float64)
    for index, profile in enumerate(profiles):
        if not bounds[index] or not np.isfinite(profile).all():
            continue
        if surface_level is None:
            inside = profile[radii <= max(0.75, 0.40 * expected_radius)]
            outside = profile[
                radii >= expected_radius + max(1.0, 0.50 * search_margin_voxels)
            ]
            if not len(inside) or not len(outside):
                continue
            inside_level = float(np.median(inside))
            outside_level = float(np.median(outside))
            contrast = inside_level - outside_level
            if contrast < minimum_local_contrast:
                continue
            level = 0.5 * (inside_level + outside_level)
        else:
            level = float(surface_level)
            if profile[0] < level:
                continue
        centered = profile - level
        candidates = np.flatnonzero(
            (radii[:-1] >= 0.25 * expected_radius)
            & (centered[:-1] >= 0.0)
            & (centered[1:] < 0.0)
        )
        if not candidates.size:
            continue
        candidate = int(candidates[0])
        denominator = centered[candidate + 1] - centered[candidate]
        fraction = 0.0 if denominator == 0.0 else -centered[candidate] / denominator
        crossings[index] = radii[candidate] + fraction * (
            radii[candidate + 1] - radii[candidate]
        )
    return crossings


def measure_strut_cross_sections(
    volume_zyx: np.ndarray,
    endpoint0_xyz: Sequence[float],
    endpoint1_xyz: Sequence[float],
    expected_radius_voxels: float | Sequence[float],
    *,
    endpoint_exclusion_fraction: float = 0.12,
    axial_step_voxels: float = 1.0,
    cross_section_step_voxels: float = 0.5,
    search_margin_voxels: float = 3.0,
    ray_count: int = 16,
    radial_step_voxels: float = 0.25,
    minimum_local_contrast: float = 1000.0,
    minimum_presence_area_fraction: float = 0.15,
    minimum_area_fraction: float = 0.35,
    minimum_valid_ray_fraction: float = 0.50,
    connection_gap_tolerance_voxels: float = 1.5,
) -> dict[str, Any]:
    """Measure one expected strut from bounded native-TIFF cross-sections."""

    volume = np.asarray(volume_zyx)
    if volume.ndim != 3 or volume.dtype.kind not in "uif":
        raise ValueError("volume_zyx must be a numeric 3D array")
    first, second, direction, axes, length = _cross_section_frame(
        endpoint0_xyz, endpoint1_xyz
    )
    if not 0.0 <= endpoint_exclusion_fraction < 0.45:
        raise ValueError("endpoint_exclusion_fraction must lie in [0, 0.45)")
    positive_values = {
        "axial_step_voxels": axial_step_voxels,
        "cross_section_step_voxels": cross_section_step_voxels,
        "search_margin_voxels": search_margin_voxels,
        "radial_step_voxels": radial_step_voxels,
        "connection_gap_tolerance_voxels": connection_gap_tolerance_voxels,
    }
    if any(not np.isfinite(value) or value <= 0.0 for value in positive_values.values()):
        raise ValueError("sampling steps, margins, and gap tolerance must be positive")
    if not isinstance(ray_count, int) or ray_count < 8:
        raise ValueError("ray_count must be an integer >= 8")
    if not np.isfinite(minimum_local_contrast) or minimum_local_contrast < 0.0:
        raise ValueError("minimum_local_contrast must be nonnegative")
    if not 0.0 < minimum_presence_area_fraction <= minimum_area_fraction <= 1.0:
        raise ValueError(
            "area fractions must satisfy 0 < minimum_presence <= minimum_area <= 1"
        )
    if not 0.0 < minimum_valid_ray_fraction <= 1.0:
        raise ValueError("minimum_valid_ray_fraction must lie in (0, 1]")
    start = endpoint_exclusion_fraction * length
    stop = (1.0 - endpoint_exclusion_fraction) * length
    body_length = stop - start
    station_count = max(3, int(math.floor(body_length / axial_step_voxels)) + 1)
    axial_positions = np.linspace(start, stop, station_count)
    station_step = body_length / max(1, station_count - 1)
    stations = first[None, :] + axial_positions[:, None] * direction[None, :]
    expected_radii = _radius_profile(expected_radius_voxels, station_count)
    grid_extent = float(np.max(expected_radii) + search_margin_voxels)
    coordinates = np.arange(
        -grid_extent,
        grid_extent + 0.5 * cross_section_step_voxels,
        cross_section_step_voxels,
    )
    vv, uu = np.meshgrid(coordinates, coordinates, indexing="ij")
    local_uv = np.stack((uu.ravel(), vv.ravel()), axis=1)
    offsets_xyz = local_uv @ axes
    query = stations[:, None, :] + offsets_xyz[None, :, :]
    sampled, in_bounds = trilinear_sample(volume, query.reshape(-1, 3))
    intensities = sampled.reshape(station_count, len(local_uv))
    bounds = in_bounds.reshape(station_count, len(local_uv))
    radial_grid = np.linalg.norm(local_uv, axis=1)
    supported = np.zeros(station_count, dtype=bool)
    radial_valid = np.zeros(station_count, dtype=bool)
    local_levels = np.full(station_count, np.nan, dtype=np.float64)
    contrasts = np.full(station_count, np.nan, dtype=np.float64)
    area_fractions = np.full(station_count, np.nan, dtype=np.float64)
    center_uv = np.full((station_count, 2), np.nan, dtype=np.float64)
    center_displacement = np.full(station_count, np.nan, dtype=np.float64)
    observed_radius = np.full(station_count, np.nan, dtype=np.float64)
    valid_ray_fraction = np.zeros(station_count, dtype=np.float64)
    station_reasons = []
    for index, values in enumerate(intensities):
        radius = expected_radii[index]
        required = radial_grid <= radius + search_margin_voxels
        if float(np.mean(bounds[index][required])) < 0.99:
            station_reasons.append("cross_section_out_of_bounds")
            continue
        component = _select_seeded_material_component(
            values, bounds[index], local_uv, vv.shape, radial_grid, radius,
            minimum_local_contrast,
        )
        contrasts[index] = component.get("contrast", np.nan)
        local_levels[index] = component.get("level", np.nan)
        if component["reason"] != "component_selected":
            station_reasons.append(component["reason"])
            continue
        area_fraction = float(component["area_fraction"])
        area_fractions[index] = area_fraction
        if area_fraction < minimum_presence_area_fraction:
            station_reasons.append("insufficient_cross_section_material")
            continue
        centroid = np.asarray(component["centroid_uv"], dtype=np.float64)
        center_uv[index] = centroid
        center_displacement[index] = float(np.linalg.norm(centroid))
        supported[index] = True
        if area_fraction < minimum_area_fraction:
            station_reasons.append("present_radial_area_uncertain")
            continue
        center_xyz = stations[index] + centroid @ axes
        crossings = _radial_crossings(
            volume,
            center_xyz,
            axes,
            radius,
            ray_count=ray_count,
            radial_step_voxels=radial_step_voxels,
            search_margin_voxels=search_margin_voxels,
            minimum_local_contrast=minimum_local_contrast,
            surface_level=float(component["level"]),
        )
        ray_fraction = float(np.mean(np.isfinite(crossings)))
        valid_ray_fraction[index] = ray_fraction
        if ray_fraction < minimum_valid_ray_fraction:
            station_reasons.append("present_radial_crossings_uncertain")
            continue
        observed_radius[index] = float(np.median(crossings[np.isfinite(crossings)]))
        radial_valid[index] = True
        station_reasons.append("supported")
    longest_run = _longest_false_run(supported)
    longest_gap = float(longest_run * station_step)
    connected = bool(
        supported[0]
        and supported[-1]
        and longest_gap <= connection_gap_tolerance_voxels
    )
    radius_deviation = observed_radius - expected_radii
    valid_radius = np.isfinite(radius_deviation) & radial_valid
    valid_center = np.isfinite(center_displacement) & supported
    if np.any(valid_radius):
        signed = radius_deviation[valid_radius]
        radial_median = float(np.median(signed))
        radial_p90 = float(np.quantile(np.abs(signed), 0.90))
    else:
        radial_median = None
        radial_p90 = None
    center_p90 = (
        float(np.quantile(center_displacement[valid_center], 0.90))
        if np.any(valid_center) else None
    )
    observed_fraction = float(np.mean(supported))
    measurement_valid = bool(
        station_count >= 3
        and np.count_nonzero(supported) >= 2
        and radial_median is not None
        and center_p90 is not None
    )
    return {
        "measurement_valid": measurement_valid,
        "endpoint0_xyz_voxels": first.tolist(),
        "endpoint1_xyz_voxels": second.tolist(),
        "length_voxels": length,
        "station_count": station_count,
        "station_step_voxels": station_step,
        "observed_axial_fraction": observed_fraction,
        "longest_unsupported_gap_voxels": longest_gap,
        "connected_support": connected,
        "median_signed_radial_deviation_voxels": radial_median,
        "p90_absolute_radial_deviation_voxels": radial_p90,
        "p90_centerline_displacement_voxels": center_p90,
        "station_axial_position_voxels": axial_positions.tolist(),
        "station_supported": supported.astype(np.uint8).tolist(),
        "station_radial_measurement_valid": radial_valid.astype(np.uint8).tolist(),
        "station_expected_radius_voxels": expected_radii.tolist(),
        "station_observed_radius_voxels": [
            None if not np.isfinite(value) else float(value) for value in observed_radius
        ],
        "station_center_displacement_voxels": [
            None if not np.isfinite(value) else float(value) for value in center_displacement
        ],
        "station_local_iso50_level": [
            None if not np.isfinite(value) else float(value) for value in local_levels
        ],
        "station_local_contrast": [
            None if not np.isfinite(value) else float(value) for value in contrasts
        ],
        "station_area_fraction": [
            None if not np.isfinite(value) else float(value) for value in area_fractions
        ],
        "station_valid_ray_fraction": valid_ray_fraction.tolist(),
        "station_reason": station_reasons,
        "parameters": {
            "endpoint_exclusion_fraction": endpoint_exclusion_fraction,
            "axial_step_voxels": axial_step_voxels,
            "cross_section_step_voxels": cross_section_step_voxels,
            "search_margin_voxels": search_margin_voxels,
            "ray_count": ray_count,
            "radial_step_voxels": radial_step_voxels,
            "minimum_local_contrast": minimum_local_contrast,
            "minimum_presence_area_fraction": minimum_presence_area_fraction,
            "minimum_area_fraction": minimum_area_fraction,
            "minimum_valid_ray_fraction": minimum_valid_ray_fraction,
            "connection_gap_tolerance_voxels": connection_gap_tolerance_voxels,
        },
    }


def classify_strut_measurement(
    measurement: dict[str, Any],
    *,
    registration_uncertainty_voxels: float,
    minimum_axial_fraction: float = 0.80,
    maximum_gap_voxels: float = 3.0,
    manufacturing_radial_tolerance_voxels: float = 0.75,
    manufacturing_centerline_tolerance_voxels: float = 0.75,
    review_margin_voxels: float = 0.25,
) -> dict[str, Any]:
    """Apply explicit tolerances without altering the underlying measurement."""

    if not isinstance(measurement, dict):
        raise ValueError("measurement must be a dictionary")
    if not np.isfinite(registration_uncertainty_voxels) or registration_uncertainty_voxels < 0:
        raise ValueError("registration uncertainty must be finite and nonnegative")
    if not 0.0 < minimum_axial_fraction <= 1.0:
        raise ValueError("minimum_axial_fraction must lie in (0, 1]")
    positive = (
        maximum_gap_voxels,
        manufacturing_radial_tolerance_voxels,
        manufacturing_centerline_tolerance_voxels,
        review_margin_voxels,
    )
    if any(not np.isfinite(value) or value < 0.0 for value in positive):
        raise ValueError("decision tolerances must be finite and nonnegative")
    if measurement.get("measurement_valid") is not True:
        return {
            "has_error": None,
            "review_required": True,
            "decision_reason": "insufficient_measurement_evidence",
            "failed_checks": [],
        }
    required = (
        "observed_axial_fraction",
        "longest_unsupported_gap_voxels",
        "connected_support",
        "median_signed_radial_deviation_voxels",
        "p90_absolute_radial_deviation_voxels",
        "p90_centerline_displacement_voxels",
    )
    if any(measurement.get(name) is None for name in required):
        raise ValueError("valid measurement is missing required metrics")
    axial = float(measurement["observed_axial_fraction"])
    gap = float(measurement["longest_unsupported_gap_voxels"])
    radial_median = abs(float(measurement["median_signed_radial_deviation_voxels"]))
    radial_p90 = float(measurement["p90_absolute_radial_deviation_voxels"])
    center_p90 = float(measurement["p90_centerline_displacement_voxels"])
    radial_limit = manufacturing_radial_tolerance_voxels + registration_uncertainty_voxels
    center_limit = manufacturing_centerline_tolerance_voxels + registration_uncertainty_voxels
    failed = []
    if axial < minimum_axial_fraction:
        failed.append("axial_coverage")
    if gap > maximum_gap_voxels:
        failed.append("unsupported_gap")
    if measurement["connected_support"] is not True:
        failed.append("continuous_support")
    if radial_median > radial_limit or radial_p90 > radial_limit:
        failed.append("radial_deviation")
    if center_p90 > center_limit:
        failed.append("centerline_displacement")
    confirmed_failed = [
        name for name in failed
        if name in {"axial_coverage", "unsupported_gap", "radial_deviation"}
    ]
    if confirmed_failed:
        return {
            "has_error": True,
            "review_required": True,
            "decision_reason": "one_or_more_measurement_tolerances_exceeded",
            "failed_checks": failed,
            "effective_radial_tolerance_voxels": radial_limit,
            "effective_centerline_tolerance_voxels": center_limit,
        }
    if failed:
        only_centerline = failed == ["centerline_displacement"]
        return {
            "has_error": None,
            "review_required": True,
            "decision_reason": (
                "centerline_offset_requires_local_alignment_review"
                if only_centerline else "nonconfirmatory_connectivity_or_location_review"
            ),
            "failed_checks": failed,
            "effective_radial_tolerance_voxels": radial_limit,
            "effective_centerline_tolerance_voxels": center_limit,
        }
    clearly_healthy = bool(
        axial >= min(1.0, minimum_axial_fraction + 0.05)
        and gap <= max(0.0, maximum_gap_voxels - 1.0)
        and measurement["connected_support"] is True
        and radial_p90 <= max(0.0, radial_limit - review_margin_voxels)
        and center_p90 <= max(0.0, center_limit - review_margin_voxels)
    )
    return {
        "has_error": False if clearly_healthy else None,
        "review_required": not clearly_healthy,
        "decision_reason": (
            "all_measurements_clearly_inside_tolerance"
            if clearly_healthy else "measurements_near_a_declared_tolerance"
        ),
        "failed_checks": [],
        "effective_radial_tolerance_voxels": radial_limit,
        "effective_centerline_tolerance_voxels": center_limit,
    }


__all__ = ["classify_strut_measurement", "measure_strut_cross_sections"]
