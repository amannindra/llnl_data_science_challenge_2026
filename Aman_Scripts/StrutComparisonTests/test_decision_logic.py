"""Adversarial tests for the pure STL/CT axial-profile decision policy."""

from __future__ import annotations

import numpy as np
import pytest

from Aman_Scripts.Components.strut_comparison import evaluate_strut_profiles


def evaluate(
    expected: np.ndarray,
    realized: np.ndarray,
    *,
    bridge: bool = True,
    agreement: float = 1.0,
    expected_present: bool = True,
) -> dict[str, object]:
    """Use fixed plan defaults so boundary tests remain easy to audit."""

    return dict(evaluate_strut_profiles(
        expected,
        realized,
        minimum_gap_voxels=3,
        minimum_realized_fraction=0.80,
        bridge_connected=bridge,
        perturbation_agreement=agreement,
        minimum_perturbation_agreement=0.80,
        expected_present=expected_present,
    ))


def full(length: int = 20) -> np.ndarray:
    return np.ones(length, dtype=bool)


def assertion(result: dict[str, object], expected: bool | None, review: bool) -> None:
    assert result["has_error"] is expected
    assert result["review_required"] is review


def test_intact_expected_strut_is_healthy() -> None:
    assertion(evaluate(full(), full()), False, False)


def test_completely_absent_expected_strut_is_error() -> None:
    assertion(evaluate(full(), np.zeros(20, dtype=bool), bridge=False), True, True)


def test_midspan_gap_at_minimum_length_is_error() -> None:
    observed = full()
    observed[8:11] = False
    result = evaluate(full(), observed, bridge=False)
    assertion(result, True, True)
    assert result["longest_unrealized_gap_voxels"] == 3


def test_two_voxel_pinhole_is_not_confirmed_error() -> None:
    observed = full()
    observed[8:10] = False
    assertion(evaluate(full(), observed, bridge=True), False, False)


def test_broken_bridge_alone_requires_review_not_confirmed_error() -> None:
    result = evaluate(full(), full(), bridge=False)
    assertion(result, None, True)
    assert result["decision_reason"] == "bridge_only_disagreement"


def test_broken_bridge_strengthens_a_three_bin_gap_error() -> None:
    observed = full()
    observed[8:11] = False
    assertion(evaluate(full(), observed, bridge=False), True, True)


def test_low_realization_alone_is_error() -> None:
    observed = full()
    observed[[1, 4, 7, 10, 13]] = False
    result = evaluate(full(), observed)
    assertion(result, True, True)
    assert result["realized_axial_fraction"] == pytest.approx(0.75)


def test_exact_realization_boundary_is_healthy() -> None:
    observed = full()
    observed[[1, 6, 11, 16]] = False
    assertion(evaluate(full(), observed), False, False)


def test_nonexpected_axial_bins_do_not_reduce_realization() -> None:
    expected = np.zeros(20, dtype=bool)
    expected[5:15] = True
    observed = expected.copy()
    result = evaluate(expected, observed)
    assertion(result, False, False)
    assert result["realized_axial_fraction"] == pytest.approx(1.0)


def test_expected_absence_matching_ct_is_healthy() -> None:
    empty = np.zeros(20, dtype=bool)
    result = evaluate(empty, empty, bridge=False, expected_present=False)
    assertion(result, False, False)
    assert result["comparison_applicable"] is False


def test_unexpected_material_for_absent_cad_strut_is_explicitly_out_of_scope() -> None:
    empty = np.zeros(20, dtype=bool)
    result = evaluate(empty, full(), bridge=True, expected_present=False)
    assertion(result, False, False)
    assert result["comparison_applicable"] is False


def test_partial_material_for_absent_cad_strut_is_explicitly_out_of_scope() -> None:
    empty = np.zeros(20, dtype=bool)
    observed = np.zeros(20, dtype=bool)
    observed[::2] = True
    result = evaluate(empty, observed, bridge=False, expected_present=False)
    assertion(result, False, False)
    assert result["comparison_applicable"] is False


def test_threshold_instability_requires_review_even_for_clear_error() -> None:
    result = evaluate(
        full(), np.zeros(20, dtype=bool), bridge=False, agreement=0.79
    )
    assertion(result, None, True)


def test_exact_stability_boundary_is_accepted() -> None:
    assertion(evaluate(full(), full(), agreement=0.80), False, False)


@pytest.mark.parametrize(
    ("expected", "realized"),
    [
        (np.ones(0, dtype=bool), np.ones(0, dtype=bool)),
        (np.ones(3, dtype=bool), np.ones(4, dtype=bool)),
        (np.ones((2, 2), dtype=bool), np.ones((2, 2), dtype=bool)),
    ],
)
def test_invalid_profile_shapes_are_rejected(
    expected: np.ndarray, realized: np.ndarray
) -> None:
    with pytest.raises(ValueError):
        evaluate(expected, realized)


@pytest.mark.parametrize("agreement", [-0.01, 1.01, np.nan])
def test_invalid_agreement_is_rejected(agreement: float) -> None:
    with pytest.raises(ValueError):
        evaluate(full(), full(), agreement=agreement)


def test_policy_is_deterministic() -> None:
    observed = full()
    observed[6:11] = False
    first = evaluate(full(), observed, bridge=False, agreement=0.95)
    second = evaluate(full(), observed, bridge=False, agreement=0.95)
    assert first == second
