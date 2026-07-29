"""Per-strut segmentation, defect features, and conservative candidate rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt

from .alignment import neighborhood_offsets
from .colors import CANDIDATE_COLORS
from .geometry import line_points


DISPLAY_COLORS = dict(CANDIDATE_COLORS)
RULE_VERSION = "rules-v2-missing-0.10"
BASELINE_LABEL_SOURCE = "deterministic_rule_baseline"


@dataclass(frozen=True)
class RuleSettings:
    """Transparent provisional candidate rules for the unlabeled MVP."""

    missing_max_occupancy: float = 0.10
    broken_max_occupancy: float = 0.85
    broken_min_gap_fraction: float = 0.15
    maximum_alignment_error_vox: float = 3.0
    minimum_stability: float = 2.0 / 3.0


def longest_false_run(values: np.ndarray) -> int:
    """Return the longest consecutive false run in a boolean sequence."""

    longest = current = 0
    for value in np.asarray(values, dtype=bool):
        if value:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def longest_false_run_bounds(values: np.ndarray) -> tuple[int, int]:
    """Return half-open bounds for the longest consecutive false run."""

    best_start = best_end = current_start = 0
    in_gap = False
    for index, value in enumerate(np.asarray(values, dtype=bool)):
        if not value and not in_gap:
            current_start = index
            in_gap = True
        elif value and in_gap:
            if index - current_start > best_end - best_start:
                best_start, best_end = current_start, index
            in_gap = False
    if in_gap and len(values) - current_start > best_end - best_start:
        best_start, best_end = current_start, len(values)
    return best_start, best_end


def _roi_for_line(
    start: np.ndarray,
    end: np.ndarray,
    shape: tuple[int, int, int],
    padding: int,
) -> tuple[tuple[slice, slice, slice], np.ndarray]:
    lower = np.maximum(np.floor(np.minimum(start, end)).astype(int) - padding, 0)
    upper = np.minimum(
        np.ceil(np.maximum(start, end)).astype(int) + padding + 1,
        np.asarray(shape),
    )
    if np.any(upper <= lower):
        raise ValueError("Strut ROI falls outside the CT volume")
    slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper))
    return slices, lower


def _station_measurements(
    intensities: np.ndarray,
    distance_um: np.ndarray,
    local_points: np.ndarray,
    threshold: float,
    search_radius: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    integer_points = np.rint(local_points).astype(np.int64)
    offsets, offset_distances = neighborhood_offsets(search_radius)
    support = np.zeros(len(integer_points), dtype=bool)
    nearest = np.full(len(integer_points), np.inf, dtype=float)
    diameter = np.full(len(integer_points), np.nan, dtype=float)
    peak_intensity = np.zeros(len(integer_points), dtype=float)
    shape = np.asarray(intensities.shape)
    for index, point in enumerate(integer_points):
        candidates = point[None, :] + offsets
        valid = np.all((candidates >= 0) & (candidates < shape), axis=1)
        candidates = candidates[valid]
        distances = offset_distances[valid]
        values = np.asarray(
            intensities[candidates[:, 0], candidates[:, 1], candidates[:, 2]],
            dtype=float,
        )
        material = values >= threshold
        peak_intensity[index] = float(values.max(initial=0))
        if np.any(material):
            support[index] = True
            nearest[index] = float(distances[material].min())
            local_diameter = 2.0 * distance_um[
                candidates[material, 0],
                candidates[material, 1],
                candidates[material, 2],
            ]
            diameter[index] = float(np.max(local_diameter))
    return support, nearest, diameter, peak_intensity


def _single_threshold_features(
    roi: np.ndarray,
    local_points: np.ndarray,
    threshold: float,
    voxel_spacing_um: tuple[float, float, float],
    search_radius: int,
) -> dict[str, float]:
    mask = roi >= threshold
    distance_um = distance_transform_edt(mask, sampling=voxel_spacing_um)
    support, nearest, diameter, peak = _station_measurements(
        roi,
        distance_um,
        local_points,
        threshold,
        search_radius,
    )
    count = len(support)
    endpoint_count = max(1, int(np.ceil(0.1 * count)))
    central = slice(int(0.2 * count), max(int(0.8 * count), int(0.2 * count) + 1))
    central_diameter = diameter[central]
    finite_diameter = central_diameter[np.isfinite(central_diameter)]
    finite_nearest = nearest[np.isfinite(nearest)]
    gap_start, gap_end = longest_false_run_bounds(support)
    gap_center_fraction = (
        float(((gap_start + gap_end - 1) / 2) / max(count - 1, 1))
        if gap_end > gap_start
        else 0.5
    )
    return {
        "occupancy": float(support.mean()),
        "gap_fraction": float(longest_false_run(support) / max(count, 1)),
        "largest_gap_center_fraction": gap_center_fraction,
        "start_support": float(support[:endpoint_count].mean()),
        "end_support": float(support[-endpoint_count:].mean()),
        "alignment_error_vox": (
            float(np.median(finite_nearest)) if len(finite_nearest) else float("nan")
        ),
        "diameter_median_um": (
            float(np.median(finite_diameter)) if len(finite_diameter) else float("nan")
        ),
        "diameter_std_um": (
            float(np.std(finite_diameter, ddof=1)) if len(finite_diameter) > 1 else 0.0
        ),
        "diameter_q25_um": (
            float(np.quantile(finite_diameter, 0.25))
            if len(finite_diameter)
            else float("nan")
        ),
        "diameter_q75_um": (
            float(np.quantile(finite_diameter, 0.75))
            if len(finite_diameter)
            else float("nan")
        ),
        "peak_intensity_median": float(np.median(peak)),
        "station_count": int(count),
    }


def _coarse_state(features: dict[str, float], rules: RuleSettings) -> str:
    occupancy = features["occupancy"]
    gap = features["gap_fraction"]
    if occupancy <= rules.missing_max_occupancy:
        return "missing"
    if occupancy <= rules.broken_max_occupancy and gap >= rules.broken_min_gap_fraction:
        return "broken"
    return "intact"


def analyze_strut(
    volume: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    *,
    base_threshold: float,
    threshold_factors: tuple[float, ...],
    voxel_spacing_um: tuple[float, float, float],
    search_radius: int,
    rules: RuleSettings,
) -> dict[str, Any]:
    """Analyze one expected strut without allocating a full-volume mask."""

    started = perf_counter()
    padding = search_radius + 3
    slices, origin = _roi_for_line(start, end, volume.shape, padding)
    roi = np.asarray(volume[slices])
    points, _ = line_points(start, end, spacing_vox=0.5, trim_fraction=0.1)
    local_points = points - origin[None, :]
    by_threshold: list[tuple[float, dict[str, float], str]] = []
    for factor in threshold_factors:
        threshold = float(base_threshold * factor)
        features = _single_threshold_features(
            roi,
            local_points,
            threshold,
            voxel_spacing_um,
            search_radius,
        )
        by_threshold.append((factor, features, _coarse_state(features, rules)))

    baseline_index = int(np.argmin(np.abs(np.asarray(threshold_factors) - 1.0)))
    _, baseline, baseline_state = by_threshold[baseline_index]
    states = [item[2] for item in by_threshold]
    stability = float(sum(state == baseline_state for state in states) / len(states))
    diameter_values = [
        item[1]["diameter_median_um"]
        for item in by_threshold
        if np.isfinite(item[1]["diameter_median_um"])
    ]
    output: dict[str, Any] = dict(baseline)
    output.update(
        {
            "coarse_state": baseline_state,
            "threshold_stability": stability,
            "threshold_states": "|".join(states),
            "diameter_threshold_range_um": (
                float(max(diameter_values) - min(diameter_values))
                if diameter_values
                else float("nan")
            ),
            "runtime_seconds": float(perf_counter() - started),
        }
    )
    return output


def _thin_cutoff(
    table: pd.DataFrame,
    design_diameter_um: float,
) -> tuple[float, dict[str, float]]:
    eligible = table.loc[
        table["thickness_measurement_valid"]
        & (table["coarse_state"] == "intact")
        & np.isfinite(table["diameter_median_um"]),
        "diameter_median_um",
    ].to_numpy(float)
    if not len(eligible):
        return float("nan"), {
            "median_um": float("nan"),
            "robust_sigma_um": float("nan"),
            "lower_tail_quantile": float("nan"),
            "valid_measurement_count": 0,
        }
    median = float(np.median(eligible))
    mad = float(np.median(np.abs(eligible - median)))
    robust_sigma = 1.4826 * mad
    lower_tail = float(np.quantile(eligible, 0.1))
    cutoff = float(min(design_diameter_um, lower_tail))
    return cutoff, {
        "median_um": median,
        "robust_sigma_um": robust_sigma,
        "lower_tail_quantile": lower_tail,
        "valid_measurement_count": int(len(eligible)),
    }


def classify_candidates(
    table: pd.DataFrame,
    *,
    rules: RuleSettings,
    design_diameter_um: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Assign conservative candidate labels and uncalibrated confidence."""

    result = table.copy()
    result["thickness_measurement_valid"] = (
        (result["region"] == "interior")
        & (result["coarse_state"] == "intact")
        & np.isfinite(result["alignment_error_vox"])
        & (result["alignment_error_vox"] <= rules.maximum_alignment_error_vox)
        & np.isfinite(result["diameter_median_um"])
    )
    result["thickness_exclusion_reason"] = np.where(
        result["thickness_measurement_valid"],
        "",
        np.where(
            result["region"] != "interior",
            "exterior strut may be contaminated by solid skin/wall",
            np.where(
                result["coarse_state"] != "intact",
                "missing/broken support is not an intact thickness measurement",
                "alignment or diameter measurement is unreliable",
            ),
        ),
    )
    cutoff, thickness_reference = _thin_cutoff(result, design_diameter_um)
    predictions: list[str] = []
    confidences: list[float] = []
    reasons: list[str] = []
    for _, row in result.iterrows():
        state = str(row["coarse_state"])
        threshold_states = tuple(str(row["threshold_states"]).split("|"))
        all_thresholds_missing = bool(threshold_states) and all(
            item == "missing" for item in threshold_states
        )
        alignment = float(row["alignment_error_vox"])
        stability = float(row["threshold_stability"])
        diameter = float(row["diameter_median_um"])
        reason = f"occupancy={row['occupancy']:.3f}; gap={row['gap_fraction']:.3f}"

        if state == "missing" and all_thresholds_missing:
            prediction = "missing"
            reason += "; negligible material at all three tested thresholds"
        elif state == "missing":
            prediction = "uncertain"
            reason += "; missing-state evidence changes with threshold"
        elif state == "broken":
            prediction = "broken"
            reason += "; material support contains a long internal gap"
        elif not np.isfinite(alignment) or alignment > rules.maximum_alignment_error_vox:
            prediction = "uncertain"
            reason += "; centerline alignment is outside the reliable range"
        elif stability < rules.minimum_stability:
            prediction = "uncertain"
            reason += "; classification changes with threshold"
        elif (
            bool(row["thickness_measurement_valid"])
            and np.isfinite(cutoff)
            and diameter <= cutoff
            and diameter < design_diameter_um
        ):
            prediction = "thin"
            reason += (
                f"; valid interior diameter={diameter:.1f} µm is in the "
                f"sample's exploratory lower tail (≤{cutoff:.1f} µm)"
            )
        else:
            prediction = state

        if prediction == "missing":
            missing_margin = np.clip(
                (rules.missing_max_occupancy - float(row["occupancy"]))
                / max(rules.missing_max_occupancy, 1e-12),
                0.0,
                1.0,
            )
            confidence = 100.0 * (0.75 * stability + 0.25 * missing_margin)
        else:
            alignment_score = (
                float(np.exp(-alignment / 3.0)) if np.isfinite(alignment) else 0.0
            )
            confidence = 100.0 * (0.65 * stability + 0.35 * alignment_score)
        if prediction == "uncertain":
            confidence = min(confidence, 50.0)
        predictions.append(prediction)
        confidences.append(round(confidence, 1))
        reasons.append(reason)

    result["prediction"] = predictions
    # Stable teammate-integration field. `prediction` is retained for the
    # current dashboard while future detectors may replace `label` by strut_id.
    result["label"] = predictions
    result["confidence_percent_uncalibrated"] = confidences
    result["prediction_reason"] = reasons
    result["thin_candidate_cutoff_um"] = cutoff
    result["label_source"] = BASELINE_LABEL_SOURCE
    result["label_version"] = RULE_VERSION
    result["evidence_focus_zyx"] = result.apply(
        lambda row: json.dumps(
            [
                round(
                    float(row[f"start_{axis}"])
                    + (
                        float(row["largest_gap_center_fraction"])
                        if row["prediction"] == "broken"
                        else 0.5
                    )
                    * (float(row[f"end_{axis}"]) - float(row[f"start_{axis}"])),
                    4,
                )
                for axis in ("z", "y", "x")
            ],
            separators=(",", ":"),
        ),
        axis=1,
    )
    return result, {
        "thin_candidate_cutoff_um": cutoff,
        "eligible_thickness_median_um": thickness_reference["median_um"],
        "eligible_thickness_robust_sigma_um": thickness_reference["robust_sigma_um"],
        "eligible_thickness_lower_10pct_um": thickness_reference[
            "lower_tail_quantile"
        ],
        "valid_thickness_measurement_count": thickness_reference[
            "valid_measurement_count"
        ],
        "design_reference_um_unconfirmed": design_diameter_um,
    }


def analyze_sample(
    volume: np.ndarray,
    sample: pd.DataFrame,
    *,
    base_threshold: float,
    threshold_factors: tuple[float, ...],
    voxel_spacing_um: tuple[float, float, float],
    search_radius: int,
    design_diameter_um: float,
    rules: RuleSettings | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Analyze every sampled strut with deterministic provisional rules."""

    rules = rules or RuleSettings()
    records: list[dict[str, Any]] = []
    for _, row in sample.iterrows():
        start = row[["start_z", "start_y", "start_x"]].to_numpy(float)
        end = row[["end_z", "end_y", "end_x"]].to_numpy(float)
        records.append(
            analyze_strut(
                volume,
                start,
                end,
                base_threshold=base_threshold,
                threshold_factors=threshold_factors,
                voxel_spacing_um=voxel_spacing_um,
                search_radius=search_radius,
                rules=rules,
            )
        )
    features = pd.DataFrame.from_records(records)
    combined = pd.concat(
        [sample.reset_index(drop=True), features.reset_index(drop=True)],
        axis=1,
    )
    return classify_candidates(
        combined,
        rules=rules,
        design_diameter_um=design_diameter_um,
    )
