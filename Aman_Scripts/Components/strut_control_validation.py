"""Frozen CAD-only controls and post-hoc validation; selection never reads CT intensity."""

from __future__ import annotations

from collections import defaultdict
import copy
import hashlib
import re
from typing import Any, Mapping, Sequence

import numpy as np

from .lattice_graph import LatticeGraph, weld_coincident_nodes
from .reporting import canonical_json_bytes, json_safe
from .strut_control_statistics import (
    DEFAULT_GATES,
    StrutControlValidationError,
    auc_bounds,
    decision as _decision,
    matched_pair_win_bounds,
    population_metrics as _population_metrics,
    powered_stratum_gate,
    raw_anomaly_score,
    stratified_metrics as _stratified_metrics,
    tie_aware_auc,
    wilson_interval,
)


MANIFEST_SCHEMA_VERSION = "stl-tiff-strut-controls.v1"
RESULT_SCHEMA_VERSION = "stl-tiff-strut-control-results.v1"
FORBIDDEN_MANIFEST_EVIDENCE_KEYS = frozenset({
    "has_error", "realized_axial_fraction", "longest_unrealized_gap_voxels",
    "realized_profile", "support_intensity_profile", "local_background_median_profile",
    "local_contrast_fraction_profile", "ct_to_stl_near_fraction", "stl_to_ct_near_fraction",
})
REQUIRED_PROVENANCE_KEYS = (
    "design_json_sha256", "registered_json_sha256", "complete_stl_sha256",
    "specimen_stl_sha256", "tiff_sha256", "registration_transform_sha256",
    "comparator_parameters_sha256", "removed_strut_ids_sha256",
    "mapping_algorithm_version",
)
def _xyz(value: Sequence[float], name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise StrutControlValidationError(f"{name} must contain three finite XYZ values")
    return result


def _positive(value: float, name: str, *, allow_zero: bool = False) -> float:
    number = float(value)
    valid = number >= 0.0 if allow_zero else number > 0.0
    if not np.isfinite(number) or not valid:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise StrutControlValidationError(f"{name} must be finite and {qualifier}")
    return number


def canonical_undirected_orientation(vector_xyz: Sequence[float], *, tolerance: float = 1e-8
                                     ) -> tuple[int, int, int]:
    """Return one exact sign-invariant lattice direction in {-1, 0, 1}^3."""

    vector = _xyz(vector_xyz, "vector_xyz")
    tolerance = _positive(tolerance, "tolerance", allow_zero=True)
    scale = float(np.max(np.abs(vector)))
    if scale <= tolerance:
        raise StrutControlValidationError("orientation vector must be nonzero")
    direction = vector / scale
    lattice_direction = np.rint(direction)
    if np.any(np.abs(direction - lattice_direction) > tolerance):
        raise StrutControlValidationError("orientation is not an equal-component lattice direction")
    direction = lattice_direction.astype(np.int8)
    nonzero = np.flatnonzero(np.abs(direction) > tolerance)
    if nonzero.size == 0:
        raise StrutControlValidationError("orientation vector is below tolerance")
    if direction[int(nonzero[0])] < 0:
        direction *= -1
    return tuple(int(item) for item in direction)


def orientation_key(orientation_xyz: Sequence[float]) -> str:
    """Serialize one canonical orientation without platform-dependent reprs."""

    values = canonical_undirected_orientation(orientation_xyz)
    return ",".join(str(item) for item in values)


def classify_boundary(
    endpoint0_xyz: Sequence[float],
    endpoint1_xyz: Sequence[float],
    bbox_min_xyz: Sequence[float],
    bbox_max_xyz: Sequence[float],
    *,
    near_boundary_depth: float = 2.0,
    tolerance: float = 1e-8,
) -> str:
    """Classify by endpoint contact, then midpoint distance from a box face."""

    first = _xyz(endpoint0_xyz, "endpoint0_xyz")
    second = _xyz(endpoint1_xyz, "endpoint1_xyz")
    lower = _xyz(bbox_min_xyz, "bbox_min_xyz")
    upper = _xyz(bbox_max_xyz, "bbox_max_xyz")
    depth = _positive(near_boundary_depth, "near_boundary_depth", allow_zero=True)
    tolerance = _positive(tolerance, "tolerance", allow_zero=True)
    if np.any(upper <= lower):
        raise StrutControlValidationError("design bounding box must have positive span")
    for endpoint in (first, second):
        if np.any(np.abs(endpoint - lower) <= tolerance) or np.any(
            np.abs(endpoint - upper) <= tolerance
        ):
            return "boundary_endpoint"
    midpoint = (first + second) / 2.0
    face_distance = float(np.min(np.concatenate((midpoint - lower, upper - midpoint))))
    return "near_boundary" if face_distance <= depth + tolerance else "interior"


def axis_tertiles(midpoint_xyz: Sequence[float], bbox_min_xyz: Sequence[float],
                  bbox_max_xyz: Sequence[float]) -> tuple[int, int, int]:
    """Return half-open XYZ thirds, clipping the maximum face into bin two."""

    midpoint = _xyz(midpoint_xyz, "midpoint_xyz")
    lower = _xyz(bbox_min_xyz, "bbox_min_xyz")
    upper = _xyz(bbox_max_xyz, "bbox_max_xyz")
    span = upper - lower
    if np.any(span <= 0.0):
        raise StrutControlValidationError("design bounding box must have positive span")
    relative = (midpoint - lower) / span
    if np.any(relative < -1e-10) or np.any(relative > 1.0 + 1e-10):
        raise StrutControlValidationError("midpoint lies outside the design bounding box")
    bins = np.clip(np.floor(3.0 * relative).astype(np.int64), 0, 2)
    return tuple(int(item) for item in bins)


def _corridor_paddings(
    radius: float, distance: float, background_guard: float, maximum_shift: float
) -> tuple[float, float, float]:
    corridor = max(3.0, max(0.1, min(10.0, radius + distance)))
    absolute = corridor + 1.0
    central_annulus = radius + background_guard + max(2.0, radius) + 1.0
    return absolute, central_annulus, central_annulus + maximum_shift


def corridor_fov_eligible(endpoint0_xyz: Sequence[float], endpoint1_xyz: Sequence[float],
                          tiff_shape_zyx: Sequence[int], *, expected_radius_voxels: float,
                          distance_tolerance_voxels: float = 2.0,
                          selection_padding_voxels: float | None = None,
                          background_guard_voxels: float = 2.0,
                          maximum_perturbation_shift_voxels: float = 1.0) -> tuple[bool, float]:
    """Apply the comparator's exact integer crop rule using native TIFF shape."""

    first = _xyz(endpoint0_xyz, "endpoint0_xyz")
    second = _xyz(endpoint1_xyz, "endpoint1_xyz")
    shape_zyx = np.asarray(tiff_shape_zyx)
    if shape_zyx.shape != (3,) or np.any(shape_zyx < 2):
        raise StrutControlValidationError("tiff_shape_zyx must contain three sizes >= 2")
    if not np.equal(shape_zyx, np.floor(shape_zyx)).all():
        raise StrutControlValidationError("tiff_shape_zyx must contain integers")
    radius = _positive(expected_radius_voxels, "expected_radius_voxels")
    distance = _positive(
        distance_tolerance_voxels, "distance_tolerance_voxels", allow_zero=True
    )
    guard = _positive(background_guard_voxels, "background_guard_voxels", allow_zero=True)
    shift = _positive(
        maximum_perturbation_shift_voxels,
        "maximum_perturbation_shift_voxels", allow_zero=True,
    )
    _, _, required_padding = _corridor_paddings(radius, distance, guard, shift)
    padding = required_padding if selection_padding_voxels is None else _positive(
        selection_padding_voxels, "selection_padding_voxels"
    )
    if padding + 1e-12 < required_padding:
        raise StrutControlValidationError("selection padding cannot omit shifted annular evidence")
    shape_xyz = shape_zyx[::-1].astype(np.int64)
    lower = np.floor(np.minimum(first, second) - padding).astype(np.int64)
    upper = np.ceil(np.maximum(first, second) + padding).astype(np.int64) + 1
    eligible = bool(np.all(lower >= 0) and np.all(upper <= shape_xyz))
    return eligible, float(padding)


def _orientation_key_from_canonical(values: Sequence[float]) -> str:
    return ",".join(str(int(item)) for item in values)


def _stratum_key(feature: Mapping[str, Any]) -> tuple[Any, ...]:
    bins = feature["axis_tertiles_xyz"]
    return (
        feature["orientation_key"],
        feature["boundary_class"],
        int(bins[0]),
        int(bins[1]),
        int(bins[2]),
    )


def build_control_features(design_graph: LatticeGraph, registered_graph: LatticeGraph,
                           tiff_shape_zyx: Sequence[int], *, expected_radius_voxels: float,
                           distance_tolerance_voxels: float = 2.0,
                           selection_padding_voxels: float | None = None,
                           background_guard_voxels: float = 2.0,
                           maximum_perturbation_shift_voxels: float = 1.0,
                           near_boundary_depth: float = 2.0, skin_normal_axis: int = 2,
                           tolerance: float = 1e-8) -> dict[int, dict[str, Any]]:
    """Build deterministic pure-geometry features for every source strut."""

    if skin_normal_axis not in (0, 1, 2):
        raise StrutControlValidationError("skin_normal_axis must be 0, 1, or 2")
    design_ids = [item.id for item in design_graph.struts]
    registered_ids = [item.id for item in registered_graph.struts]
    if design_ids != registered_ids:
        raise StrutControlValidationError("design and registered strut IDs differ")
    design_junctions = design_graph.junction_by_id()
    registered_junctions = registered_graph.junction_by_id()
    design_points = np.asarray([item.position for item in design_graph.junctions])
    if design_points.shape[0] == 0:
        raise StrutControlValidationError("design graph has no junctions")
    lower = design_points.min(axis=0)
    upper = design_points.max(axis=0)
    if np.any(upper <= lower):
        raise StrutControlValidationError("design graph bounding box is degenerate")
    welded = weld_coincident_nodes(design_graph, tolerance=1e-6)
    features: dict[int, dict[str, Any]] = {}
    registered_by_id = registered_graph.strut_by_id()
    for edge in design_graph.struts:
        registered_edge = registered_by_id[edge.id]
        if (edge.junction0, edge.junction1) != (
            registered_edge.junction0,
            registered_edge.junction1,
        ):
            raise StrutControlValidationError(
                f"design and registered endpoints differ for strut {edge.id}"
            )
        first = np.asarray(design_junctions[edge.junction0].position, dtype=np.float64)
        second = np.asarray(design_junctions[edge.junction1].position, dtype=np.float64)
        registered_first = registered_junctions[edge.junction0].position
        registered_second = registered_junctions[edge.junction1].position
        midpoint = (first + second) / 2.0
        orientation = canonical_undirected_orientation(
            second - first, tolerance=tolerance
        )
        fov_eligible, padding = corridor_fov_eligible(
            registered_first,
            registered_second,
            tiff_shape_zyx,
            expected_radius_voxels=expected_radius_voxels,
            distance_tolerance_voxels=distance_tolerance_voxels,
            selection_padding_voxels=selection_padding_voxels,
            background_guard_voxels=background_guard_voxels,
            maximum_perturbation_shift_voxels=maximum_perturbation_shift_voxels,
        )
        absolute_padding, central_padding, required_padding = _corridor_paddings(
            expected_radius_voxels, distance_tolerance_voxels,
            background_guard_voxels, maximum_perturbation_shift_voxels,
        )
        lower_skin = (
            abs(first[skin_normal_axis] - lower[skin_normal_axis]) <= tolerance
            and abs(second[skin_normal_axis] - lower[skin_normal_axis]) <= tolerance
        )
        upper_skin = (
            abs(first[skin_normal_axis] - upper[skin_normal_axis]) <= tolerance
            and abs(second[skin_normal_axis] - upper[skin_normal_axis]) <= tolerance
        )
        features[edge.id] = {
            "strut_id": int(edge.id),
            "orientation_xyz": list(orientation),
            "orientation_key": _orientation_key_from_canonical(orientation),
            "boundary_class": classify_boundary(
                first,
                second,
                lower,
                upper,
                near_boundary_depth=near_boundary_depth,
                tolerance=tolerance,
            ),
            "axis_tertiles_xyz": list(axis_tertiles(midpoint, lower, upper)),
            "midpoint_xyz_design": midpoint.tolist(),
            "physical_node_ids": sorted([
                int(welded.junction_to_node[edge.junction0]),
                int(welded.junction_to_node[edge.junction1]),
            ]),
            "skin_embedded": bool(lower_skin or upper_skin),
            "fov_eligible": fov_eligible,
            "fov_padding_voxels": padding,
            "absolute_corridor_padding_voxels": float(absolute_padding),
            "central_annulus_padding_voxels": float(central_padding),
            "required_selection_padding_voxels": float(required_padding),
        }
    return features


def _validated_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(provenance, Mapping):
        raise StrutControlValidationError("provenance must be a mapping")
    clean = json_safe(dict(provenance))
    for key in REQUIRED_PROVENANCE_KEYS:
        if key not in clean or not isinstance(clean[key], str) or not clean[key]:
            raise StrutControlValidationError(f"provenance is missing nonempty {key!r}")
    for key, value in clean.items():
        if key.endswith("_sha256") and not re.fullmatch(r"[0-9a-f]{64}", str(value)):
            raise StrutControlValidationError(f"provenance {key!r} is not lowercase SHA-256")
    matrix = clean.get("registration_matrix")
    comparator = clean.get("comparator_parameters")
    try:
        matrix_array = np.asarray(matrix, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise StrutControlValidationError("registration_matrix must be numeric") from exc
    if matrix_array.shape != (4, 4) or not np.isfinite(matrix_array).all():
        raise StrutControlValidationError("registration_matrix must be a finite 4x4 matrix")
    if not isinstance(comparator, Mapping) or not comparator:
        raise StrutControlValidationError("comparator_parameters must be a nonempty mapping")
    raw_hash_pairs = (
        (matrix, "registration_transform_sha256"),
        (comparator, "comparator_parameters_sha256"),
    )
    for raw, hash_key in raw_hash_pairs:
        expected_hash = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
        if clean[hash_key] != expected_hash:
            raise StrutControlValidationError(f"provenance {hash_key!r} does not match raw content")
    return clean


def _validated_gates(gates: Mapping[str, float] | None) -> dict[str, float]:
    values = dict(DEFAULT_GATES if gates is None else gates)
    if set(values) != set(DEFAULT_GATES):
        raise StrutControlValidationError(
            f"gate names must be exactly {sorted(DEFAULT_GATES)}"
        )
    result = {}
    for key, value in values.items():
        number = float(value)
        if not np.isfinite(number) or not 0.0 <= number <= 1.0:
            raise StrutControlValidationError(f"gate {key!r} must lie in [0, 1]")
        result[key] = number
    return result


def _validate_comparator_binding(
    provenance: Mapping[str, Any], expected: Mapping[str, float | int]
) -> None:
    comparator = provenance["comparator_parameters"]
    for key, expected_value in expected.items():
        if key not in comparator:
            raise StrutControlValidationError(f"comparator_parameters is missing {key!r}")
        actual = comparator[key]
        if key in {"minimum_gap_voxels"}:
            matches = not isinstance(actual, bool) and int(actual) == expected_value
        else:
            try:
                matches = bool(np.isclose(float(actual), float(expected_value), rtol=0, atol=1e-12))
            except (TypeError, ValueError, OverflowError):
                matches = False
        if not matches:
            raise StrutControlValidationError(f"frozen comparator parameter {key!r} mismatch")


def _content_hash(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop("content_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_sha256"] = _content_hash(result)
    return result


def _pair_fraction(positive_id: int, negative_id: int) -> float:
    digest = hashlib.sha256(f"{positive_id}:{negative_id}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _manifest_record(feature: Mapping[str, Any], coverage_quality: float, *,
                     control_label: int) -> dict[str, Any]:
    result = copy.deepcopy(dict(feature))
    result["control_label"] = int(control_label)
    result["control_role"] = "cad_omission_positive" if control_label == 1 else "cad_present_matched_negative"
    result["complete_stl_coverage_quality"] = float(coverage_quality)
    return result


def build_control_manifest(design_graph: LatticeGraph, registered_graph: LatticeGraph,
                           strut_ids: Sequence[int], removed_strut_ids: Sequence[int],
                           complete_surface_coverage: np.ndarray,
                           tiff_shape_zyx: Sequence[int], provenance: Mapping[str, Any], *,
                           expected_radius_voxels: float, distance_tolerance_voxels: float = 2.0,
                           selection_padding_voxels: float | None = None,
                           background_guard_voxels: float = 2.0,
                           maximum_perturbation_shift_voxels: float = 1.0,
                           near_boundary_depth: float = 2.0, negative_matches_per_positive: int = 2,
                           exclude_source_ids_below: int = 500,
                           minimum_local_contrast_fraction: float = 0.25,
                           minimum_realized_fraction: float = 0.80,
                           minimum_gap_voxels: int = 3,
                           powered_stratum_min_positive_controls: int = 10,
                           expected_positive_count: int | None = 94,
                           expected_skin_positive_count: int | None = 3,
                           gates: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Freeze CAD-only positives and globally matched presumed negatives."""

    from scipy.optimize import linear_sum_assignment

    ids = np.asarray(strut_ids, dtype=np.int64)
    removed = np.asarray(sorted({int(item) for item in removed_strut_ids}), dtype=np.int64)
    coverage = np.asarray(complete_surface_coverage)
    if ids.ndim != 1 or ids.size == 0 or len(np.unique(ids)) != len(ids):
        raise StrutControlValidationError("strut_ids must be a nonempty unique vector")
    if coverage.ndim != 3 or coverage.shape[0] != len(ids):
        raise StrutControlValidationError(
            "complete_surface_coverage must have shape (struts, bins, radii)"
        )
    if coverage.shape[1] == 0 or coverage.shape[2] == 0:
        raise StrutControlValidationError("complete surface coverage axes cannot be empty")
    if set(removed) - set(ids):
        raise StrutControlValidationError("removed_strut_ids contain unknown IDs")
    if expected_positive_count is not None and len(removed) != expected_positive_count:
        raise StrutControlValidationError(
            f"expected {expected_positive_count} CAD omissions, got {len(removed)}"
        )
    if not isinstance(negative_matches_per_positive, int) or negative_matches_per_positive < 1:
        raise StrutControlValidationError("negative_matches_per_positive must be positive")
    if not isinstance(exclude_source_ids_below, int):
        raise StrutControlValidationError("exclude_source_ids_below must be an integer")
    if not np.isfinite(minimum_local_contrast_fraction) or not 0 < minimum_local_contrast_fraction <= 1:
        raise StrutControlValidationError("minimum_local_contrast_fraction must lie in (0, 1]")
    if not np.isfinite(minimum_realized_fraction) or not 0 < minimum_realized_fraction < 1:
        raise StrutControlValidationError("minimum_realized_fraction must lie in (0, 1)")
    if isinstance(minimum_gap_voxels, bool) or not isinstance(minimum_gap_voxels, int) or minimum_gap_voxels < 1:
        raise StrutControlValidationError("minimum_gap_voxels must be a positive integer")
    if (isinstance(powered_stratum_min_positive_controls, bool)
            or not isinstance(powered_stratum_min_positive_controls, int)
            or powered_stratum_min_positive_controls < 1):
        raise StrutControlValidationError("powered-stratum minimum count must be positive")
    provenance_clean = _validated_provenance(provenance)
    gate_values = _validated_gates(gates)
    features = build_control_features(
        design_graph,
        registered_graph,
        tiff_shape_zyx,
        expected_radius_voxels=expected_radius_voxels,
        distance_tolerance_voxels=distance_tolerance_voxels,
        selection_padding_voxels=selection_padding_voxels,
        background_guard_voxels=background_guard_voxels,
        maximum_perturbation_shift_voxels=maximum_perturbation_shift_voxels,
        near_boundary_depth=near_boundary_depth,
    )
    if set(features) != set(ids):
        raise StrutControlValidationError("strut_ids do not exactly match graph IDs")
    applied_padding = next(iter(features.values()))["fov_padding_voxels"]
    _validate_comparator_binding(provenance_clean, {
        "expected_radius_voxels": expected_radius_voxels,
        "distance_tolerance_voxels": distance_tolerance_voxels,
        "selection_padding_voxels": applied_padding,
        "background_guard_voxels": background_guard_voxels,
        "maximum_perturbation_shift_voxels": maximum_perturbation_shift_voxels,
        "minimum_local_contrast_fraction": minimum_local_contrast_fraction,
        "minimum_realized_fraction": minimum_realized_fraction,
        "minimum_gap_voxels": minimum_gap_voxels,
    })
    coverage_float = coverage.astype(np.float64, copy=False)
    if not np.isfinite(coverage_float).all() or np.any(
        (coverage_float < 0.0) | (coverage_float > 1.0)
    ):
        raise StrutControlValidationError("complete surface coverage must lie in [0, 1]")
    quality_values = np.median(coverage_float.mean(axis=1), axis=1)
    quality = {int(strut_id): float(quality_values[index]) for index, strut_id in enumerate(ids)}
    removed_set = set(int(item) for item in removed)
    removed_hash = hashlib.sha256(canonical_json_bytes(sorted(removed_set))).hexdigest()
    if provenance_clean["removed_strut_ids_sha256"] != removed_hash:
        raise StrutControlValidationError("frozen removed-strut IDs do not match provenance")
    positive_features = [features[item] for item in sorted(removed_set)]
    skin_positive_count = sum(bool(item["skin_embedded"]) for item in positive_features)
    if (
        expected_skin_positive_count is not None
        and skin_positive_count != expected_skin_positive_count
    ):
        raise StrutControlValidationError(
            f"expected {expected_skin_positive_count} skin omissions, got {skin_positive_count}"
        )
    observable = [
        item for item in positive_features
        if not item["skin_embedded"] and item["fov_eligible"]
    ]
    candidates = [
        feature for strut_id, feature in sorted(features.items())
        if strut_id not in removed_set
        and strut_id >= exclude_source_ids_below
        and not feature["skin_embedded"]
        and feature["fov_eligible"]
    ]
    positives_by_stratum: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    candidates_by_stratum: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in observable:
        positives_by_stratum[_stratum_key(item)].append(item)
    for item in candidates:
        candidates_by_stratum[_stratum_key(item)].append(item)

    matches: dict[int, list[int]] = defaultdict(list)
    sentinel = 1e9
    for stratum in sorted(positives_by_stratum, key=repr):
        positives = sorted(positives_by_stratum[stratum], key=lambda item: item["strut_id"])
        negatives = sorted(
            candidates_by_stratum.get(stratum, []), key=lambda item: item["strut_id"]
        )
        rows = [positive for positive in positives for _ in range(negative_matches_per_positive)]
        if len(negatives) < len(rows):
            raise StrutControlValidationError(
                f"stratum {stratum!r} has {len(rows)} match slots but {len(negatives)} candidates"
            )
        costs = np.full((len(rows), len(negatives)), sentinel, dtype=np.float64)
        for row_index, positive in enumerate(rows):
            positive_nodes = set(positive["physical_node_ids"])
            positive_midpoint = np.asarray(positive["midpoint_xyz_design"], dtype=np.float64)
            for column_index, negative in enumerate(negatives):
                if positive_nodes.intersection(negative["physical_node_ids"]):
                    continue
                negative_midpoint = np.asarray(
                    negative["midpoint_xyz_design"], dtype=np.float64
                )
                spatial = float(np.sum((positive_midpoint - negative_midpoint) ** 2))
                coverage_difference = abs(
                    quality[positive["strut_id"]] - quality[negative["strut_id"]]
                )
                candidate_tie = 1e-9 * (column_index + 1) / (len(negatives) + 1)
                pair_tie = 1e-12 * _pair_fraction(
                    positive["strut_id"], negative["strut_id"]
                )
                costs[row_index, column_index] = (
                    spatial + 0.1 * coverage_difference + candidate_tie + pair_tie
                )
        row_indices, column_indices = linear_sum_assignment(costs)
        if len(row_indices) != len(rows):
            raise StrutControlValidationError(f"stratum {stratum!r} assignment is incomplete")
        for row_index, column_index in zip(row_indices, column_indices):
            if costs[row_index, column_index] >= sentinel:
                raise StrutControlValidationError(
                    f"stratum {stratum!r} has no valid nonadjacent global assignment"
                )
            matches[int(rows[row_index]["strut_id"])].append(
                int(negatives[column_index]["strut_id"])
            )

    positive_records = []
    for item in positive_features:
        record = _manifest_record(item, quality[item["strut_id"]], control_label=1)
        record["inspectable"] = bool(not item["skin_embedded"] and item["fov_eligible"])
        if item["skin_embedded"]:
            record["noninspectable_reason"] = "skin_embedded"
        elif not item["fov_eligible"]:
            record["noninspectable_reason"] = "outside_complete_ct_corridor"
        else:
            record["noninspectable_reason"] = None
        positive_records.append(record)
    negative_records = []
    for positive_id in sorted(matches):
        selected = sorted(matches[positive_id])
        if len(selected) != negative_matches_per_positive:
            raise StrutControlValidationError(
                f"positive {positive_id} received {len(selected)} matched controls"
            )
        for slot, negative_id in enumerate(selected):
            record = _manifest_record(features[negative_id], quality[negative_id], control_label=0)
            record["matched_positive_strut_id"] = positive_id
            record["match_slot"] = slot
            negative_records.append(record)
    expected_negative_count = len(observable) * negative_matches_per_positive
    if len(negative_records) != expected_negative_count:
        raise StrutControlValidationError("matched-negative count is inconsistent")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "provenance": provenance_clean,
        "removed_strut_ids_sha256": removed_hash,
        "parameters": {
            "tiff_shape_zyx": [int(item) for item in tiff_shape_zyx],
            "expected_radius_voxels": float(expected_radius_voxels),
            "distance_tolerance_voxels": float(distance_tolerance_voxels),
            "background_guard_voxels": float(background_guard_voxels),
            "maximum_perturbation_shift_voxels": float(
                maximum_perturbation_shift_voxels
            ),
            "absolute_corridor_padding_voxels": next(iter(features.values()))[
                "absolute_corridor_padding_voxels"
            ],
            "central_annulus_padding_voxels": next(iter(features.values()))[
                "central_annulus_padding_voxels"
            ],
            "required_selection_padding_voxels": next(iter(features.values()))[
                "required_selection_padding_voxels"
            ],
            "selection_padding_voxels": applied_padding,
            "minimum_local_contrast_fraction": float(minimum_local_contrast_fraction),
            "minimum_realized_fraction": float(minimum_realized_fraction),
            "minimum_gap_voxels": int(minimum_gap_voxels),
            "powered_stratum_min_positive_controls": powered_stratum_min_positive_controls,
            "near_boundary_depth_design_units": float(near_boundary_depth),
            "negative_matches_per_positive": int(negative_matches_per_positive),
            "exclude_source_ids_below": int(exclude_source_ids_below),
            "matching_cost": "squared design-midpoint distance + 0.1*absolute complete-STL coverage-quality difference + deterministic tie breaks",
            "matching_exact_strata": ["orientation", "boundary_class", "x_tertile", "y_tertile", "z_tertile"],
            "selection_uses_ct_intensity": False,
        },
        "counts": {
            "positive_total": len(positive_records),
            "positive_inspectable": len(observable),
            "positive_skin_unobservable": skin_positive_count,
            "positive_fov_unobservable": sum(
                not item["fov_eligible"] and not item["skin_embedded"]
                for item in positive_features
            ),
            "matched_negative_total": len(negative_records),
        },
        "gates": gate_values,
        "positive_controls": positive_records,
        "matched_negative_controls": negative_records,
        "semantics": {
            "positive": "weak CAD-omission control against the complete-design corridor; not a final 0.5-STL label",
            "negative": "CAD-present matched control; presumed, not manually proven, healthy",
            "scope": "missing-member sensitivity only; broken-member sensitivity is not established",
        },
    }
    sealed = _sealed(manifest)
    validate_control_manifest(sealed)
    return sealed


def _walk_mapping_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_walk_mapping_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_walk_mapping_keys(item))
    return keys


def validate_control_manifest(manifest: Mapping[str, Any], *,
                              expected_provenance: Mapping[str, Any] | None = None) -> None:
    """Reject tampering, leakage fields, mismatched strata, and stale sources."""

    if not isinstance(manifest, Mapping):
        raise StrutControlValidationError("manifest must be a mapping")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise StrutControlValidationError("unsupported control-manifest schema")
    if manifest.get("content_sha256") != _content_hash(manifest):
        raise StrutControlValidationError("control-manifest content hash mismatch")
    provenance = _validated_provenance(manifest.get("provenance", {}))
    if expected_provenance is not None:
        expected = _validated_provenance(expected_provenance)
        if provenance != expected:
            raise StrutControlValidationError("control-manifest provenance mismatch")
    forbidden = FORBIDDEN_MANIFEST_EVIDENCE_KEYS.intersection(_walk_mapping_keys(manifest))
    if forbidden:
        raise StrutControlValidationError(
            f"control manifest contains CT-derived evidence keys: {sorted(forbidden)}"
        )
    positives = manifest.get("positive_controls")
    negatives = manifest.get("matched_negative_controls")
    counts = manifest.get("counts")
    parameters = manifest.get("parameters")
    if not isinstance(positives, list) or not isinstance(negatives, list):
        raise StrutControlValidationError("manifest control populations must be arrays")
    if not isinstance(counts, Mapping) or not isinstance(parameters, Mapping):
        raise StrutControlValidationError("manifest counts and parameters must be mappings")
    if parameters.get("selection_uses_ct_intensity") is not False:
        raise StrutControlValidationError("control selection is not declared CT-intensity-free")
    powered_minimum = parameters.get("powered_stratum_min_positive_controls")
    if (isinstance(powered_minimum, bool) or not isinstance(powered_minimum, int)
            or powered_minimum < 1):
        raise StrutControlValidationError("invalid powered-stratum minimum count")
    _validate_comparator_binding(provenance, {
        key: parameters[key] for key in (
            "expected_radius_voxels", "distance_tolerance_voxels",
            "selection_padding_voxels", "background_guard_voxels",
            "maximum_perturbation_shift_voxels", "minimum_local_contrast_fraction",
            "minimum_realized_fraction", "minimum_gap_voxels",
        )
    })
    positive_ids = [int(item["strut_id"]) for item in positives]
    negative_ids = [int(item["strut_id"]) for item in negatives]
    if len(positive_ids) != len(set(positive_ids)):
        raise StrutControlValidationError("positive control IDs are not unique")
    if len(negative_ids) != len(set(negative_ids)):
        raise StrutControlValidationError("negative control IDs are not unique")
    if set(positive_ids).intersection(negative_ids):
        raise StrutControlValidationError("positive and negative control IDs overlap")
    expected_removed_hash = hashlib.sha256(
        canonical_json_bytes(sorted(positive_ids))
    ).hexdigest()
    if manifest.get("removed_strut_ids_sha256") != expected_removed_hash:
        raise StrutControlValidationError("removed-strut ID hash mismatch")
    if provenance["removed_strut_ids_sha256"] != expected_removed_hash:
        raise StrutControlValidationError("removed-strut provenance hash mismatch")
    if int(counts.get("positive_total", -1)) != len(positives):
        raise StrutControlValidationError("positive count mismatch")
    if int(counts.get("matched_negative_total", -1)) != len(negatives):
        raise StrutControlValidationError("negative count mismatch")
    positive_by_id = {int(item["strut_id"]): item for item in positives}
    matches_per_positive = int(parameters.get("negative_matches_per_positive", -1))
    excluded_below = int(parameters.get("exclude_source_ids_below", -1))
    if matches_per_positive < 1:
        raise StrutControlValidationError("invalid negative_matches_per_positive")
    match_count: dict[int, int] = defaultdict(int)
    match_slots: dict[int, set[int]] = defaultdict(set)
    for positive in positives:
        if positive.get("control_label") != 1 or positive.get("control_role") != "cad_omission_positive":
            raise StrutControlValidationError("invalid positive-control semantics")
        inspectable = bool(positive.get("inspectable"))
        expected_inspectable = not bool(positive.get("skin_embedded")) and bool(
            positive.get("fov_eligible")
        )
        if inspectable != expected_inspectable:
            raise StrutControlValidationError("positive inspectability is inconsistent")
    for negative in negatives:
        if negative.get("control_label") != 0 or negative.get("control_role") != "cad_present_matched_negative":
            raise StrutControlValidationError("invalid negative-control semantics")
        if negative.get("skin_embedded") or not negative.get("fov_eligible"):
            raise StrutControlValidationError("negative control is not independently inspectable")
        if int(negative["strut_id"]) < excluded_below:
            raise StrutControlValidationError("negative control violates the source-ID exclusion")
        positive_id = int(negative.get("matched_positive_strut_id"))
        if positive_id not in positive_by_id or not positive_by_id[positive_id].get("inspectable"):
            raise StrutControlValidationError("negative references a noninspectable/unknown positive")
        positive = positive_by_id[positive_id]
        if _stratum_key(negative) != _stratum_key(positive):
            raise StrutControlValidationError("matched controls do not share an exact stratum")
        if set(negative["physical_node_ids"]).intersection(positive["physical_node_ids"]):
            raise StrutControlValidationError("matched controls share a welded physical endpoint")
        slot = int(negative.get("match_slot", -1))
        if slot < 0 or slot >= matches_per_positive or slot in match_slots[positive_id]:
            raise StrutControlValidationError("matched-control slots are inconsistent")
        match_slots[positive_id].add(slot)
        match_count[positive_id] += 1
    inspectable_ids = {
        int(item["strut_id"]) for item in positives if item.get("inspectable")
    }
    if set(match_count) != inspectable_ids or any(
        match_count[item] != matches_per_positive for item in inspectable_ids
    ):
        raise StrutControlValidationError("per-positive matched-control counts are inconsistent")
    if any(match_slots[item] != set(range(matches_per_positive)) for item in inspectable_ids):
        raise StrutControlValidationError("matched-control slot coverage is inconsistent")
    if int(counts.get("positive_inspectable", -1)) != len(inspectable_ids):
        raise StrutControlValidationError("inspectable-positive count mismatch")
    _validated_gates(manifest.get("gates"))


def _derive_control_analysis(
    rows: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    positive_rows = [item for item in rows if item["control_label"] == 1]
    negative_rows = [item for item in rows if item["control_label"] == 0]
    positive_metrics = _population_metrics(positive_rows, positive=True)
    negative_metrics = _population_metrics(negative_rows, positive=False)
    auc = auc_bounds(
        [item["raw_anomaly_score"] for item in positive_rows],
        [item["raw_anomaly_score"] for item in negative_rows],
    )
    negatives_by_positive: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for item in negative_rows:
        negatives_by_positive[int(item["matched_positive_strut_id"])].append(item)
    positive_by_id = {int(item["strut_id"]): item for item in positive_rows}
    pair_positive, pair_negative = [], []
    for positive_id in sorted(positive_by_id):
        for negative in sorted(
            negatives_by_positive[positive_id], key=lambda item: item["strut_id"]
        ):
            pair_positive.append(positive_by_id[positive_id]["raw_anomaly_score"])
            pair_negative.append(negative["raw_anomaly_score"])
    pairwise = matched_pair_win_bounds(pair_positive, pair_negative)
    gate_values = dict(manifest["gates"])
    powered = powered_stratum_gate(
        rows,
        threshold=gate_values[
            "powered_stratum_conservative_positive_sensitivity_min"
        ],
        minimum_positive_controls=manifest["parameters"][
            "powered_stratum_min_positive_controls"
        ],
    )
    observed = {
        "roc_auc_lower_bound_min": auc["lower_bound"],
        "decidable_positive_sensitivity_min": positive_metrics["success_rate_decidable"],
        "decidable_negative_stable_rate_min": negative_metrics["success_rate_decidable"],
        "positive_review_rate_max": positive_metrics["review_rate"],
        "negative_review_rate_max": negative_metrics["review_rate"],
        "conservative_positive_capture_min": positive_metrics["success_rate_conservative"],
        "conservative_negative_stable_rate_min": negative_metrics["success_rate_conservative"],
        "matched_pair_win_lower_bound_min": pairwise["lower_bound"],
        "powered_stratum_conservative_positive_sensitivity_min": powered[
            "worst_powered_sensitivity"
        ],
    }
    checks = []
    for name, threshold in sorted(gate_values.items()):
        value = observed[name]
        maximum = name.endswith("_max")
        passed = value is not None and (value <= threshold if maximum else value >= threshold)
        checks.append({
            "name": name, "observed": value, "threshold": threshold,
            "comparison": "<=" if maximum else ">=", "passed": bool(passed),
        })
    return {
        "metrics": {
            "positive": positive_metrics, "negative": negative_metrics,
            "roc_auc": auc, "matched_pair_win": pairwise,
            "powered_stratum_gate": powered,
        },
        "stratified_metrics": _stratified_metrics(rows),
        "gate_evaluation": {
            "passed": all(item["passed"] for item in checks), "checks": checks,
        },
    }


def summarize_control_results(
    manifest: Mapping[str, Any],
    results_by_strut_id: Mapping[int, Mapping[str, Any]],
    *,
    minimum_realized_fraction: float = 0.80,
    minimum_gap_voxels: int = 3,
) -> dict[str, Any]:
    """Build a sealed control artifact with metrics and frozen gate outcomes."""

    validate_control_manifest(manifest)
    frozen_parameters = manifest["parameters"]
    if not np.isclose(
        minimum_realized_fraction,
        frozen_parameters["minimum_realized_fraction"], rtol=0, atol=1e-12,
    ) or minimum_gap_voxels != frozen_parameters["minimum_gap_voxels"]:
        raise StrutControlValidationError("score parameters differ from frozen comparator")
    positive_manifest = {
        int(item["strut_id"]): item
        for item in manifest["positive_controls"] if item["inspectable"]
    }
    negative_manifest = {
        int(item["strut_id"]): item for item in manifest["matched_negative_controls"]
    }
    expected_ids = set(positive_manifest).union(negative_manifest)
    normalized_results = {int(key): value for key, value in results_by_strut_id.items()}
    if set(normalized_results) != expected_ids:
        missing = sorted(expected_ids - set(normalized_results))
        extra = sorted(set(normalized_results) - expected_ids)
        raise StrutControlValidationError(
            f"control results do not match manifest IDs; missing={missing[:5]}, extra={extra[:5]}"
        )
    rows = []
    for strut_id in sorted(expected_ids):
        definition = positive_manifest.get(strut_id, negative_manifest.get(strut_id))
        evidence = normalized_results[strut_id]
        if not isinstance(evidence, Mapping) or "has_error" not in evidence:
            raise StrutControlValidationError(f"control {strut_id} lacks has_error evidence")
        decision = _decision(evidence["has_error"])
        if evidence.get("comparison_applicable", True) is not True:
            raise StrutControlValidationError(f"control {strut_id} is not comparison-applicable")
        row = copy.deepcopy(dict(definition))
        row["has_error"] = decision
        row["raw_anomaly_score"] = raw_anomaly_score(
            evidence,
            minimum_realized_fraction=minimum_realized_fraction,
            minimum_gap_voxels=minimum_gap_voxels,
        )
        row["evidence"] = json_safe(dict(evidence))
        rows.append(row)
    analysis = _derive_control_analysis(rows, manifest)
    artifact = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "manifest_content_sha256": manifest["content_sha256"],
        "provenance": copy.deepcopy(manifest["provenance"]),
        "score_parameters": {
            "minimum_realized_fraction": float(minimum_realized_fraction),
            "minimum_gap_voxels": int(minimum_gap_voxels),
        },
        "rows": rows,
        **analysis,
        "limitations": [
            "CAD-present controls are presumed negatives, not manually proven healthy struts.",
            "CAD omissions test missing-member sensitivity, not broken-member sensitivity.",
            "Raw-score AUC does not replace ternary decision and review-rate gates.",
        ],
    }
    sealed = _sealed(artifact)
    validate_control_artifact_provenance(sealed, manifest)
    return sealed


def validate_control_artifact_provenance(
    artifact: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    expected_provenance: Mapping[str, Any] | None = None,
) -> None:
    """Verify result content, frozen-manifest binding, sources, and row IDs."""

    validate_control_manifest(manifest, expected_provenance=expected_provenance)
    if not isinstance(artifact, Mapping) or artifact.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise StrutControlValidationError("unsupported control-result schema")
    if artifact.get("content_sha256") != _content_hash(artifact):
        raise StrutControlValidationError("control-result content hash mismatch")
    if artifact.get("manifest_content_sha256") != manifest.get("content_sha256"):
        raise StrutControlValidationError("control result is bound to a different manifest")
    if artifact.get("provenance") != manifest.get("provenance"):
        raise StrutControlValidationError("control-result provenance mismatch")
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        raise StrutControlValidationError("control-result rows must be an array")
    result_ids = [int(item["strut_id"]) for item in rows]
    expected_ids = {
        int(item["strut_id"])
        for item in manifest["positive_controls"] if item["inspectable"]
    }.union(
        int(item["strut_id"]) for item in manifest["matched_negative_controls"]
    )
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != expected_ids:
        raise StrutControlValidationError("control-result row IDs do not match manifest")
    score_parameters = artifact.get("score_parameters")
    if not isinstance(score_parameters, Mapping):
        raise StrutControlValidationError("control-result score parameters are missing")
    frozen = manifest["parameters"]
    minimum_realized = float(score_parameters.get("minimum_realized_fraction", np.nan))
    minimum_gap = score_parameters.get("minimum_gap_voxels")
    if (not np.isclose(minimum_realized, frozen["minimum_realized_fraction"], rtol=0, atol=1e-12)
            or minimum_gap != frozen["minimum_gap_voxels"]):
        raise StrutControlValidationError("control-result score parameters are not frozen")
    definitions = {
        int(item["strut_id"]): item
        for item in manifest["positive_controls"] if item["inspectable"]
    }
    definitions.update({
        int(item["strut_id"]): item for item in manifest["matched_negative_controls"]
    })
    for row in rows:
        strut_id = int(row["strut_id"])
        definition = definitions[strut_id]
        for key, expected in definition.items():
            if json_safe(row.get(key)) != json_safe(expected):
                raise StrutControlValidationError(f"control-result row {strut_id} changed {key!r}")
        evidence = row.get("evidence")
        if not isinstance(evidence, Mapping) or "has_error" not in evidence:
            raise StrutControlValidationError(f"control-result row {strut_id} lacks evidence")
        if evidence.get("comparison_applicable", True) is not True:
            raise StrutControlValidationError(f"control-result row {strut_id} is not applicable")
        if _decision(row.get("has_error")) != _decision(evidence["has_error"]):
            raise StrutControlValidationError(f"control-result row {strut_id} decision mismatch")
        expected_score = raw_anomaly_score(
            evidence, minimum_realized_fraction=minimum_realized,
            minimum_gap_voxels=int(minimum_gap),
        )
        actual_score = row.get("raw_anomaly_score")
        score_matches = actual_score is None and expected_score is None
        if actual_score is not None and expected_score is not None:
            score_matches = bool(np.isclose(actual_score, expected_score, rtol=0, atol=1e-12))
        if not score_matches:
            raise StrutControlValidationError(f"control-result row {strut_id} raw score mismatch")
    derived = _derive_control_analysis(rows, manifest)
    for key in ("metrics", "stratified_metrics", "gate_evaluation"):
        if json_safe(artifact.get(key)) != json_safe(derived[key]):
            raise StrutControlValidationError(f"control-result derived {key} mismatch")
