"""Direct, native-resolution comparison of one STL strut with CT material.

The STL side is represented by transformed surface samples belonging to one
registered graph edge.  The CT side is sampled directly from a ``ZYX`` scalar
volume at those same physical locations.  No whole-volume STL mask and no CT
downsampling are used.

Public functions intentionally return ordinary dictionaries so the results can
be copied directly onto the repository's existing lattice JSON records.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import math
from typing import Any

import numpy as np

from .local_contrast import evaluate_annular_hysteresis_contrast


class StrutComparisonError(ValueError):
    """Raised when a local STL/CT comparison is geometrically invalid."""


def _xyz(value: Sequence[float], name: str) -> np.ndarray:
    point = np.asarray(value, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise StrutComparisonError(f"{name} must contain three finite XYZ values")
    return point


def _profile(value: Iterable[bool], name: str) -> np.ndarray:
    result = np.asarray(tuple(value), dtype=bool)
    if result.ndim != 1 or result.size == 0:
        raise StrutComparisonError(f"{name} must be a nonempty one-dimensional profile")
    return result


def _longest_true_run(values: np.ndarray) -> int:
    padded = np.concatenate(([False], np.asarray(values, dtype=bool), [False]))
    transitions = np.flatnonzero(padded[1:] != padded[:-1])
    if transitions.size == 0:
        return 0
    return int(np.max(transitions[1::2] - transitions[::2], initial=0))


def evaluate_strut_profiles(
    expected_profile: Iterable[bool],
    realized_profile: Iterable[bool],
    *,
    minimum_gap_voxels: int = 3,
    minimum_realized_fraction: float = 0.80,
    bridge_connected: bool | None = True,
    perturbation_agreement: float = 1.0,
    minimum_perturbation_agreement: float = 0.80,
    expected_present: bool = True,
) -> dict[str, Any]:
    """Turn paired axial profiles into one conservative binary decision.

    ``expected_profile`` marks axial bins occupied by the STL.  A realized bin
    is useful only where the STL expects material.  ``has_error`` is nullable:
    unstable or unobservable measurements must never silently become healthy.
    This function deliberately does not distinguish missing from broken.
    """

    expected = _profile(expected_profile, "expected_profile")
    realized = _profile(realized_profile, "realized_profile")
    if expected.shape != realized.shape:
        raise StrutComparisonError(
            f"profile shapes differ: expected {expected.shape}, realized {realized.shape}"
        )
    if minimum_gap_voxels < 1:
        raise StrutComparisonError("minimum_gap_voxels must be at least 1")
    for value, label in (
        (minimum_realized_fraction, "minimum_realized_fraction"),
        (perturbation_agreement, "perturbation_agreement"),
        (minimum_perturbation_agreement, "minimum_perturbation_agreement"),
    ):
        if not (np.isfinite(value) and 0.0 <= value <= 1.0):
            raise StrutComparisonError(f"{label} must lie in [0, 1]")

    expected_bins = int(np.count_nonzero(expected))
    if not expected_present:
        return {
            "comparison_applicable": False,
            "comparison_valid": True,
            "has_error": False,
            "review_required": False,
            "confidence": 1.0,
            "realized_axial_fraction": None,
            "longest_unrealized_gap_voxels": 0,
            "longest_unrealized_gap_fraction": 0.0,
            "bridge_connected_26": None,
            "perturbation_agreement": float(perturbation_agreement),
            "decision_reason": "stl_does_not_expect_a_strut",
        }
    if expected_bins == 0 or bridge_connected is None:
        return {
            "comparison_applicable": True,
            "comparison_valid": False,
            "has_error": None,
            "review_required": True,
            "confidence": 0.0,
            "realized_axial_fraction": None,
            "longest_unrealized_gap_voxels": None,
            "longest_unrealized_gap_fraction": None,
            "bridge_connected_26": bridge_connected,
            "perturbation_agreement": float(perturbation_agreement),
            "decision_reason": "insufficient_expected_or_ct_coverage",
        }

    supported = expected & realized
    missing = expected & ~realized
    realized_fraction = float(np.count_nonzero(supported) / expected_bins)
    longest_gap = _longest_true_run(missing)
    longest_gap_fraction = float(longest_gap / expected_bins)
    unstable = perturbation_agreement < minimum_perturbation_agreement
    if unstable:
        has_error: bool | None = None
        reason = "threshold_or_registration_unstable"
    else:
        low_realization = realized_fraction < minimum_realized_fraction
        long_gap = longest_gap >= minimum_gap_voxels
        broken_bridge = not bool(bridge_connected)
        # A bridge can break because a one-voxel threshold fluctuation severs a
        # 26-neighbour path.  Treat that evidence alone as review-required,
        # rather than promoting a sub-resolution pinhole to a confirmed error.
        if broken_bridge and not (low_realization or long_gap):
            has_error = None
            reason = "bridge_only_disagreement"
        else:
            has_error = bool(low_realization or long_gap)
        reasons = []
        if low_realization:
            reasons.append("low_stl_realization")
        if long_gap:
            reasons.append("continuous_unrealized_gap")
        if broken_bridge:
            reasons.append("broken_ct_bridge")
        if has_error is not None:
            reason = "+".join(reasons) if reasons else "stl_strut_realized_in_ct"

    realization_margin = abs(realized_fraction - minimum_realized_fraction)
    gap_margin = abs(longest_gap - minimum_gap_voxels) / max(expected_bins, 1)
    evidence_margin = min(1.0, realization_margin + gap_margin)
    confidence = float(perturbation_agreement * (0.75 + 0.25 * evidence_margin))
    if has_error is None:
        confidence = 0.0
    return {
        "comparison_applicable": True,
        "comparison_valid": has_error is not None,
        "has_error": has_error,
        "review_required": has_error is not False,
        "confidence": confidence,
        "realized_axial_fraction": realized_fraction,
        "longest_unrealized_gap_voxels": longest_gap,
        "longest_unrealized_gap_fraction": longest_gap_fraction,
        "bridge_connected_26": bool(bridge_connected),
        "perturbation_agreement": float(perturbation_agreement),
        "decision_reason": reason,
    }


def _validate_volume(volume: np.ndarray) -> np.ndarray:
    array = np.asanyarray(volume)
    if array.ndim != 3 or any(int(size) < 2 for size in array.shape):
        raise StrutComparisonError(f"ct_volume_zyx must be a nonempty 3D array, got {array.shape}")
    if array.dtype.kind not in "uibf":
        raise StrutComparisonError(f"ct_volume_zyx must be numeric, got {array.dtype}")
    return array


def _axial_geometry(
    endpoint0_xyz: Sequence[float],
    endpoint1_xyz: Sequence[float],
    endpoint_exclusion_fraction: float,
    axial_step_voxels: float,
) -> tuple[np.ndarray, np.ndarray, float, float, float, int]:
    first = _xyz(endpoint0_xyz, "endpoint0_xyz")
    second = _xyz(endpoint1_xyz, "endpoint1_xyz")
    vector = second - first
    length = float(np.linalg.norm(vector))
    if length <= 0.0:
        raise StrutComparisonError("strut endpoints must be distinct")
    if not (0.0 <= endpoint_exclusion_fraction < 0.5):
        raise StrutComparisonError("endpoint_exclusion_fraction must lie in [0, 0.5)")
    if not (np.isfinite(axial_step_voxels) and axial_step_voxels > 0.0):
        raise StrutComparisonError("axial_step_voxels must be positive")
    start = endpoint_exclusion_fraction * length
    stop = (1.0 - endpoint_exclusion_fraction) * length
    body_length = stop - start
    bins = max(1, int(math.ceil(body_length / axial_step_voxels)))
    return first, vector / length, length, start, stop, bins


def _surface_bins(
    surface_xyz: np.ndarray,
    first: np.ndarray,
    direction: np.ndarray,
    start: float,
    stop: float,
    bins: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(surface_xyz, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise StrutComparisonError(
            f"stl_surface_points_xyz must have finite shape (n, 3), got {points.shape}"
        )
    if points.shape[0] == 0:
        return points, np.empty(0, dtype=np.int64), np.zeros(bins, dtype=np.int64)
    axial = (points - first) @ direction
    inside = (axial >= start) & (axial <= stop)
    points = points[inside]
    axial = axial[inside]
    if points.shape[0] == 0:
        return points, np.empty(0, dtype=np.int64), np.zeros(bins, dtype=np.int64)
    scaled = (axial - start) / max(stop - start, np.finfo(float).eps)
    indices = np.minimum((scaled * bins).astype(np.int64), bins - 1)
    counts = np.bincount(indices, minlength=bins).astype(np.int64, copy=False)
    return points, indices, counts


def _maximum_nearby_intensity(
    volume_zyx: np.ndarray,
    points_xyz: np.ndarray,
    radius: float,
    shift_xyz: Sequence[float] = (0.0, 0.0, 0.0),
    *,
    chunk_points: int = 1024,
) -> tuple[np.ndarray, np.ndarray]:
    if not (np.isfinite(radius) and radius >= 0.0):
        raise StrutComparisonError("distance_tolerance_voxels must be finite and nonnegative")
    shifted = points_xyz + _xyz(shift_xyz, "shift_xyz")
    maxima = np.full(len(shifted), -np.inf, dtype=np.float64)
    observable = np.zeros(len(shifted), dtype=bool)
    extent = int(math.ceil(radius)) + 1
    axis = np.arange(-extent, extent + 1, dtype=np.int64)
    zz, yy, xx = np.meshgrid(axis, axis, axis, indexing="ij")
    offsets_xyz = np.stack((xx.ravel(), yy.ravel(), zz.ravel()), axis=1)
    shape_xyz = np.asarray(volume_zyx.shape[::-1], dtype=np.int64)

    for begin in range(0, len(shifted), chunk_points):
        points = shifted[begin : begin + chunk_points]
        bases = np.floor(points).astype(np.int64)
        candidates = bases[:, None, :] + offsets_xyz[None, :, :]
        distance_ok = np.sum((candidates - points[:, None, :]) ** 2, axis=2) <= radius ** 2 + 1e-12
        bounds_ok = np.all((candidates >= 0) & (candidates < shape_xyz), axis=2)
        valid = distance_ok & bounds_ok
        rows = np.flatnonzero(np.any(valid, axis=1))
        if rows.size:
            for row in rows:
                xyz = candidates[row, valid[row]]
                values = volume_zyx[xyz[:, 2], xyz[:, 1], xyz[:, 0]]
                maxima[begin + row] = float(np.max(values))
                observable[begin + row] = True
    return maxima, observable


def _interpolated_realized_profile(
    bin_indices: np.ndarray,
    expected_counts: np.ndarray,
    matched_points: np.ndarray,
    minimum_supported_bin_fraction: float,
) -> tuple[np.ndarray, np.ndarray]:
    matched_counts = np.bincount(
        bin_indices, weights=matched_points.astype(np.float64), minlength=len(expected_counts)
    )
    fractions = np.full(len(expected_counts), np.nan, dtype=np.float64)
    sampled = expected_counts > 0
    fractions[sampled] = matched_counts[sampled] / expected_counts[sampled]
    sampled_indices = np.flatnonzero(sampled)
    if sampled_indices.size == 0:
        return np.zeros(len(expected_counts), dtype=bool), fractions
    if sampled_indices.size == 1:
        fractions[:] = fractions[sampled_indices[0]]
    else:
        missing = ~sampled
        fractions[missing] = np.interp(
            np.flatnonzero(missing), sampled_indices, fractions[sampled_indices]
        )
    return fractions >= minimum_supported_bin_fraction, fractions


def _cross_section_intensities(
    volume_zyx: np.ndarray,
    first_xyz: np.ndarray,
    direction_xyz: np.ndarray,
    start: float,
    stop: float,
    bins: int,
    *,
    radius_voxels: float,
    shift_xyz: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, int]:
    """Sample native CT intensities on edge-normal disks at every axial bin."""

    if not (np.isfinite(radius_voxels) and radius_voxels > 0.0):
        raise StrutComparisonError("cross-section radius must be positive")
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(direction_xyz @ reference)) > 0.90:
        reference = np.array([0.0, 1.0, 0.0])
    basis0 = np.cross(direction_xyz, reference)
    basis0 /= np.linalg.norm(basis0)
    basis1 = np.cross(direction_xyz, basis0)

    extent = int(math.ceil(radius_voxels))
    grid = np.arange(-extent, extent + 1, dtype=np.float64)
    uu, vv = np.meshgrid(grid, grid, indexing="ij")
    disk = uu * uu + vv * vv <= radius_voxels ** 2 + 1e-12
    offsets = (
        uu[disk, None] * basis0[None, :]
        + vv[disk, None] * basis1[None, :]
    )
    positions = start + (np.arange(bins, dtype=np.float64) + 0.5) * (stop - start) / bins
    centers = first_xyz + positions[:, None] * direction_xyz
    coordinates = centers[:, None, :] + offsets[None, :, :] + _xyz(shift_xyz, "shift_xyz")
    indices_xyz = np.floor(coordinates + 0.5).astype(np.int64)
    shape_xyz = np.asarray(volume_zyx.shape[::-1], dtype=np.int64)
    valid = np.all((indices_xyz >= 0) & (indices_xyz < shape_xyz), axis=2)
    # Oblique disk coordinates can round onto the same native voxel.  Count
    # each physical voxel once so diagonal members cannot receive artificially
    # inflated cross-sectional support.
    unique_indices: list[np.ndarray] = []
    maximum_unique = 0
    for row in range(indices_xyz.shape[0]):
        selected = indices_xyz[row, valid[row]]
        unique = np.unique(selected, axis=0) if selected.size else selected
        unique_indices.append(unique)
        maximum_unique = max(maximum_unique, int(unique.shape[0]))
    values = np.full((bins, maximum_unique), -np.inf, dtype=np.float64)
    unique_valid = np.zeros((bins, maximum_unique), dtype=bool)
    for row, unique in enumerate(unique_indices):
        count = int(unique.shape[0])
        if count == 0:
            continue
        values[row, :count] = volume_zyx[
            unique[:, 2], unique[:, 1], unique[:, 0]
        ]
        unique_valid[row, :count] = True
    return values, unique_valid, maximum_unique


def _bridge_connected_26(
    volume_zyx: np.ndarray,
    endpoint0_xyz: np.ndarray,
    endpoint1_xyz: np.ndarray,
    *,
    threshold: float,
    corridor_radius_voxels: float,
) -> tuple[bool | None, float]:
    """Return whether foreground connects the two endpoint bands in a cylinder."""

    from scipy import ndimage

    vector = endpoint1_xyz - endpoint0_xyz
    length = float(np.linalg.norm(vector))
    direction = vector / length
    padding = corridor_radius_voxels + 1.0
    lower_xyz = np.floor(np.minimum(endpoint0_xyz, endpoint1_xyz) - padding).astype(int)
    upper_xyz = np.ceil(np.maximum(endpoint0_xyz, endpoint1_xyz) + padding).astype(int) + 1
    shape_xyz = np.asarray(volume_zyx.shape[::-1], dtype=int)
    clipped_lower = np.maximum(lower_xyz, 0)
    clipped_upper = np.minimum(upper_xyz, shape_xyz)
    requested = np.maximum(upper_xyz - lower_xyz, 1)
    retained = np.maximum(clipped_upper - clipped_lower, 0)
    coverage = float(np.prod(retained) / np.prod(requested))
    if np.any(retained <= 0) or coverage < 0.95:
        return None, coverage

    x = np.arange(clipped_lower[0], clipped_upper[0], dtype=np.float32)
    y = np.arange(clipped_lower[1], clipped_upper[1], dtype=np.float32)
    z = np.arange(clipped_lower[2], clipped_upper[2], dtype=np.float32)
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    dx = xx - endpoint0_xyz[0]
    dy = yy - endpoint0_xyz[1]
    dz = zz - endpoint0_xyz[2]
    axial = dx * direction[0] + dy * direction[1] + dz * direction[2]
    radial_squared = dx * dx + dy * dy + dz * dz - axial * axial
    corridor = (
        (axial >= -1.0)
        & (axial <= length + 1.0)
        & (radial_squared <= corridor_radius_voxels ** 2)
    )
    crop = volume_zyx[
        clipped_lower[2] : clipped_upper[2],
        clipped_lower[1] : clipped_upper[1],
        clipped_lower[0] : clipped_upper[0],
    ]
    material = np.asarray(crop >= threshold) & corridor
    if not np.any(material):
        return False, coverage
    labels, _ = ndimage.label(material, structure=np.ones((3, 3, 3), dtype=np.uint8))
    band = max(2.0, min(5.0, 0.10 * length))
    first_labels = set(np.unique(labels[(axial <= band) & material]).tolist()) - {0}
    second_labels = set(np.unique(labels[(axial >= length - band) & material]).tolist()) - {0}
    return bool(first_labels & second_labels), coverage


def compare_strut_local(
    ct_volume_zyx: np.ndarray,
    endpoint0_xyz: Sequence[float],
    endpoint1_xyz: Sequence[float],
    stl_surface_points_xyz: np.ndarray,
    *,
    thresholds: Sequence[float] = (38557.0, 40054.0, 41018.0),
    central_threshold: float | None = None,
    distance_tolerance_voxels: float = 2.0,
    endpoint_exclusion_fraction: float = 0.10,
    axial_step_voxels: float = 1.0,
    minimum_supported_bin_fraction: float = 0.20,
    minimum_gap_voxels: int = 3,
    minimum_realized_fraction: float = 0.80,
    minimum_perturbation_agreement: float = 0.80,
    minimum_local_contrast_fraction: float | None = 0.25,
    expected_presence_low: float = 0.20,
    expected_presence_high: float = 0.80,
    expected_present_override: bool | None = None,
    expected_radius_voxels: float | None = None,
    stl_surface_distances_voxels: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Compare one transformed STL strut surface directly with native CT voxels.

    The surface points must already be selected from the STL triangles near the
    target registered edge.  The returned mapping contains the exact evidence
    fields appended to a source strut JSON record by the full pipeline.
    """

    volume = _validate_volume(ct_volume_zyx)
    threshold_values = tuple(float(value) for value in thresholds)
    if (
        not threshold_values
        or not all(np.isfinite(threshold_values))
        or any(second <= first for first, second in zip(threshold_values, threshold_values[1:]))
    ):
        raise StrutComparisonError("thresholds must be finite, unique, and strictly increasing")
    if central_threshold is None:
        central_threshold_value = threshold_values[len(threshold_values) // 2]
    else:
        central_threshold_value = float(central_threshold)
        if not np.isfinite(central_threshold_value):
            raise StrutComparisonError("central_threshold must be finite")
        if central_threshold_value not in threshold_values:
            raise StrutComparisonError("central_threshold must be one of thresholds")
    if not (np.isfinite(distance_tolerance_voxels) and distance_tolerance_voxels >= 0.0):
        raise StrutComparisonError("distance_tolerance_voxels must be nonnegative")
    if not (0.0 < minimum_supported_bin_fraction <= 1.0):
        raise StrutComparisonError("minimum_supported_bin_fraction must lie in (0, 1]")
    if not (0.0 <= expected_presence_low < expected_presence_high <= 1.0):
        raise StrutComparisonError("expected-presence bounds must satisfy 0 <= low < high <= 1")
    if minimum_local_contrast_fraction is not None and not (
        np.isfinite(minimum_local_contrast_fraction)
        and 0.0 < minimum_local_contrast_fraction <= 1.0
    ):
        raise StrutComparisonError(
            "minimum_local_contrast_fraction must be None or lie in (0, 1]"
        )
    if expected_present_override is not None and not isinstance(
        expected_present_override, (bool, np.bool_)
    ):
        raise StrutComparisonError("expected_present_override must be Boolean or None")
    if expected_radius_voxels is not None and not (
        np.isfinite(expected_radius_voxels) and expected_radius_voxels > 0.0
    ):
        raise StrutComparisonError("expected_radius_voxels must be positive")

    raw_surface_points = np.asarray(stl_surface_points_xyz, dtype=np.float64)
    supplied_surface_distances: np.ndarray | None = None
    if stl_surface_distances_voxels is not None:
        supplied_surface_distances = np.asarray(
            stl_surface_distances_voxels, dtype=np.float64
        )
        if (
            supplied_surface_distances.ndim != 1
            or supplied_surface_distances.shape[0] != raw_surface_points.shape[0]
            or not np.isfinite(supplied_surface_distances).all()
            or np.any(supplied_surface_distances < 0.0)
        ):
            raise StrutComparisonError(
                "stl_surface_distances_voxels must be finite, nonnegative, and match points"
            )

    first, direction, length, start, stop, bins = _axial_geometry(
        endpoint0_xyz, endpoint1_xyz, endpoint_exclusion_fraction, axial_step_voxels
    )
    second = _xyz(endpoint1_xyz, "endpoint1_xyz")
    points, bin_indices, expected_counts = _surface_bins(
        stl_surface_points_xyz, first, direction, start, stop, bins
    )
    sampled_expected = expected_counts > 0
    measured_axial_fraction = float(np.mean(sampled_expected))
    stl_expected_axial_fraction = (
        1.0 if expected_present_override is True else measured_axial_fraction
    )
    if expected_present_override is False or (
        expected_present_override is None
        and stl_expected_axial_fraction <= expected_presence_low
    ):
        result = evaluate_strut_profiles(
            np.ones(bins, dtype=bool), np.zeros(bins, dtype=bool), expected_present=False
        )
        result.update({
            "stl_expected_present": False,
            "stl_expectation_valid": True,
            "stl_expected_axial_fraction": stl_expected_axial_fraction,
            "stl_surface_sample_count": int(len(points)),
            "stl_to_ct_near_fraction": None,
            "ct_to_stl_near_fraction": None,
            "axial_bin_count": bins,
            "thresholds": list(threshold_values),
        })
        return result
    if (
        expected_present_override is None
        and stl_expected_axial_fraction < expected_presence_high
    ):
        return {
            "comparison_applicable": True,
            "comparison_valid": False,
            "stl_expected_present": None,
            "stl_expectation_valid": False,
            "has_error": None,
            "review_required": True,
            "confidence": 0.0,
            "decision_reason": "ambiguous_stl_strut_coverage",
            "stl_expected_axial_fraction": stl_expected_axial_fraction,
            "stl_surface_sample_count": int(len(points)),
            "stl_to_ct_near_fraction": None,
            "ct_to_stl_near_fraction": None,
            "axial_bin_count": bins,
            "thresholds": list(threshold_values),
        }

    expected_profile = np.ones(bins, dtype=bool)
    radial = np.linalg.norm(
        (points - first)
        - (((points - first) @ direction)[:, None] * direction[None, :]),
        axis=1,
    )
    measured_surface_radius = (
        float(np.median(supplied_surface_distances))
        if supplied_surface_distances is not None and supplied_surface_distances.size
        else (float(np.median(radial)) if radial.size else float("nan"))
    )
    decision_radius = (
        float(expected_radius_voxels)
        if expected_radius_voxels is not None
        else measured_surface_radius
    )
    if not (np.isfinite(decision_radius) and decision_radius >= 0.0):
        raise StrutComparisonError("could not determine a nonnegative STL radius")
    sampling_radius = max(
        0.1, min(10.0, decision_radius + distance_tolerance_voxels)
    )
    corridor_radius = max(3.0, sampling_radius)

    shifts = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
    )
    decisions: list[bool | None] = []
    profile_records: dict[
        tuple[float, tuple[float, float, float]],
        tuple[np.ndarray, np.ndarray, np.ndarray, float],
    ] = {}
    expected_disk_area = max(1.0, math.pi * decision_radius ** 2)
    minimum_material_samples = max(
        1, int(math.ceil(minimum_supported_bin_fraction * expected_disk_area))
    )
    central_surface_fraction: float | None = None
    for shift in shifts:
        cross_values, cross_observable, _ = _cross_section_intensities(
            volume,
            first,
            direction,
            start,
            stop,
            bins,
            radius_voxels=sampling_radius,
            shift_xyz=shift,
        )
        if cross_observable.size and float(np.mean(np.any(cross_observable, axis=1))) < 0.95:
            decisions.extend([None] * len(threshold_values))
            continue
        surface_maxima: np.ndarray | None = None
        if shift == shifts[0]:
            surface_maxima, surface_observable = _maximum_nearby_intensity(
                volume, points, distance_tolerance_voxels, shift
            )
            if surface_observable.size and float(np.mean(surface_observable)) < 0.95:
                surface_maxima = None
        for threshold in threshold_values:
            material_counts = np.count_nonzero(cross_values >= threshold, axis=1)
            realized = material_counts >= minimum_material_samples
            fractions = material_counts.astype(np.float64) / expected_disk_area
            if surface_maxima is None or surface_maxima.size == 0:
                point_fraction = float("nan")
            else:
                point_fraction = float(np.mean(surface_maxima >= threshold))
                if threshold == central_threshold_value and np.isfinite(point_fraction):
                    central_surface_fraction = point_fraction
            bounded_fractions = np.minimum(fractions, 1.0)
            profile_records[(threshold, shift)] = (
                realized, bounded_fractions, fractions, point_fraction
            )
            provisional = evaluate_strut_profiles(
                expected_profile,
                realized,
                minimum_gap_voxels=minimum_gap_voxels,
                minimum_realized_fraction=minimum_realized_fraction,
                # Connectivity is evaluated once at the central threshold.
                # Perturbation trials measure the stability of axial material
                # support and therefore cannot become null solely from a
                # threshold-fragile one-voxel bridge.
                bridge_connected=True,
                perturbation_agreement=1.0,
                minimum_perturbation_agreement=minimum_perturbation_agreement,
                expected_present=True,
            )
            decisions.append(provisional["has_error"])

    central_key = (central_threshold_value, shifts[0])
    if central_key not in profile_records or not decisions:
        return {
            "comparison_applicable": True,
            "comparison_valid": False,
            "stl_expected_present": True,
            "stl_expectation_valid": True,
            "has_error": None,
            "review_required": True,
            "confidence": 0.0,
            "decision_reason": "insufficient_ct_coverage",
            "stl_expected_axial_fraction": stl_expected_axial_fraction,
            "stl_surface_sample_count": int(len(points)),
            "stl_to_ct_near_fraction": None,
            "ct_to_stl_near_fraction": None,
            "axial_bin_count": bins,
            "thresholds": list(threshold_values),
        }

    central_profile, central_fractions, central_area_ratios, _ = profile_records[central_key]
    central_bridge, crop_coverage = _bridge_connected_26(
        volume,
        first,
        second,
        threshold=central_threshold_value,
        corridor_radius_voxels=corridor_radius,
    )
    central_provisional = evaluate_strut_profiles(
        expected_profile,
        central_profile,
        minimum_gap_voxels=minimum_gap_voxels,
        minimum_realized_fraction=minimum_realized_fraction,
        bridge_connected=central_bridge,
        perturbation_agreement=1.0,
        minimum_perturbation_agreement=minimum_perturbation_agreement,
        expected_present=True,
    )
    central_boolean = central_provisional["has_error"]
    valid_trial_fraction = float(
        np.mean([decision is not None for decision in decisions])
    )
    if central_boolean is None:
        agreement = 0.0
        result = dict(central_provisional)
        result["perturbation_agreement"] = agreement
        result["confidence"] = 0.0
    else:
        agreement = float(np.mean([
            decision is not None and bool(decision) is bool(central_boolean)
            for decision in decisions
        ]))
        result = evaluate_strut_profiles(
            expected_profile,
            central_profile,
            minimum_gap_voxels=minimum_gap_voxels,
            minimum_realized_fraction=minimum_realized_fraction,
            bridge_connected=central_bridge,
            perturbation_agreement=agreement,
            minimum_perturbation_agreement=minimum_perturbation_agreement,
            expected_present=True,
        )

    contrast_evidence: dict[str, Any] = {
        "contrast_method": (
            "disabled" if minimum_local_contrast_fraction is None
            else "not_run_absolute_result_not_error"
        ),
        "contrast_review_authorized": False,
        "contrast_decision_reason": "not_evaluated",
        "contrast_valid_shift_count": 0,
        "contrast_pass_shift_count": 0,
        "contrast_required_pass_count": 0,
        "contrast_shift_agreement": None,
        "contrast_shift_trials": [],
        "contrast_parameters": None,
        "local_contrast_realized_fraction": None,
        "local_contrast_profile": [],
        "support_intensity_profile": [],
        "local_background_median_profile": [],
        "local_background_noise_profile": [],
        "adaptive_lower_threshold_profile": [],
        "local_contrast_fraction_profile": [],
        "annulus_valid_profile": [],
        "annulus_contamination_fraction_profile": [],
        "contrast_low_path_connected_26": None,
        "contrast_annulus_valid_fraction": None,
        "contrast_longest_unsupported_gap_voxels": None,
    }
    if result.get("has_error") is True and minimum_local_contrast_fraction is not None:
        contrast_evidence = evaluate_annular_hysteresis_contrast(
            volume,
            first,
            direction,
            start,
            stop,
            bins,
            expected_radius_voxels=decision_radius,
            central_threshold=central_threshold_value,
            threshold_span=max(threshold_values) - min(threshold_values),
            minimum_local_contrast_fraction=minimum_local_contrast_fraction,
            minimum_supported_bin_fraction=minimum_supported_bin_fraction,
            minimum_realized_fraction=minimum_realized_fraction,
            minimum_gap_voxels=minimum_gap_voxels,
            minimum_perturbation_agreement=minimum_perturbation_agreement,
        )
        # Adaptive evidence is a veto against false certainty, not an alternate
        # segmentation. It may downgrade error to review, never to healthy.
        if contrast_evidence.get("contrast_review_authorized") is True:
            result["absolute_threshold_has_error"] = True
            result["absolute_threshold_decision_reason"] = result.get("decision_reason")
            result["has_error"] = None
            result["comparison_valid"] = False
            result["review_required"] = True
            result["confidence"] = 0.0
            result["decision_reason"] = "subthreshold_connected_annular_contrast"
    result.update(contrast_evidence)
    result.update({
        "stl_expected_present": True,
        "stl_expectation_valid": True,
        "stl_expected_axial_fraction": stl_expected_axial_fraction,
        "stl_surface_sample_count": int(len(points)),
        "stl_to_ct_near_fraction": central_surface_fraction,
        "representative_stl_surface_support_fraction": central_surface_fraction,
        "ct_to_stl_near_fraction": None,
        "axial_bin_count": bins,
        "central_threshold": central_threshold_value,
        "thresholds": list(threshold_values),
        "corridor_radius_voxels": corridor_radius,
        "cross_section_sampling_radius_voxels": sampling_radius,
        "stl_surface_radius_voxels": (
            None if not np.isfinite(measured_surface_radius)
            else measured_surface_radius
        ),
        "expected_radius_voxels": decision_radius,
        "minimum_material_samples_per_bin": minimum_material_samples,
        "ct_crop_coverage": float(crop_coverage),
        "valid_perturbation_trial_fraction": valid_trial_fraction,
        "minimum_local_contrast_fraction": minimum_local_contrast_fraction,
        "realized_profile": central_profile.astype(np.uint8).tolist(),
        "realized_bin_support_fraction": [
            None if not np.isfinite(value) else float(value) for value in central_fractions
        ],
        "realized_bin_material_area_ratio": [
            None if not np.isfinite(value) else float(value)
            for value in central_area_ratios
        ],
    })
    return result


__all__ = [
    "StrutComparisonError",
    "compare_strut_local",
    "evaluate_strut_profiles",
]
