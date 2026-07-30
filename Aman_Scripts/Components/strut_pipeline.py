"""End-to-end direct comparison of a specimen STL with a raw CT TIFF.

The registered lattice JSON is an address book, not the comparison target: it
supplies stable strut IDs and endpoints in native CT XYZ coordinates.  Expected
surface geometry comes from ``0.5.stl`` and observed material comes from the
TIFF.  ``0.stl`` is used only to resolve which IDs the monolithic specimen STL
intentionally omits.
"""

from __future__ import annotations

import copy
import gc
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .asset_io import inspect_stl, inspect_tiff, load_json, read_tiff
from .cad_strut_mapping import (
    build_registered_centerline_atlas,
    identify_skin_embedded_struts,
    infer_specimen_cad_omissions,
    sample_stl_surface_against_atlas,
)
from .coordinates import compose_transforms
from .lattice_graph import (
    connected_components,
    load_lattice_graph,
    weld_coincident_nodes,
)
from .reporting import file_sha256, json_safe, write_json, write_json_lines
from .strut_comparison import compare_strut_local
from .stl_surface_index import STLSurfaceIndex
from .tiff_mesh import otsu_threshold_from_histogram, streaming_integer_histogram
from tif2stl.registration import (
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
    stl_to_design_matrix,
)


SCHEMA_VERSION = "stl-tiff-strut-error-map.v1"
ALGORITHM_VERSION = "native-surface-corridor-v3"
REQUIRED_STL_ROTATION = "+z+x+y"
SKIN_NORMAL_DESIGN_AXIS = 2


class StrutPipelineError(RuntimeError):
    """Raised when an end-to-end comparison fails a scientific safety gate."""


def build_stl_to_ct_registration(
    specimen_stl_path: str | Path,
    design_json_path: str | Path,
    registered_json_path: str | Path,
    *,
    design_span: float = 18.0,
    mm_per_design_unit: float = 2.28,
    nominal_strut_diameter_mm: float = 0.424,
    maximum_surface_extent_residual_mm: float = 0.10,
    stl_rotation: str = REQUIRED_STL_ROTATION,
    maximum_fit_rms_voxels: float = 1e-6,
) -> dict[str, Any]:
    """Recover the exact composite STL-mm -> native-CT-voxel transform."""

    if not (np.isfinite(design_span) and design_span > 0.0):
        raise StrutPipelineError("design_span must be positive")
    if not (np.isfinite(mm_per_design_unit) and mm_per_design_unit > 0.0):
        raise StrutPipelineError("mm_per_design_unit must be positive")
    if not (np.isfinite(nominal_strut_diameter_mm) and nominal_strut_diameter_mm > 0.0):
        raise StrutPipelineError("nominal_strut_diameter_mm must be positive")
    if not (
        np.isfinite(maximum_surface_extent_residual_mm)
        and maximum_surface_extent_residual_mm >= 0.0
    ):
        raise StrutPipelineError("maximum_surface_extent_residual_mm must be nonnegative")
    metadata = inspect_stl(specimen_stl_path)
    if metadata.bounding_box_min is None or metadata.bounding_box_max is None:
        raise StrutPipelineError("specimen STL has no measurable bounds")
    rotations = dict(proper_cube_rotations())
    if stl_rotation not in rotations:
        raise StrutPipelineError(
            f"unknown STL rotation {stl_rotation!r}; expected one of {sorted(rotations)}"
        )
    design_graph = load_lattice_graph(design_json_path)
    registered_graph = load_lattice_graph(registered_json_path)
    design_points, registered_points = paired_junction_positions(design_graph, registered_graph)
    fit = similarity_transform(design_points, registered_points)
    if fit.rms_error > maximum_fit_rms_voxels:
        raise StrutPipelineError(
            f"design->CT fit RMS {fit.rms_error:.6g} exceeds {maximum_fit_rms_voxels} voxels"
        )
    lower = np.asarray(metadata.bounding_box_min, dtype=np.float64)
    upper = np.asarray(metadata.bounding_box_max, dtype=np.float64)
    # The graph spans node centres, while the STL bounding box spans the outer
    # solid surface.  Dividing the latter by ``design_span`` therefore counts
    # roughly one extra strut diameter and biases scale high.  Fisher/Tran et
    # al. specify a 4.56 mm unit-cell edge; the graph advances two coordinate
    # units per cell, hence the physical 2.28 mm/design-unit default.
    lattice_extents_xz = (upper - lower)[[0, 2]]
    expected_surface_extent = design_span * mm_per_design_unit + nominal_strut_diameter_mm
    surface_extent_residuals = lattice_extents_xz - expected_surface_extent
    if np.any(np.abs(surface_extent_residuals) > maximum_surface_extent_residual_mm):
        raise StrutPipelineError(
            "STL X/Z surface extents disagree with the physical design scale: "
            f"residuals={surface_extent_residuals.tolist()} mm"
        )
    stl_center = (lower + upper) / 2.0
    design_center = np.repeat(design_span / 2.0, 3)
    stl_to_design = stl_to_design_matrix(
        mm_per_design_unit=mm_per_design_unit,
        stl_center_xyz=tuple(stl_center),
        design_center_xyz=tuple(design_center),
        rotation=rotations[stl_rotation],
    )
    matrix = compose_transforms(stl_to_design, fit.matrix)
    return {
        "matrix": matrix,
        "stl_rotation": stl_rotation,
        "mm_per_design_unit": mm_per_design_unit,
        "mm_per_design_unit_source": "paper 4.56 mm cell edge / 2 graph units",
        "nominal_strut_diameter_mm": nominal_strut_diameter_mm,
        "stl_surface_extent_xz_mm": lattice_extents_xz,
        "expected_surface_extent_xz_mm": [expected_surface_extent, expected_surface_extent],
        "surface_extent_residual_xz_mm": surface_extent_residuals,
        "stl_center_xyz_mm": stl_center,
        "design_to_ct_scale_voxels_per_unit": fit.scale,
        "design_to_ct_rotation_degrees": fit.rotation_angle_degrees,
        "design_to_ct_translation_xyz_voxels": fit.translation,
        "fit_rms_voxels": fit.rms_error,
        "fit_max_voxels": fit.max_error,
        "fit_point_count": fit.point_count,
        "fit_scope": (
            "design-JSON to registered-JSON control points; this residual is "
            "not an independent STL-to-CT image-registration error"
        ),
    }


def _memory_rss_bytes() -> int:
    try:
        import psutil
    except ImportError:  # pragma: no cover - DSC includes psutil
        return 0
    return int(psutil.Process().memory_info().rss)


def prepare_cad_strut_map(
    complete_stl_path: str | Path,
    specimen_stl_path: str | Path,
    registered_json_path: str | Path,
    stl_to_ct_transform: np.ndarray,
    *,
    axial_bins: int = 45,
    endpoint_exclusion_fraction: float = 0.10,
    association_radii_voxels: Sequence[float] = (8.0, 9.0, 10.0),
    retain_complete_surface_points: bool = False,
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Map both CAD meshes onto IDs; optionally retain complete-STL stations."""

    emit = progress or (lambda _message: None)
    graph = load_lattice_graph(registered_json_path)
    atlas = build_registered_centerline_atlas(
        graph,
        axial_bins=axial_bins,
        endpoint_exclusion_fraction=endpoint_exclusion_fraction,
    )
    emit("mapping every complete-STL triangle to registered strut bins")
    complete = sample_stl_surface_against_atlas(
        complete_stl_path,
        stl_to_ct_transform,
        atlas,
        association_radii_voxels=association_radii_voxels,
        workers=workers,
        retain_nearest_points=retain_complete_surface_points,
    )
    emit("mapping every specimen-STL triangle to registered strut bins")
    specimen = sample_stl_surface_against_atlas(
        specimen_stl_path,
        stl_to_ct_transform,
        atlas,
        association_radii_voxels=association_radii_voxels,
        workers=workers,
        retain_nearest_points=False,
    )
    intent = infer_specimen_cad_omissions(
        complete, specimen, atlas["strut_ids"]
    )
    return {
        "atlas": atlas,
        "complete_surface": complete,
        "specimen_surface": specimen,
        "intent": intent,
    }


def _rounded_zyx(point_xyz: Sequence[float]) -> list[int]:
    xyz = np.floor(np.asarray(point_xyz, dtype=np.float64) + 0.5).astype(np.int64)
    return [int(xyz[2]), int(xyz[1]), int(xyz[0])]


def build_augmented_lattice_payload(
    source_payload: Mapping[str, Any],
    strut_results: Mapping[int, Mapping[str, Any]],
    comparison_metadata: Mapping[str, Any],
    *,
    require_all_struts: bool = True,
) -> dict[str, Any]:
    """Copy the registered lattice JSON and attach deterministic evidence."""

    if not isinstance(source_payload, Mapping):
        raise StrutPipelineError("source lattice payload must be an object")
    junctions = copy.deepcopy(source_payload.get("junctions"))
    source_struts = source_payload.get("struts")
    unit_cells = copy.deepcopy(source_payload.get("unit_cells", []))
    if not isinstance(junctions, list) or not isinstance(source_struts, list):
        raise StrutPipelineError("source payload must contain junctions and struts arrays")
    junction_by_id = {int(item["id"]): item for item in junctions}
    source_ids = [int(item["id"]) for item in source_struts]
    if len(source_ids) != len(set(source_ids)):
        raise StrutPipelineError("source strut IDs are not unique")
    result_ids = {int(value) for value in strut_results}
    unknown = result_ids - set(source_ids)
    if unknown:
        raise StrutPipelineError(f"comparison results contain unknown strut IDs: {sorted(unknown)[:5]}")
    missing = set(source_ids) - result_ids
    if require_all_struts and missing:
        raise StrutPipelineError(f"comparison results omit {len(missing)} source struts")

    reserved_evidence_keys = {
        "id", "junction0", "junction1", "unit_cell_edge_idx", "thickness",
        "edge_id", "endpoint0_xyz_voxel", "endpoint1_xyz_voxel",
        "endpoint0_nearest_zyx_index", "endpoint1_nearest_zyx_index",
    }
    augmented = []
    for source in source_struts:
        record = copy.deepcopy(source)
        strut_id = int(record["id"])
        endpoint0 = int(record["junction0"])
        endpoint1 = int(record["junction1"])
        try:
            point0 = list(junction_by_id[endpoint0]["position"])
            point1 = list(junction_by_id[endpoint1]["position"])
        except KeyError as exc:
            raise StrutPipelineError(
                f"strut {strut_id} references missing junction {exc.args[0]}"
            ) from exc
        evidence = dict(strut_results.get(strut_id, {
            "comparison_applicable": True,
            "comparison_valid": False,
            "has_error": None,
            "review_required": True,
            "confidence": 0.0,
            "decision_reason": "not_processed",
        }))
        record.update({
            "edge_id": f"E_N{min(endpoint0, endpoint1):06d}_N{max(endpoint0, endpoint1):06d}",
            "endpoint0_xyz_voxel": point0,
            "endpoint1_xyz_voxel": point1,
            "endpoint0_nearest_zyx_index": _rounded_zyx(point0),
            "endpoint1_nearest_zyx_index": _rounded_zyx(point1),
        })
        # The registered JSON is authoritative for identity and geometry.  A
        # detector result may contain convenience copies of those fields, but
        # it must never be able to replace them in the augmented artifact.
        safe_evidence = {
            key: value for key, value in evidence.items()
            if key not in reserved_evidence_keys
        }
        record.update(json_safe(safe_evidence))
        augmented.append(record)

    processed_count = sum(item.get("decision_reason") != "not_processed" for item in augmented)
    not_processed_count = len(augmented) - processed_count
    applicable = [
        item for item in augmented
        if item.get("comparison_applicable") is True
        and item.get("decision_reason") != "not_processed"
    ]
    not_applicable_count = sum(
        item.get("comparison_applicable") is False for item in augmented
    )
    error_count = sum(item.get("has_error") is True for item in applicable)
    healthy_count = sum(item.get("has_error") is False for item in applicable)
    undecided_count = sum(item.get("has_error") is None for item in applicable)
    absent_count = sum(item.get("stl_expected_present") is False for item in augmented)
    metadata = dict(comparison_metadata)
    metadata["summary"] = {
        "strut_count": len(augmented),
        "processed_count": int(processed_count),
        "not_processed_count": int(not_processed_count),
        "error_candidate_count": int(error_count),
        "healthy_count": int(healthy_count),
        "undecided_count": int(undecided_count),
        "not_applicable_count": int(not_applicable_count),
        "stl_intentionally_absent_count": int(absent_count),
    }
    extras = {
        key: copy.deepcopy(value)
        for key, value in source_payload.items()
        if key not in {"junctions", "struts", "unit_cells", "_comparison"}
    }
    return {
        "_comparison": json_safe(metadata),
        "junctions": junctions,
        "struts": augmented,
        "unit_cells": unit_cells,
        **extras,
    }


def compare_stl_to_tiff_struts(
    specimen_stl_path: str | Path,
    tiff_path: str | Path,
    registered_json_path: str | Path,
    design_json_path: str | Path,
    complete_stl_path: str | Path,
    *,
    output_json_path: str | Path | None = None,
    checkpoint_jsonl_path: str | Path | None = None,
    material_thresholds: Sequence[float] = (38557.0, 40054.0, 41018.0),
    mm_per_design_unit: float = 2.28,
    nominal_strut_diameter_mm: float = 0.424,
    distance_tolerance_voxels: float = 2.0,
    endpoint_exclusion_fraction: float = 0.10,
    minimum_supported_bin_fraction: float = 0.20,
    minimum_gap_voxels: int = 3,
    minimum_realized_fraction: float = 0.80,
    minimum_perturbation_agreement: float = 0.80,
    minimum_local_contrast_fraction: float | None = 0.25,
    limit_struts: int | None = None,
    workers: int = 1,
    maximum_rss_bytes: int = 2_500_000_000,
    checkpoint_every: int = 500,
    progress: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    """Run the complete direct STL-to-TIFF strut comparison."""

    emit = progress or (lambda _message: None)
    started = time.perf_counter()
    peak_rss = _memory_rss_bytes()
    if minimum_local_contrast_fraction is not None and not (
        np.isfinite(minimum_local_contrast_fraction)
        and 0.0 < minimum_local_contrast_fraction <= 1.0
    ):
        raise StrutPipelineError(
            "minimum_local_contrast_fraction must be None or lie in (0, 1]"
        )
    tiff_metadata = inspect_tiff(tiff_path)
    if tiff_metadata.axes != "ZYX" or len(tiff_metadata.shape) != 3:
        raise StrutPipelineError(f"expected a 3D ZYX TIFF, got {tiff_metadata.axes} {tiff_metadata.shape}")
    if not tiff_metadata.memory_mappable:
        raise StrutPipelineError("native TIFF must be memory-mappable; refusing a full allocation")
    if np.dtype(tiff_metadata.dtype).kind not in "ui":
        raise StrutPipelineError(f"expected an integer CT TIFF, got {tiff_metadata.dtype}")
    specimen_metadata = inspect_stl(specimen_stl_path)
    complete_metadata = inspect_stl(complete_stl_path)
    if specimen_metadata.triangles == 0 or complete_metadata.triangles == 0:
        raise StrutPipelineError("both STL files must contain triangles")
    source_payload = load_json(registered_json_path)
    registered_graph = load_lattice_graph(registered_json_path)
    design_graph = load_lattice_graph(design_json_path)
    if len(registered_graph.struts) != 18_468:
        raise StrutPipelineError(
            f"canonical registered graph must contain 18,468 struts, got {len(registered_graph.struts)}"
        )
    if [item.id for item in design_graph.struts] != [item.id for item in registered_graph.struts]:
        raise StrutPipelineError("design and registered graphs do not share the same strut IDs")
    skin_embedded_ids = {
        int(value)
        for value in identify_skin_embedded_struts(
            design_graph, skin_normal_axis=SKIN_NORMAL_DESIGN_AXIS
        )
    }
    welded = weld_coincident_nodes(registered_graph, tolerance=1e-6)
    components = connected_components(welded)
    if len(components) != 1 or welded.dangling_strut_ids or welded.self_loop_strut_ids:
        raise StrutPipelineError("registered graph failed welded-topology validation")
    emit(
        f"inputs valid: TIFF {tiff_metadata.shape} {tiff_metadata.dtype}; "
        f"0.5 STL {specimen_metadata.triangles:,} triangles; 18,468 struts"
    )

    registration = build_stl_to_ct_registration(
        specimen_stl_path,
        design_json_path,
        registered_json_path,
        mm_per_design_unit=mm_per_design_unit,
        nominal_strut_diameter_mm=nominal_strut_diameter_mm,
    )
    emit(
        f"JSON control-point fit valid: {registration['stl_rotation']}, "
        f"rotation {registration['design_to_ct_rotation_degrees']:.6f} deg, "
        f"RMS {registration['fit_rms_voxels']:.3e} voxel"
    )
    cad = prepare_cad_strut_map(
        complete_stl_path,
        specimen_stl_path,
        registered_json_path,
        registration["matrix"],
        axial_bins=45,
        endpoint_exclusion_fraction=endpoint_exclusion_fraction,
        retain_complete_surface_points=True,
        workers=workers,
        progress=emit,
    )
    intent = cad["intent"]
    emit(
        f"CAD identity map: {intent['removed_count']} intentionally absent struts; "
        f"split={intent['split_threshold']:.4f}, gap={intent['cluster_gap']:.4f}"
    )
    peak_rss = max(peak_rss, _memory_rss_bytes())
    if peak_rss > maximum_rss_bytes:
        raise MemoryError(
            f"peak RSS {peak_rss:,} exceeds maximum_rss_bytes={maximum_rss_bytes:,}"
        )

    volume = read_tiff(tiff_path, mmap_mode="r")
    histogram, histogram_offset = streaming_integer_histogram(volume)
    otsu = otsu_threshold_from_histogram(histogram, offset=histogram_offset)
    if abs(float(otsu) - 40054.0) > 2.0:
        raise StrutPipelineError(f"expected real-asset Otsu near 40054, measured {otsu}")
    thresholds = tuple(float(value) for value in material_thresholds)
    if (
        not thresholds
        or not all(np.isfinite(thresholds))
        or any(second <= first for first, second in zip(thresholds, thresholds[1:]))
    ):
        raise StrutPipelineError(
            "material_thresholds must be finite, unique, and strictly increasing"
        )
    central_material_threshold = thresholds[len(thresholds) // 2]
    emit(
        f"native CT mapped; Otsu={otsu:.0f}; thresholds={thresholds}; "
        f"central={central_material_threshold:g}"
    )

    atlas = cad["atlas"]
    removed_ids = {int(value) for value in intent["removed_strut_ids"]}
    strut_ids = np.asarray(atlas["strut_ids"], dtype=np.int64)
    source_struts = registered_graph.strut_by_id()
    junctions = registered_graph.junction_by_id()
    selected_ids = strut_ids if limit_struts is None else strut_ids[: max(0, int(limit_struts))]
    expected_radius_voxels = float(
        0.5
        * nominal_strut_diameter_mm
        / mm_per_design_unit
        * registration["design_to_ct_scale_voxels_per_unit"]
    )
    emit("indexing every transformed specimen-STL triangle for exact local surface queries")
    surface_index = STLSurfaceIndex.from_stl(
        specimen_stl_path,
        transform=registration["matrix"],
        max_index_bytes=min(1_500_000_000, maximum_rss_bytes),
    )
    peak_rss = max(peak_rss, _memory_rss_bytes())
    if peak_rss > maximum_rss_bytes:
        raise MemoryError(
            f"peak RSS {peak_rss:,} exceeds maximum_rss_bytes={maximum_rss_bytes:,}"
        )
    results: dict[int, dict[str, Any]] = {}
    checkpoint_rows: list[dict[str, Any]] = []
    for number, raw_id in enumerate(selected_ids, start=1):
        strut_id = int(raw_id)
        strut = source_struts[strut_id]
        endpoint0 = junctions[strut.junction0].position
        endpoint1 = junctions[strut.junction1].position
        row_index = int(np.searchsorted(strut_ids, strut_id))
        cad_absent = strut_id in removed_ids
        skin_embedded = strut_id in skin_embedded_ids
        if skin_embedded:
            evidence = {
                "stl_expected_present": not cad_absent,
                "stl_expectation_valid": True,
                "cad_intentionally_absent": cad_absent,
                "skin_embedded": True,
                "comparison_applicable": False,
                "comparison_valid": False,
                "has_error": None,
                "review_required": False,
                "confidence": 0.0,
                "decision_reason": (
                    "intentionally_absent_and_skin_embedded_unobservable"
                    if cad_absent
                    else "skin_embedded_unobservable"
                ),
                "cad_coverage_drop": float(intent["median_coverage_drop"][row_index]),
                "ct_to_stl_near_fraction": None,
            }
        elif cad_absent:
            evidence = {
                "stl_expected_present": False,
                "stl_expectation_valid": True,
                "cad_intentionally_absent": True,
                "skin_embedded": False,
                "comparison_applicable": False,
                "comparison_valid": True,
                "has_error": None,
                "review_required": False,
                "confidence": 0.0,
                "decision_reason": "intentionally_absent_in_specimen_stl",
                "cad_coverage_drop": float(intent["median_coverage_drop"][row_index]),
                "ct_to_stl_near_fraction": None,
            }
        else:
            surface_query = surface_index.query_segment_nearest(
                endpoint0,
                endpoint1,
                axial_step=1.0,
                endpoint_exclusion_fraction=endpoint_exclusion_fraction,
                candidates_per_bucket=32,
                workers=workers,
            )
            evidence = compare_strut_local(
                volume,
                endpoint0,
                endpoint1,
                surface_query.nearest_surface_points_xyz,
                thresholds=thresholds,
                central_threshold=central_material_threshold,
                distance_tolerance_voxels=distance_tolerance_voxels,
                endpoint_exclusion_fraction=endpoint_exclusion_fraction,
                minimum_supported_bin_fraction=minimum_supported_bin_fraction,
                minimum_gap_voxels=minimum_gap_voxels,
                minimum_realized_fraction=minimum_realized_fraction,
                minimum_perturbation_agreement=minimum_perturbation_agreement,
                minimum_local_contrast_fraction=minimum_local_contrast_fraction,
                expected_present_override=True,
                expected_radius_voxels=expected_radius_voxels,
                stl_surface_distances_voxels=surface_query.nearest_surface_distances,
            )
            evidence["cad_intentionally_absent"] = False
            evidence["skin_embedded"] = False
            evidence["cad_coverage_drop"] = float(intent["median_coverage_drop"][row_index])
        results[strut_id] = evidence
        checkpoint_rows.append({"strut_id": strut_id, **json_safe(evidence)})
        if checkpoint_jsonl_path and (
            number % checkpoint_every == 0 or number == len(selected_ids)
        ):
            write_json_lines(checkpoint_jsonl_path, checkpoint_rows, create_parents=True)
        if number % max(1, checkpoint_every) == 0 or number == len(selected_ids):
            peak_rss = max(peak_rss, _memory_rss_bytes())
            emit(
                f"compared {number:,}/{len(selected_ids):,} struts; "
                f"errors={sum(item.get('has_error') is True for item in results.values()):,}; "
                f"undecided={sum(item.get('comparison_applicable') is True and item.get('has_error') is None for item in results.values()):,}; "
                f"not-applicable={sum(item.get('comparison_applicable') is False for item in results.values()):,}; "
                f"RSS={peak_rss / (1024 ** 3):.2f} GiB"
            )
            if peak_rss > maximum_rss_bytes:
                raise MemoryError(
                    f"peak RSS {peak_rss:,} exceeds maximum_rss_bytes={maximum_rss_bytes:,}"
                )

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "comparison": "0.5.stl expected surface versus raw TIFF material",
        "registered_json_role": "strut identity and native-CT endpoints only",
        "complete_stl_role": "CAD strut-ID calibration only; not compared with CT",
        "coordinate_frame": {
            "geometry_order": "xyz",
            "tiff_index_order": "zyx",
            "units": "native_ct_voxel",
            "tiff_shape_zyx": list(tiff_metadata.shape),
        },
        "inputs": {
            "specimen_stl": str(Path(specimen_stl_path).resolve()),
            "complete_stl_reference": str(Path(complete_stl_path).resolve()),
            "tiff": str(Path(tiff_path).resolve()),
            "registered_json": str(Path(registered_json_path).resolve()),
            "design_json": str(Path(design_json_path).resolve()),
        },
        "input_sha256": {
            "specimen_stl": file_sha256(specimen_stl_path),
            "complete_stl_reference": file_sha256(complete_stl_path),
            "tiff": file_sha256(tiff_path),
            "registered_json": file_sha256(registered_json_path),
            "design_json": file_sha256(design_json_path),
        },
        "registration": json_safe(registration),
        "cad_identity_mapping": {
            "association_radii_voxels": [8.0, 9.0, 10.0],
            "intentionally_absent_count": intent["removed_count"],
            "split_threshold": intent["split_threshold"],
            "cluster_gap": intent["cluster_gap"],
        },
        "observability": {
            "skin_normal_design_axis": "z",
            "skin_embedded_source_strut_count": len(skin_embedded_ids),
            "rule": (
                "both design endpoints lie in the minimum-Z or maximum-Z skin plane"
            ),
        },
        "parameters": {
            "material_thresholds": list(thresholds),
            "central_material_threshold": central_material_threshold,
            "measured_otsu_threshold": otsu,
            "mm_per_design_unit": mm_per_design_unit,
            "nominal_strut_diameter_mm": nominal_strut_diameter_mm,
            "expected_strut_radius_voxels": expected_radius_voxels,
            "native_resolution": True,
            "triangle_decimation": False,
            "exact_point_to_triangle_surface_queries": True,
            "distance_tolerance_voxels": distance_tolerance_voxels,
            "endpoint_exclusion_fraction": endpoint_exclusion_fraction,
            "minimum_supported_bin_fraction": minimum_supported_bin_fraction,
            "minimum_gap_voxels": minimum_gap_voxels,
            "minimum_realized_fraction": minimum_realized_fraction,
            "minimum_perturbation_agreement": minimum_perturbation_agreement,
            "minimum_local_contrast_fraction": minimum_local_contrast_fraction,
            "ct_to_stl_near_fraction_status": "not used in v1 missing/broken screen",
        },
        "resource_policy": {
            "maximum_process_rss_bytes": maximum_rss_bytes,
            "native_tiff_memory_mapped": True,
            "whole_volume_stl_mask": False,
        },
        "result_semantics": {
            "has_error_true": "automatically supported STL-expected strut mismatch candidate",
            "has_error_false": "stable match for a strut expected by 0.5.stl",
            "has_error_null": (
                "inspect comparison_applicable and review_required: null can mean "
                "review-required uncertainty or geometry that is not independently inspectable"
            ),
            "not_applicable": (
                "the ID is absent from 0.5.stl or its member is embedded in a solid skin"
            ),
            "subtype": "not classified in v1",
            "confidence": "uncalibrated deterministic stability score, not a probability",
        },
    }
    payload = build_augmented_lattice_payload(
        source_payload,
        results,
        metadata,
        require_all_struts=limit_struts is None,
    )
    if output_json_path is not None:
        write_json(output_json_path, payload, create_parents=True)
        emit(f"wrote {Path(output_json_path).resolve()}")
    emit(
        f"comparison finished in {time.perf_counter() - started:.2f} s; "
        f"peak measured RSS {peak_rss / (1024 ** 3):.2f} GiB"
    )
    # Drop large mapping arrays promptly for notebook callers that keep payload.
    del cad, surface_index
    gc.collect()
    return payload


__all__ = [
    "ALGORITHM_VERSION",
    "SCHEMA_VERSION",
    "StrutPipelineError",
    "build_augmented_lattice_payload",
    "build_stl_to_ct_registration",
    "compare_stl_to_tiff_struts",
    "prepare_cad_strut_map",
]
