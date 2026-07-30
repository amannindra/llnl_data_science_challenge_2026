"""Focused adversarial tests for frozen CAD-only control validation."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest

from Aman_Scripts.Components.lattice_graph import load_lattice_graph, parse_lattice_graph
from Aman_Scripts.Components.reporting import canonical_json_bytes, file_sha256
from Aman_Scripts.Components.strut_control_validation import (
    StrutControlValidationError,
    auc_bounds,
    axis_tertiles,
    build_control_features,
    build_control_manifest,
    canonical_undirected_orientation,
    classify_boundary,
    corridor_fov_eligible,
    matched_pair_win_bounds,
    raw_anomaly_score,
    summarize_control_results,
    tie_aware_auc,
    validate_control_artifact_provenance,
    validate_control_manifest,
    wilson_interval,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "missing_struts"
DESIGN_JSON = DATA / "octet_truss_9x9x9.json"
REGISTERED_JSON = (
    DATA / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)
RADIUS = 3.6717664968970167
DISTANCE = 2.0
ABSOLUTE_PADDING = RADIUS + DISTANCE + 1.0
SELECTION_PADDING = RADIUS + 2.0 + max(2.0, RADIUS) + 2.0
CURRENT_REMOVED_IDS = (
    170, 506, 614, 761, 1223, 1232, 1465, 1785, 2294, 2311, 2447, 2453,
    2536, 3282, 3364, 3383, 4016, 4461, 4463, 4626, 4651, 4774, 5104,
    5250, 5277, 5285, 5304, 5602, 5643, 5667, 5718, 5803, 5827, 5830,
    6191, 6257, 6298, 6499, 6519, 6522, 6939, 6956, 7590, 7615, 7617,
    7809, 7817, 7836, 7840, 7844, 8127, 8286, 8311, 8313, 8505, 8513,
    8528, 8532, 8536, 8592, 8686, 8731, 8814, 9038, 9745, 10458, 10515,
    10997, 11083, 11482, 11592, 11679, 12476, 12661, 13286, 13559, 13628,
    13765, 13990, 14040, 14864, 15457, 15618, 15655, 15830, 16089, 16230,
    16379, 16436, 16594, 17095, 17192, 17799, 18445,
)
EXPECTED_REMOVED_SHA256 = "97388c3f821e1969d9fa8a6be57c2a6e0d4a5bccfca17cd24c8db98e99031f28"


def _hash(value) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _provenance(removed_ids=(1000, 1001)) -> dict:
    matrix = np.eye(4).tolist()
    comparator = {
        "expected_radius_voxels": 1.0,
        "distance_tolerance_voxels": 1.0,
        "selection_padding_voxels": 7.0,
        "background_guard_voxels": 2.0,
        "maximum_perturbation_shift_voxels": 1.0,
        "minimum_local_contrast_fraction": 0.25,
        "minimum_realized_fraction": 0.8,
        "minimum_gap_voxels": 3,
    }
    return {
        "design_json_sha256": "a" * 64,
        "registered_json_sha256": "b" * 64,
        "complete_stl_sha256": "c" * 64,
        "specimen_stl_sha256": "d" * 64,
        "tiff_sha256": "e" * 64,
        "registration_matrix": matrix,
        "registration_transform_sha256": _hash(matrix),
        "comparator_parameters": comparator,
        "comparator_parameters_sha256": _hash(comparator),
        "removed_strut_ids_sha256": _hash(sorted(removed_ids)),
        "mapping_algorithm_version": "synthetic-test-v1",
    }


def _synthetic_graphs():
    # Separate source-junction IDs intentionally repeat one physical coordinate
    # so endpoint-adjacency rejection is tested after positional welding.
    segments = [
        (1, (0.0, 0.0, 0.0), (12.0, 12.0, 12.0)),
        (1000, (4.1, 5.0, 6.0), (5.1, 5.0, 6.0)),
        (1001, (6.1, 6.0, 6.0), (7.1, 6.0, 6.0)),
        (1100, (4.2, 7.0, 6.0), (5.2, 7.0, 6.0)),
        (1101, (5.3, 5.5, 6.0), (6.3, 5.5, 6.0)),
        (1102, (6.3, 7.0, 6.0), (7.3, 7.0, 6.0)),
        (1103, (6.9, 5.0, 6.0), (7.9, 5.0, 6.0)),
        (1104, (5.1, 5.0, 6.0), (6.1, 5.0, 6.0)),
    ]

    def payload(shift: float) -> dict:
        junctions, struts = [], []
        for offset, (strut_id, first, second) in enumerate(segments):
            first_id, second_id = 2 * offset, 2 * offset + 1
            junctions.extend([
                {"id": first_id, "position": [value + shift for value in first]},
                {"id": second_id, "position": [value + shift for value in second]},
            ])
            struts.append({
                "id": strut_id,
                "junction0": first_id,
                "junction1": second_id,
                "thickness": 0.1,
            })
        return {"junctions": junctions, "struts": struts}

    return parse_lattice_graph(payload(0.0)), parse_lattice_graph(payload(20.0))


def _synthetic_manifest() -> dict:
    design, registered = _synthetic_graphs()
    ids = [item.id for item in design.struts]
    coverage = np.full((len(ids), 4, 3), 0.95, dtype=np.float32)
    return build_control_manifest(
        design,
        registered,
        ids,
        [1000, 1001],
        coverage,
        (64, 64, 64),
        _provenance(),
        expected_radius_voxels=1.0,
        distance_tolerance_voxels=1.0,
        selection_padding_voxels=7.0,
        expected_positive_count=2,
        expected_skin_positive_count=0,
    )


def _reseal(value: dict) -> None:
    payload = copy.deepcopy(value)
    payload.pop("content_sha256", None)
    value["content_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _ideal_results(manifest: dict) -> dict[int, dict]:
    results = {}
    for item in manifest["positive_controls"]:
        if item["inspectable"]:
            results[item["strut_id"]] = {
                "comparison_applicable": True,
                "has_error": True,
                "realized_axial_fraction": 0.20,
                "longest_unrealized_gap_voxels": 6,
            }
    for item in manifest["matched_negative_controls"]:
        results[item["strut_id"]] = {
            "comparison_applicable": True,
            "has_error": False,
            "realized_axial_fraction": 1.0,
            "longest_unrealized_gap_voxels": 0,
        }
    return results


def test_orientation_is_an_exact_undirected_integer_lattice_key() -> None:
    forward = canonical_undirected_orientation((2.0, -2.0, 0.0))
    reverse = canonical_undirected_orientation((-2.0, 2.0, -0.0))
    assert forward == reverse == (1, -1, 0)
    assert all(isinstance(value, int) for value in forward)


def test_zero_orientation_is_rejected() -> None:
    with pytest.raises(StrutControlValidationError, match="nonzero"):
        canonical_undirected_orientation((0.0, 0.0, 0.0))


def test_boundary_classification_covers_all_three_classes() -> None:
    box_min, box_max = (0, 0, 0), (12, 12, 12)
    assert classify_boundary((0, 5, 5), (1, 5, 5), box_min, box_max) == "boundary_endpoint"
    assert classify_boundary((1, 5, 5), (2, 5, 5), box_min, box_max) == "near_boundary"
    assert classify_boundary((4, 5, 6), (5, 5, 6), box_min, box_max) == "interior"


def test_axis_tertiles_use_half_open_thirds_and_include_maximum() -> None:
    assert axis_tertiles((0, 4, 12), (0, 0, 0), (12, 12, 12)) == (0, 1, 2)
    assert axis_tertiles((3.999, 7.999, 8), (0, 0, 0), (12, 12, 12)) == (0, 1, 2)


def test_fov_rule_uses_explicit_selection_padding_in_xyz_order() -> None:
    eligible, padding = corridor_fov_eligible(
        (11, 11, 11), (20, 20, 20), (30, 31, 32),
        expected_radius_voxels=3, distance_tolerance_voxels=2,
        selection_padding_voxels=10,
    )
    assert eligible is False
    assert padding == 10


def test_selection_padding_cannot_understate_absolute_corridor() -> None:
    with pytest.raises(StrutControlValidationError, match="shifted annular"):
        corridor_fov_eligible(
            (10, 10, 10), (20, 20, 20), (40, 40, 40),
            expected_radius_voxels=3, distance_tolerance_voxels=2,
            selection_padding_voxels=5,
        )


def test_raw_score_matches_detector_or_boundary() -> None:
    assert raw_anomaly_score({
        "realized_axial_fraction": 0.8,
        "longest_unrealized_gap_voxels": 3,
    }) == pytest.approx(1.0)
    assert raw_anomaly_score({
        "realized_axial_fraction": 0.4,
        "longest_unrealized_gap_voxels": 1,
    }) == pytest.approx(3.0)


def test_raw_score_is_unavailable_when_required_evidence_is_missing() -> None:
    assert raw_anomaly_score({"realized_axial_fraction": 0.5}) is None


def test_auc_awards_half_credit_to_ties() -> None:
    assert tie_aware_auc([2.0, 1.0], [1.0, 0.0]) == pytest.approx(0.875)


def test_auc_bounds_are_conservative_for_unavailable_scores() -> None:
    result = auc_bounds([2.0, None], [1.0, 0.0])
    assert result["complete_case_auc"] == 1.0
    assert result["lower_bound"] == 0.5
    assert result["upper_bound"] == 1.0


def test_matched_pair_win_is_aligned_not_all_pairs_auc() -> None:
    result = matched_pair_win_bounds([2.0, 0.0], [1.0, -1.0])
    assert result["complete_case_win_fraction"] == 1.0
    assert result["lower_bound"] == 1.0
    assert tie_aware_auc([2.0, 0.0], [1.0, -1.0]) == 0.75


def test_matched_pair_bounds_include_unknown_pair_extremes() -> None:
    result = matched_pair_win_bounds([2.0, None], [1.0, 0.0])
    assert result["known_pair_count"] == 1
    assert result["lower_bound"] == 0.5
    assert result["upper_bound"] == 1.0


def test_wilson_interval_handles_extreme_and_empty_counts() -> None:
    assert wilson_interval(0, 0) is None
    lower, upper = wilson_interval(10, 10)
    assert 0.72 < lower < upper == pytest.approx(1.0)


def test_feature_builder_welds_duplicate_physical_endpoints() -> None:
    design, registered = _synthetic_graphs()
    features = build_control_features(
        design, registered, (64, 64, 64), expected_radius_voxels=1,
        distance_tolerance_voxels=1, selection_padding_voxels=7,
    )
    assert set(features[1000]["physical_node_ids"]).intersection(
        features[1104]["physical_node_ids"]
    )
    assert features[1000]["boundary_class"] == "interior"


def test_manifest_is_deterministic_exact_stratified_global_two_to_one() -> None:
    first, second = _synthetic_manifest(), _synthetic_manifest()
    assert first == second
    assert first["content_sha256"] == second["content_sha256"]
    assert first["counts"]["positive_inspectable"] == 2
    assert first["counts"]["matched_negative_total"] == 4
    negatives = first["matched_negative_controls"]
    assert len({item["strut_id"] for item in negatives}) == 4
    for negative in negatives:
        positive = next(
            item for item in first["positive_controls"]
            if item["strut_id"] == negative["matched_positive_strut_id"]
        )
        assert negative["orientation_key"] == positive["orientation_key"]
        assert negative["boundary_class"] == positive["boundary_class"]
        assert negative["axis_tertiles_xyz"] == positive["axis_tertiles_xyz"]
        assert not set(negative["physical_node_ids"]).intersection(
            positive["physical_node_ids"]
        )


def test_manifest_records_both_absolute_and_final_selection_padding() -> None:
    manifest = _synthetic_manifest()
    assert manifest["parameters"]["absolute_corridor_padding_voxels"] == 4.0
    assert manifest["parameters"]["central_annulus_padding_voxels"] == 6.0
    assert manifest["parameters"]["required_selection_padding_voxels"] == 7.0
    assert manifest["parameters"]["selection_padding_voxels"] == 7.0


def test_manifest_rejects_insufficient_nonadjacent_candidates() -> None:
    design, registered = _synthetic_graphs()
    ids = [item.id for item in design.struts]
    with pytest.raises(StrutControlValidationError, match="match slots|global assignment"):
        build_control_manifest(
            design, registered, ids, [1000, 1001],
            np.ones((len(ids), 2, 2)), (64, 64, 64), _provenance(),
            expected_radius_voxels=1, distance_tolerance_voxels=1,
            selection_padding_voxels=7, negative_matches_per_positive=3,
            expected_positive_count=2, expected_skin_positive_count=0,
        )


def test_manifest_hash_detects_unsealed_tampering() -> None:
    manifest = _synthetic_manifest()
    manifest["counts"]["matched_negative_total"] += 1
    with pytest.raises(StrutControlValidationError, match="content hash"):
        validate_control_manifest(manifest)


def test_manifest_rejects_ct_evidence_even_after_resealing() -> None:
    manifest = _synthetic_manifest()
    manifest["parameters"]["realized_profile"] = [True]
    _reseal(manifest)
    with pytest.raises(StrutControlValidationError, match="CT-derived evidence"):
        validate_control_manifest(manifest)


def test_manifest_rejects_duplicate_match_slots_after_resealing() -> None:
    manifest = _synthetic_manifest()
    rows = manifest["matched_negative_controls"]
    same_positive = [
        item for item in rows
        if item["matched_positive_strut_id"] == rows[0]["matched_positive_strut_id"]
    ]
    same_positive[1]["match_slot"] = same_positive[0]["match_slot"]
    _reseal(manifest)
    with pytest.raises(StrutControlValidationError, match="slots"):
        validate_control_manifest(manifest)


def test_manifest_rejects_stale_expected_provenance() -> None:
    expected = _provenance()
    expected["mapping_algorithm_version"] = "different-version"
    with pytest.raises(StrutControlValidationError, match="provenance mismatch"):
        validate_control_manifest(_synthetic_manifest(), expected_provenance=expected)


@pytest.mark.parametrize("raw_key", ["registration_matrix", "comparator_parameters"])
def test_manifest_rejects_raw_provenance_whose_hash_is_stale(raw_key: str) -> None:
    manifest = _synthetic_manifest()
    if raw_key == "registration_matrix":
        manifest["provenance"][raw_key][0][0] = 2.0
    else:
        manifest["provenance"][raw_key]["minimum_gap_voxels"] = 99
    _reseal(manifest)
    with pytest.raises(StrutControlValidationError, match="does not match raw content"):
        validate_control_manifest(manifest)


def test_ideal_control_results_pass_every_frozen_gate() -> None:
    manifest = _synthetic_manifest()
    artifact = summarize_control_results(manifest, _ideal_results(manifest))
    assert artifact["gate_evaluation"]["passed"] is True
    assert artifact["metrics"]["roc_auc"]["lower_bound"] == 1.0
    assert artifact["metrics"]["matched_pair_win"]["lower_bound"] == 1.0
    validate_control_artifact_provenance(artifact, manifest)


def test_unknown_evidence_widens_bounds_and_fails_frozen_gates() -> None:
    manifest = _synthetic_manifest()
    results = _ideal_results(manifest)
    negative_id = manifest["matched_negative_controls"][0]["strut_id"]
    results[negative_id] = {"comparison_applicable": True, "has_error": None}
    artifact = summarize_control_results(manifest, results)
    assert artifact["metrics"]["roc_auc"]["lower_bound"] == 0.75
    assert artifact["metrics"]["matched_pair_win"]["lower_bound"] == 0.75
    assert artifact["gate_evaluation"]["passed"] is False


def test_result_population_must_exactly_match_manifest() -> None:
    manifest = _synthetic_manifest()
    results = _ideal_results(manifest)
    results.pop(next(iter(results)))
    with pytest.raises(StrutControlValidationError, match="do not match"):
        summarize_control_results(manifest, results)


def test_result_artifact_cannot_be_rebound_to_another_manifest() -> None:
    manifest = _synthetic_manifest()
    artifact = summarize_control_results(manifest, _ideal_results(manifest))
    artifact["manifest_content_sha256"] = "f" * 64
    _reseal(artifact)
    with pytest.raises(StrutControlValidationError, match="different manifest"):
        validate_control_artifact_provenance(artifact, manifest)


def test_real_current_cad_omissions_support_91_by_2_ct_free_controls() -> None:
    """Exercise real graph geometry without rerunning either large STL mapping."""

    assert len(CURRENT_REMOVED_IDS) == 94
    removed_hash = _hash(sorted(CURRENT_REMOVED_IDS))
    assert removed_hash == EXPECTED_REMOVED_SHA256
    assert file_sha256(DESIGN_JSON) == (
        "af7bbd51657735f0a0af07ea8ede2007416c61821b7860936457ab0b76fad6a2"
    )
    assert file_sha256(REGISTERED_JSON) == (
        "8e422e1ceece719bdc1d0aa1b6f42273c4dea5bff6ee2ebba76e85ffddba99c7"
    )
    design, registered = load_lattice_graph(DESIGN_JSON), load_lattice_graph(REGISTERED_JSON)
    ids = [item.id for item in design.struts]
    registration_matrix = [
        [0.08810763318255853, -0.01410802262535, 17.319423431489426, 416.2703565020146],
        [17.319362899930898, 0.04798663135928507, -0.08806823638762563, 406.70596969256985],
        [-0.047914257007765707, 17.319581064144156, 0.014351901163363854, 381.17098265062987],
        [0.0, 0.0, 0.0, 1.0],
    ]
    comparator = {
        "expected_radius_voxels": RADIUS,
        "distance_tolerance_voxels": DISTANCE,
        "selection_padding_voxels": SELECTION_PADDING,
        "background_guard_voxels": 2.0,
        "maximum_perturbation_shift_voxels": 1.0,
        "minimum_local_contrast_fraction": 0.25,
        "minimum_realized_fraction": 0.8,
        "minimum_gap_voxels": 3,
    }
    provenance = {
        "design_json_sha256": file_sha256(DESIGN_JSON),
        "registered_json_sha256": file_sha256(REGISTERED_JSON),
        "complete_stl_sha256": (
            "2a5b2911f641b0282c276ea6bb1062d98c5b956396a18dd60a9fd3b8c1d8220a"
        ),
        "specimen_stl_sha256": (
            "24dcb40c13c4a729cdd84b760b803d78c61bb31ec6b2411724ff6f78cafc2ec4"
        ),
        "tiff_sha256": "1dea75b7a9882065cc52d4eb137b7d2cdc86d3ad928543e751ae4c811c466b79",
        "registration_matrix": registration_matrix,
        "registration_transform_sha256": _hash(registration_matrix),
        "comparator_parameters": comparator,
        "comparator_parameters_sha256": _hash(comparator),
        "removed_strut_ids_sha256": EXPECTED_REMOVED_SHA256,
        "mapping_algorithm_version": "native-surface-corridor-v1/current-intent-audit",
    }
    # Uniform complete-STL quality deliberately tests only graph/FOV feasibility;
    # production selection supplies the measured complete-STL coverage tensor.
    manifest = build_control_manifest(
        design, registered, ids, CURRENT_REMOVED_IDS,
        np.ones((len(ids), 1, 1), dtype=np.float32),
        (761, 815, 837), provenance,
        expected_radius_voxels=RADIUS,
        distance_tolerance_voxels=DISTANCE,
        selection_padding_voxels=SELECTION_PADDING,
    )
    assert manifest["removed_strut_ids_sha256"] == EXPECTED_REMOVED_SHA256
    assert manifest["counts"] == {
        "positive_total": 94,
        "positive_inspectable": 91,
        "positive_skin_unobservable": 3,
        "positive_fov_unobservable": 0,
        "matched_negative_total": 182,
    }
    assert manifest["parameters"]["absolute_corridor_padding_voxels"] == pytest.approx(
        ABSOLUTE_PADDING
    )
    assert manifest["parameters"]["selection_padding_voxels"] == pytest.approx(
        SELECTION_PADDING
    )
    assert {item["strut_id"] for item in manifest["positive_controls"] if item["skin_embedded"]} == {
        170, 1223, 1465,
    }
    validate_control_manifest(manifest, expected_provenance=provenance)
