"""Conservative lower-intensity continuity evidence for one expected strut.

This module is intentionally separate from the absolute-threshold comparator.
It may authorize only an ``error -> review`` downgrade when a noise-significant
26-connected material path survives in a guarded target tube.  It never emits
a healthy classification.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


DEFAULT_SHIFTS_XYZ: tuple[tuple[float, float, float], ...] = (
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, -1.0),
)


class LocalContrastError(ValueError):
    """Raised when adaptive local-contrast geometry is invalid."""


def _finite_xyz(value: Sequence[float], name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise LocalContrastError(f"{name} must contain three finite XYZ values")
    return result


def _longest_false_run(profile: np.ndarray) -> int:
    missing = ~np.asarray(profile, dtype=bool)
    padded = np.concatenate(([False], missing, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    if changes.size == 0:
        return 0
    return int(np.max(changes[1::2] - changes[::2], initial=0))


def _nullable_profile(values: np.ndarray) -> list[float | None]:
    return [None if not np.isfinite(value) else float(value) for value in values]


def _dtype_quantum(volume: np.ndarray, threshold: float) -> float:
    dtype = np.dtype(volume.dtype)
    if dtype.kind in "ui":
        return 1.0
    if dtype.kind == "f":
        return float(np.finfo(dtype).eps * max(1.0, abs(threshold)))
    raise LocalContrastError(f"volume must be numeric, got {dtype}")


def _trial(
    volume_zyx: np.ndarray,
    first_xyz: np.ndarray,
    direction_xyz: np.ndarray,
    start: float,
    stop: float,
    bins: int,
    *,
    shift_xyz: Sequence[float],
    expected_radius_voxels: float,
    central_threshold: float,
    threshold_span: float,
    minimum_local_contrast_fraction: float,
    minimum_supported_bin_fraction: float,
    minimum_realized_fraction: float,
    minimum_gap_voxels: int,
    core_margin_voxels: float,
    background_guard_voxels: float,
    minimum_annulus_samples: int,
    maximum_annulus_high_fraction: float,
    noise_multiplier: float,
    noise_floor_span_fraction: float,
) -> dict[str, Any]:
    """Evaluate one shifted core tube and its guarded annulus."""

    from scipy import ndimage

    shift = _finite_xyz(shift_xyz, "shift_xyz")
    shifted_first = first_xyz + shift
    core_radius = expected_radius_voxels + core_margin_voxels
    annulus_inner = expected_radius_voxels + background_guard_voxels
    annulus_outer = annulus_inner + max(2.0, expected_radius_voxels)
    body_first = shifted_first + start * direction_xyz
    body_last = shifted_first + stop * direction_xyz
    crop_padding = annulus_outer + 1.0
    lower_xyz = np.floor(np.minimum(body_first, body_last) - crop_padding).astype(np.int64)
    upper_xyz = np.ceil(np.maximum(body_first, body_last) + crop_padding).astype(np.int64) + 1
    shape_xyz = np.asarray(volume_zyx.shape[::-1], dtype=np.int64)
    clipped_lower = np.maximum(lower_xyz, 0)
    clipped_upper = np.minimum(upper_xyz, shape_xyz)
    requested = np.maximum(upper_xyz - lower_xyz, 1)
    retained = np.maximum(clipped_upper - clipped_lower, 0)
    crop_coverage = float(np.prod(retained) / np.prod(requested))
    if np.any(retained <= 0) or crop_coverage < 0.95:
        return {
            "valid": False,
            "passed": False,
            "reason": "contrast_crop_out_of_bounds",
            "crop_coverage": crop_coverage,
            "annulus_valid_fraction": 0.0,
            "shift_xyz": shift.tolist(),
        }

    x = np.arange(clipped_lower[0], clipped_upper[0], dtype=np.float32)
    y = np.arange(clipped_lower[1], clipped_upper[1], dtype=np.float32)
    z = np.arange(clipped_lower[2], clipped_upper[2], dtype=np.float32)
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    dx = xx - shifted_first[0]
    dy = yy - shifted_first[1]
    dz = zz - shifted_first[2]
    axial = dx * direction_xyz[0] + dy * direction_xyz[1] + dz * direction_xyz[2]
    radial_squared = dx * dx + dy * dy + dz * dz - axial * axial
    body = (axial >= start) & (axial <= stop)
    body_span = max(stop - start, np.finfo(np.float64).eps)
    bin_index = np.floor((axial - start) * bins / body_span).astype(np.int32)
    bin_index = np.clip(bin_index, 0, bins - 1)
    core = body & (radial_squared <= core_radius ** 2)
    annulus = (
        body
        & (radial_squared >= annulus_inner ** 2)
        & (radial_squared <= annulus_outer ** 2)
    )
    crop = np.asarray(
        volume_zyx[
            clipped_lower[2] : clipped_upper[2],
            clipped_lower[1] : clipped_upper[1],
            clipped_lower[0] : clipped_upper[0],
        ],
        dtype=np.float64,
    )

    background = np.full(bins, np.nan, dtype=np.float64)
    raw_sigma = np.full(bins, np.nan, dtype=np.float64)
    contamination = np.full(bins, np.nan, dtype=np.float64)
    support_intensity = np.full(bins, np.nan, dtype=np.float64)
    annulus_valid = np.zeros(bins, dtype=bool)
    minimum_material_samples = max(
        2,
        int(math.ceil(minimum_supported_bin_fraction * math.pi * expected_radius_voxels ** 2)),
    )
    for axial_bin in range(bins):
        annulus_values = crop[annulus & (bin_index == axial_bin)]
        if annulus_values.size >= minimum_annulus_samples:
            median = float(np.median(annulus_values))
            background[axial_bin] = median
            raw_sigma[axial_bin] = float(
                1.4826 * np.median(np.abs(annulus_values - median))
            )
            contamination[axial_bin] = float(
                np.mean(annulus_values >= central_threshold)
            )
            annulus_valid[axial_bin] = bool(
                contamination[axial_bin] <= maximum_annulus_high_fraction
                and median < central_threshold
            )
        core_values = crop[core & (bin_index == axial_bin)]
        if core_values.size >= minimum_material_samples:
            kth = core_values.size - minimum_material_samples
            support_intensity[axial_bin] = float(np.partition(core_values, kth)[kth])

    valid_fraction = float(np.mean(annulus_valid))
    preliminary_sigma = raw_sigma[annulus_valid & np.isfinite(raw_sigma)]
    pooled_sigma = (
        float(np.median(preliminary_sigma)) if preliminary_sigma.size else float("nan")
    )
    span = threshold_span if threshold_span > 0.0 else 0.10 * abs(central_threshold)
    sigma_floor = max(
        _dtype_quantum(volume_zyx, central_threshold),
        noise_floor_span_fraction * max(span, np.finfo(np.float64).eps),
    )
    effective_sigma = np.full(bins, np.nan, dtype=np.float64)
    lower_threshold = np.full(bins, np.nan, dtype=np.float64)
    contrast_fraction = np.full(bins, np.nan, dtype=np.float64)
    for axial_bin in np.flatnonzero(annulus_valid):
        candidates = [sigma_floor]
        if np.isfinite(raw_sigma[axial_bin]):
            candidates.append(float(raw_sigma[axial_bin]))
        if np.isfinite(pooled_sigma):
            candidates.append(pooled_sigma)
        effective_sigma[axial_bin] = max(candidates)
        threshold_gap = central_threshold - background[axial_bin]
        required = max(
            minimum_local_contrast_fraction * threshold_gap,
            noise_multiplier * effective_sigma[axial_bin],
        )
        candidate_threshold = background[axial_bin] + required
        if candidate_threshold < central_threshold:
            lower_threshold[axial_bin] = candidate_threshold
        if np.isfinite(support_intensity[axial_bin]) and threshold_gap > 0.0:
            contrast_fraction[axial_bin] = (
                support_intensity[axial_bin] - background[axial_bin]
            ) / threshold_gap

    usable_bins = annulus_valid & np.isfinite(lower_threshold)
    valid_fraction = float(np.mean(usable_bins))
    if valid_fraction < 0.95:
        return {
            "valid": False,
            "passed": False,
            "reason": "insufficient_uncontaminated_annulus",
            "crop_coverage": crop_coverage,
            "annulus_valid_fraction": valid_fraction,
            "shift_xyz": shift.tolist(),
            "minimum_material_samples_per_bin": minimum_material_samples,
            "annulus_valid_profile": usable_bins.astype(np.uint8).tolist(),
            "background_profile": _nullable_profile(background),
            "noise_sigma_profile": _nullable_profile(effective_sigma),
            "lower_threshold_profile": _nullable_profile(lower_threshold),
            "support_intensity_profile": _nullable_profile(support_intensity),
            "contrast_fraction_profile": _nullable_profile(contrast_fraction),
            "contamination_fraction_profile": _nullable_profile(contamination),
            "connected_support_profile": np.zeros(bins, dtype=np.uint8).tolist(),
            "connected_support_fraction": 0.0,
            "longest_unsupported_gap_voxels": bins,
            "low_path_connected_26": False,
        }

    voxel_threshold = lower_threshold[bin_index]
    low = core & usable_bins[bin_index] & (crop >= voxel_threshold)
    high = core & usable_bins[bin_index] & (crop >= central_threshold)
    labels, component_count = ndimage.label(
        low, structure=np.ones((3, 3, 3), dtype=np.uint8)
    )
    endpoint_band_bins = max(2, int(math.ceil(0.10 * bins)))
    seed_bin_requirement = max(3, int(math.ceil(0.10 * bins)))
    first_band = low & (bin_index < endpoint_band_bins)
    last_band = low & (bin_index >= bins - endpoint_band_bins)
    first_labels = set(np.unique(labels[first_band]).tolist()) - {0}
    last_labels = set(np.unique(labels[last_band]).tolist()) - {0}
    spanning_labels = sorted(first_labels & last_labels)

    best_profile = np.zeros(bins, dtype=bool)
    best_fraction = 0.0
    best_gap = bins
    best_score = (-1, -1, -1)
    path_connected = False
    passed = False
    candidate_labels = spanning_labels
    if not candidate_labels and component_count:
        label_ids, label_counts = np.unique(labels[labels > 0], return_counts=True)
        candidate_labels = [
            int(label_ids[index])
            for index in np.argsort(label_counts, kind="stable")[::-1][:8]
        ]
    for label_id in candidate_labels:
        component = labels == label_id
        component_bins = bin_index[component]
        counts = np.bincount(component_bins, minlength=bins)
        supported = counts >= minimum_material_samples
        supported_fraction = float(np.mean(supported))
        longest_gap = _longest_false_run(supported)
        high_seed_bins = int(np.unique(bin_index[component & high]).size)
        spans = label_id in spanning_labels
        seeded_path = spans and high_seed_bins >= seed_bin_requirement
        admissible = bool(
            seeded_path
            and supported_fraction >= minimum_realized_fraction
            and longest_gap < minimum_gap_voxels
        )
        score = (
            int(seeded_path),
            int(np.count_nonzero(supported)),
            int(np.count_nonzero(component)),
        )
        if score > best_score:
            best_score = score
            best_profile = supported
            best_fraction = supported_fraction
            best_gap = longest_gap
            path_connected = seeded_path
        passed = passed or admissible

    return {
        "valid": True,
        "passed": passed,
        "reason": (
            "annular_hysteresis_path_supported"
            if passed
            else "no_admissible_annular_hysteresis_path"
        ),
        "crop_coverage": crop_coverage,
        "annulus_valid_fraction": valid_fraction,
        "shift_xyz": shift.tolist(),
        "minimum_material_samples_per_bin": minimum_material_samples,
        "annulus_valid_profile": usable_bins.astype(np.uint8).tolist(),
        "background_profile": _nullable_profile(background),
        "noise_sigma_profile": _nullable_profile(effective_sigma),
        "lower_threshold_profile": _nullable_profile(lower_threshold),
        "support_intensity_profile": _nullable_profile(support_intensity),
        "contrast_fraction_profile": _nullable_profile(contrast_fraction),
        "contamination_fraction_profile": _nullable_profile(contamination),
        "connected_support_profile": best_profile.astype(np.uint8).tolist(),
        "connected_support_fraction": best_fraction,
        "longest_unsupported_gap_voxels": best_gap,
        "low_path_connected_26": path_connected,
    }


def evaluate_annular_hysteresis_contrast(
    volume_zyx: np.ndarray,
    first_xyz: Sequence[float],
    direction_xyz: Sequence[float],
    start: float,
    stop: float,
    bins: int,
    *,
    expected_radius_voxels: float,
    central_threshold: float,
    threshold_span: float,
    minimum_local_contrast_fraction: float,
    minimum_supported_bin_fraction: float = 0.20,
    minimum_realized_fraction: float = 0.80,
    minimum_gap_voxels: int = 3,
    minimum_perturbation_agreement: float = 0.80,
    core_margin_voxels: float = 0.75,
    background_guard_voxels: float = 2.0,
    minimum_annulus_samples: int = 24,
    maximum_annulus_high_fraction: float = 0.20,
    noise_multiplier: float = 5.0,
    noise_floor_span_fraction: float = 0.05,
    shifts_xyz: Sequence[Sequence[float]] = DEFAULT_SHIFTS_XYZ,
) -> dict[str, Any]:
    """Return auditable evidence for a possible error-to-review downgrade."""

    volume = np.asanyarray(volume_zyx)
    first = _finite_xyz(first_xyz, "first_xyz")
    direction = _finite_xyz(direction_xyz, "direction_xyz")
    norm = float(np.linalg.norm(direction))
    if volume.ndim != 3 or volume.dtype.kind not in "uibf":
        raise LocalContrastError("volume_zyx must be a numeric 3D array")
    if not np.isfinite(norm) or norm <= 0.0:
        raise LocalContrastError("direction_xyz must be nonzero")
    direction = direction / norm
    if not (np.isfinite(start) and np.isfinite(stop) and 0.0 <= start < stop):
        raise LocalContrastError("body start/stop must satisfy 0 <= start < stop")
    if bins < 1:
        raise LocalContrastError("bins must be positive")
    if not (
        np.isfinite(expected_radius_voxels) and expected_radius_voxels > 0.0
    ):
        raise LocalContrastError("expected_radius_voxels must be positive")
    if not np.isfinite(central_threshold):
        raise LocalContrastError("central_threshold must be finite")
    if not (
        np.isfinite(minimum_local_contrast_fraction)
        and 0.0 < minimum_local_contrast_fraction <= 1.0
    ):
        raise LocalContrastError("minimum_local_contrast_fraction must lie in (0, 1]")
    if minimum_annulus_samples < 1 or minimum_gap_voxels < 1:
        raise LocalContrastError("sample and gap counts must be positive")
    if not (0.0 < minimum_supported_bin_fraction <= 1.0):
        raise LocalContrastError("minimum_supported_bin_fraction must lie in (0, 1]")
    if not (0.0 <= minimum_realized_fraction <= 1.0):
        raise LocalContrastError("minimum_realized_fraction must lie in [0, 1]")
    if not (0.0 <= minimum_perturbation_agreement <= 1.0):
        raise LocalContrastError("minimum_perturbation_agreement must lie in [0, 1]")
    shifts = tuple(tuple(float(value) for value in shift) for shift in shifts_xyz)
    if not shifts or shifts[0] != (0.0, 0.0, 0.0):
        raise LocalContrastError("the first contrast shift must be the central (0,0,0) shift")

    trial_parameters = {
        "expected_radius_voxels": expected_radius_voxels,
        "central_threshold": central_threshold,
        "threshold_span": threshold_span,
        "minimum_local_contrast_fraction": minimum_local_contrast_fraction,
        "minimum_supported_bin_fraction": minimum_supported_bin_fraction,
        "minimum_realized_fraction": minimum_realized_fraction,
        "minimum_gap_voxels": minimum_gap_voxels,
        "core_margin_voxels": core_margin_voxels,
        "background_guard_voxels": background_guard_voxels,
        "minimum_annulus_samples": minimum_annulus_samples,
        "maximum_annulus_high_fraction": maximum_annulus_high_fraction,
        "noise_multiplier": noise_multiplier,
        "noise_floor_span_fraction": noise_floor_span_fraction,
    }
    trials: list[dict[str, Any]] = []
    central = _trial(
        volume, first, direction, start, stop, bins,
        shift_xyz=shifts[0], **trial_parameters,
    )
    trials.append(central)
    if central.get("valid") is True and central.get("passed") is True:
        for shift in shifts[1:]:
            trials.append(
                _trial(
                    volume, first, direction, start, stop, bins,
                    shift_xyz=shift, **trial_parameters,
                )
            )

    valid_count = sum(trial.get("valid") is True for trial in trials)
    pass_count = sum(trial.get("passed") is True for trial in trials)
    required_passes = max(
        1,
        int(math.ceil(minimum_perturbation_agreement * len(shifts) - 1e-12)),
    )
    minimum_valid_shifts = min(len(shifts), max(1, required_passes))
    authorized = bool(
        central.get("valid") is True
        and central.get("passed") is True
        and valid_count >= minimum_valid_shifts
        and pass_count >= required_passes
    )
    shift_summaries = []
    for index, shift in enumerate(shifts):
        trial = trials[index] if index < len(trials) else None
        shift_summaries.append({
            "shift_xyz": list(shift),
            "valid": None if trial is None else trial.get("valid"),
            "passed": None if trial is None else trial.get("passed"),
            "reason": (
                "not_run_central_contrast_failed"
                if trial is None
                else trial.get("reason")
            ),
            "annulus_valid_fraction": (
                None if trial is None else trial.get("annulus_valid_fraction")
            ),
            "crop_coverage": None if trial is None else trial.get("crop_coverage"),
            "low_path_connected_26": (
                None if trial is None else trial.get("low_path_connected_26")
            ),
            "connected_support_fraction": (
                None if trial is None else trial.get("connected_support_fraction")
            ),
        })
    return {
        "contrast_method": "annular_hysteresis_v2",
        "contrast_review_authorized": authorized,
        "contrast_decision_reason": (
            "stable_annular_hysteresis_continuity"
            if authorized
            else central.get("reason", "contrast_evidence_not_authorized")
        ),
        "contrast_valid_shift_count": int(valid_count),
        "contrast_pass_shift_count": int(pass_count),
        "contrast_required_pass_count": int(required_passes),
        "contrast_shift_agreement": float(pass_count / len(shifts)),
        "contrast_shift_trials": shift_summaries,
        "contrast_parameters": {
            **trial_parameters,
            "minimum_perturbation_agreement": minimum_perturbation_agreement,
            "shift_count": len(shifts),
        },
        "local_contrast_realized_fraction": central.get("connected_support_fraction"),
        "local_contrast_profile": central.get(
            "connected_support_profile", np.zeros(bins, dtype=np.uint8).tolist()
        ),
        "support_intensity_profile": central.get(
            "support_intensity_profile", [None] * bins
        ),
        "local_background_median_profile": central.get(
            "background_profile", [None] * bins
        ),
        "local_background_noise_profile": central.get(
            "noise_sigma_profile", [None] * bins
        ),
        "adaptive_lower_threshold_profile": central.get(
            "lower_threshold_profile", [None] * bins
        ),
        "local_contrast_fraction_profile": central.get(
            "contrast_fraction_profile", [None] * bins
        ),
        "annulus_valid_profile": central.get(
            "annulus_valid_profile", np.zeros(bins, dtype=np.uint8).tolist()
        ),
        "annulus_contamination_fraction_profile": central.get(
            "contamination_fraction_profile", [None] * bins
        ),
        "contrast_low_path_connected_26": central.get("low_path_connected_26"),
        "contrast_annulus_valid_fraction": central.get("annulus_valid_fraction"),
        "contrast_longest_unsupported_gap_voxels": central.get(
            "longest_unsupported_gap_voxels"
        ),
    }


__all__ = [
    "DEFAULT_SHIFTS_XYZ",
    "LocalContrastError",
    "evaluate_annular_hysteresis_contrast",
]
