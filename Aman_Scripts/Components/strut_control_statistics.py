"""Reusable statistics and frozen gates for CAD-only strut controls."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Mapping, Sequence

import numpy as np


DEFAULT_GATES: dict[str, float] = {
    "roc_auc_lower_bound_min": 0.90,
    "decidable_positive_sensitivity_min": 0.90,
    "decidable_negative_stable_rate_min": 0.90,
    "positive_review_rate_max": 0.10,
    "negative_review_rate_max": 0.10,
    "conservative_positive_capture_min": 0.80,
    "conservative_negative_stable_rate_min": 0.80,
    "matched_pair_win_lower_bound_min": 0.85,
    "powered_stratum_conservative_positive_sensitivity_min": 0.75,
}
STRATIFICATION_DIMENSIONS = (
    "orientation", "boundary", "x_tertile", "y_tertile", "z_tertile",
)


class StrutControlValidationError(ValueError):
    """Raised when a control manifest, result, or statistic is invalid."""


def _positive_number(value: float, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number <= 0:
        raise StrutControlValidationError(f"{name} must be finite and positive")
    return number


def raw_anomaly_score(
    evidence: Mapping[str, Any], *, minimum_realized_fraction: float = 0.80,
    minimum_gap_voxels: int = 3,
) -> float | None:
    """Return the continuous score aligned with the detector's OR boundary."""

    if not 0.0 < float(minimum_realized_fraction) < 1.0:
        raise StrutControlValidationError("minimum_realized_fraction must lie in (0, 1)")
    if not isinstance(minimum_gap_voxels, int) or minimum_gap_voxels < 1:
        raise StrutControlValidationError("minimum_gap_voxels must be positive")
    realized = evidence.get("realized_axial_fraction")
    gap = evidence.get("longest_unrealized_gap_voxels")
    if realized is None or gap is None:
        return None
    realized_value, gap_value = float(realized), float(gap)
    if not np.isfinite(realized_value) or not 0.0 <= realized_value <= 1.0:
        raise StrutControlValidationError("realized_axial_fraction must lie in [0, 1]")
    if not np.isfinite(gap_value) or gap_value < 0.0:
        raise StrutControlValidationError("longest_unrealized_gap_voxels must be nonnegative")
    return float(max(
        (1.0 - realized_value) / (1.0 - minimum_realized_fraction),
        gap_value / minimum_gap_voxels,
    ))


def tie_aware_auc(
    positive_scores: Sequence[float], negative_scores: Sequence[float]
) -> float:
    """Return ROC AUC as the probability a positive outranks a negative."""

    positive = np.asarray(positive_scores, dtype=np.float64)
    negative = np.asarray(negative_scores, dtype=np.float64)
    if positive.ndim != 1 or negative.ndim != 1 or not len(positive) or not len(negative):
        raise StrutControlValidationError("AUC needs nonempty one-dimensional classes")
    if not np.isfinite(positive).all() or not np.isfinite(negative).all():
        raise StrutControlValidationError("AUC scores must be finite")
    differences = positive[:, None] - negative[None, :]
    wins = np.count_nonzero(differences > 0.0)
    ties = np.count_nonzero(differences == 0.0)
    return float((wins + 0.5 * ties) / differences.size)


def auc_bounds(
    positive_scores: Sequence[float | None], negative_scores: Sequence[float | None]
) -> dict[str, Any]:
    """Return complete-case AUC and worst/best bounds for unavailable scores."""

    positive_all, negative_all = list(positive_scores), list(negative_scores)
    if not positive_all or not negative_all:
        raise StrutControlValidationError("AUC bounds need both control classes")
    positive = [float(item) for item in positive_all if item is not None]
    negative = [float(item) for item in negative_all if item is not None]
    if not all(np.isfinite(item) for item in positive + negative):
        raise StrutControlValidationError("available AUC scores must be finite")
    known_pairs = len(positive) * len(negative)
    total_pairs = len(positive_all) * len(negative_all)
    complete_auc = tie_aware_auc(positive, negative) if known_pairs else None
    known_wins = 0.0 if complete_auc is None else complete_auc * known_pairs
    unknown_pairs = total_pairs - known_pairs
    return {
        "complete_case_auc": complete_auc,
        "lower_bound": float(known_wins / total_pairs),
        "upper_bound": float((known_wins + unknown_pairs) / total_pairs),
        "known_pair_count": known_pairs,
        "total_pair_count": total_pairs,
    }


def matched_pair_win_bounds(
    positive_scores: Sequence[float | None], negative_scores: Sequence[float | None]
) -> dict[str, Any]:
    """Score aligned positive/negative matches, with bounds for missing scores."""

    positive, negative = list(positive_scores), list(negative_scores)
    if not positive or len(positive) != len(negative):
        raise StrutControlValidationError(
            "matched-pair bounds need equally sized, nonempty score vectors"
        )
    known_wins, known_pairs = 0.0, 0
    for positive_score, negative_score in zip(positive, negative):
        if positive_score is None or negative_score is None:
            continue
        first, second = float(positive_score), float(negative_score)
        if not np.isfinite(first) or not np.isfinite(second):
            raise StrutControlValidationError("available matched-pair scores must be finite")
        known_pairs += 1
        known_wins += 1.0 if first > second else 0.5 if first == second else 0.0
    total_pairs = len(positive)
    return {
        "complete_case_win_fraction": (
            None if known_pairs == 0 else float(known_wins / known_pairs)
        ),
        "lower_bound": float(known_wins / total_pairs),
        "upper_bound": float((known_wins + total_pairs - known_pairs) / total_pairs),
        "known_pair_count": known_pairs,
        "total_pair_count": total_pairs,
    }


def wilson_interval(
    successes: int, total: int, *, z: float = 1.959963984540054
) -> tuple[float, float] | None:
    """Return the two-sided Wilson score interval, or ``None`` for no trials."""

    if not isinstance(successes, int) or not isinstance(total, int):
        raise StrutControlValidationError("Wilson counts must be integers")
    if total < 0 or successes < 0 or successes > total:
        raise StrutControlValidationError("Wilson counts are inconsistent")
    z = _positive_number(z, "z")
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    ) / denominator
    return float(center - half), float(center + half)


def decision(value: Any) -> bool | None:
    """Normalize one ternary detector decision."""

    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    raise StrutControlValidationError("has_error must be Boolean or null")


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else float(numerator / denominator)


def population_metrics(
    rows: Sequence[Mapping[str, Any]], *, positive: bool
) -> dict[str, Any]:
    """Summarize ternary outcomes for one positive or negative population."""

    decisions = [decision(item["has_error"]) for item in rows]
    expected, contrary = (True, False) if positive else (False, True)
    successes = sum(item is expected for item in decisions)
    contradictions = sum(item is contrary for item in decisions)
    review = sum(item is None for item in decisions)
    decidable = successes + contradictions
    return {
        "total": len(rows),
        "success_count": successes,
        "contradiction_count": contradictions,
        "review_count": review,
        "decidable_rate": _ratio(decidable, len(rows)),
        "success_rate_decidable": _ratio(successes, decidable),
        "success_rate_conservative": _ratio(successes, len(rows)),
        "review_rate": _ratio(review, len(rows)),
        "success_rate_decidable_wilson_95": wilson_interval(successes, decidable),
        "success_rate_conservative_wilson_95": wilson_interval(successes, len(rows)),
    }


def _stratum_value(row: Mapping[str, Any], dimension: str) -> str:
    if dimension == "orientation":
        return str(row["orientation_key"])
    if dimension == "boundary":
        return str(row["boundary_class"])
    axis = {"x_tertile": 0, "y_tertile": 1, "z_tertile": 2}[dimension]
    return str(row["axis_tertiles_xyz"][axis])


def stratified_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report positive/negative outcomes and AUC for all frozen strata."""

    output: dict[str, Any] = {}
    for dimension in STRATIFICATION_DIMENSIONS:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[_stratum_value(row, dimension)].append(row)
        summaries = {}
        for name, group in sorted(groups.items()):
            positive = [item for item in group if item["control_label"] == 1]
            negative = [item for item in group if item["control_label"] == 0]
            summaries[name] = {
                "positive": population_metrics(positive, positive=True),
                "negative": population_metrics(negative, positive=False),
                "auc": auc_bounds(
                    [item["raw_anomaly_score"] for item in positive],
                    [item["raw_anomaly_score"] for item in negative],
                ) if positive and negative else None,
            }
        output[dimension] = summaries
    return output


def powered_stratum_gate(
    rows: Sequence[Mapping[str, Any]], *, threshold: float = 0.75,
    minimum_positive_controls: int = 10,
) -> dict[str, Any]:
    """Gate conservative positive sensitivity in every sufficiently large stratum."""

    threshold = float(threshold)
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise StrutControlValidationError("powered-stratum threshold must lie in [0, 1]")
    if (isinstance(minimum_positive_controls, bool)
            or not isinstance(minimum_positive_controls, int)
            or minimum_positive_controls < 1):
        raise StrutControlValidationError("minimum powered-stratum count must be positive")
    positives = [item for item in rows if item["control_label"] == 1]
    reports = []
    for dimension in STRATIFICATION_DIMENSIONS:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in positives:
            groups[_stratum_value(row, dimension)].append(row)
        for name, group in sorted(groups.items()):
            metrics = population_metrics(group, positive=True)
            sensitivity = float(metrics["success_rate_conservative"])
            powered = len(group) >= minimum_positive_controls
            passed_threshold = sensitivity >= threshold
            reports.append({
                "dimension": dimension,
                "stratum": name,
                "positive_control_count": len(group),
                "success_count": metrics["success_count"],
                "contradiction_count": metrics["contradiction_count"],
                "review_count": metrics["review_count"],
                "conservative_positive_sensitivity": sensitivity,
                "powered": powered,
                "passed_threshold": passed_threshold,
                "controls_overall": powered,
                "controlling_pass": passed_threshold if powered else None,
            })
    powered_reports = [item for item in reports if item["powered"]]
    return {
        "threshold": threshold,
        "minimum_positive_controls": minimum_positive_controls,
        "reported_group_count": len(reports),
        "powered_group_count": len(powered_reports),
        "underpowered_group_count": len(reports) - len(powered_reports),
        "worst_powered_sensitivity": min(
            (item["conservative_positive_sensitivity"] for item in powered_reports),
            default=1.0,
        ),
        "passed": all(item["passed_threshold"] for item in powered_reports),
        "groups": reports,
    }
