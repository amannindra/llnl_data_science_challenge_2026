#!/usr/bin/env python3
"""Compact direct STL-to-native-TIFF strut metrology with visual evidence."""

from __future__ import annotations

import argparse
import gc
import math
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.asset_io import inspect_tiff, load_json, read_tiff  # noqa: E402
from Components.cad_strut_mapping import (  # noqa: E402
    build_registered_centerline_atlas,
    identify_skin_embedded_struts,
    infer_specimen_cad_omissions,
    sample_stl_surface_against_atlas,
)
from Components.coordinates import apply_transform  # noqa: E402
from Components.ct_surface_metrology import (  # noqa: E402
    refine_rigid_registration,
    sample_stl_surface_by_area,
)
from Components.lattice_graph import load_lattice_graph  # noqa: E402
from Components.paths import data_path, output_path  # noqa: E402
from Components.reporting import (  # noqa: E402
    atomic_write_bytes,
    file_sha256,
    json_safe,
    write_json,
)
from Components.strut_metrology import (  # noqa: E402
    classify_strut_measurement,
    measure_strut_cross_sections,
)
from Components.strut_pipeline import (  # noqa: E402
    build_augmented_lattice_payload,
    build_stl_to_ct_registration,
)


ALGORITHM_VERSION = "compact-subvoxel-strut-metrology-v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    missing = data_path("missing_struts")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl", default=str(missing / "stls" / "0.5.stl"))
    parser.add_argument("--complete-stl", default=str(missing / "stls" / "0.stl"))
    parser.add_argument(
        "--tiff",
        default=str(
            missing / "tif_stacks"
            / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
        ),
    )
    parser.add_argument("--design-json", default=str(missing / "octet_truss_9x9x9.json"))
    parser.add_argument(
        "--registered-json",
        default=str(
            missing / "registered_jsons"
            / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(output_path("simple_strut_metrology"))
    )
    parser.add_argument("--registration-only", action="store_true")
    parser.add_argument(
        "--limit-struts", type=int, default=None,
        help="evenly spaced CAD-expected diagnostic members; omit for all members",
    )
    parser.add_argument("--surface-samples", type=int, default=30_000)
    parser.add_argument("--registration-iterations", type=int, default=12)
    parser.add_argument("--minimum-registration-contrast", type=float, default=1000.0)
    parser.add_argument("--maximum-registration-translation", type=float, default=3.0)
    parser.add_argument("--maximum-registration-rotation-deg", type=float, default=0.5)
    parser.add_argument("--minimum-registration-valid-fraction", type=float, default=0.20)
    parser.add_argument("--minimum-local-contrast", type=float, default=1000.0)
    parser.add_argument("--minimum-axial-fraction", type=float, default=0.80)
    parser.add_argument("--maximum-gap-voxels", type=float, default=3.0)
    parser.add_argument("--radial-tolerance-voxels", type=float, default=0.75)
    parser.add_argument("--centerline-tolerance-voxels", type=float, default=0.75)
    parser.add_argument("--panel-count", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--maximum-rss-gib", type=float, default=2.5)
    arguments = parser.parse_args(argv)
    if arguments.limit_struts is not None and arguments.limit_struts < 1:
        parser.error("--limit-struts must be positive")
    if arguments.surface_samples < 100:
        parser.error("--surface-samples must be >= 100")
    if arguments.registration_iterations < 1:
        parser.error("--registration-iterations must be positive")
    if arguments.panel_count < 0:
        parser.error("--panel-count must be nonnegative")
    if arguments.workers < 1:
        parser.error("--workers must be positive")
    if arguments.maximum_rss_gib <= 0.0:
        parser.error("--maximum-rss-gib must be positive")
    return arguments


def _rss_bytes() -> int:
    try:
        import psutil
    except ImportError:
        return 0
    return int(psutil.Process().memory_info().rss)


def _rss_gate(maximum_bytes: int, stage: str) -> int:
    current = _rss_bytes()
    if current > maximum_bytes:
        raise MemoryError(
            f"RSS {current:,} exceeds {maximum_bytes:,} bytes during {stage}"
        )
    return current


def _correct_atlas(atlas: dict[str, Any], correction: np.ndarray) -> dict[str, Any]:
    result = dict(atlas)
    for key in ("endpoint0_xyz", "endpoint1_xyz"):
        result[key] = apply_transform(np.asarray(atlas[key]), correction)
    centers = np.asarray(atlas["centers_xyz"])
    result["centers_xyz"] = apply_transform(
        centers.reshape(-1, 3), correction
    ).reshape(centers.shape)
    result["length_voxels"] = np.linalg.norm(
        result["endpoint1_xyz"] - result["endpoint0_xyz"], axis=1
    )
    return result


def _radius_profile(distances: np.ndarray) -> np.ndarray | None:
    values = np.asarray(distances, dtype=np.float64)
    finite = np.isfinite(values) & (values > 0.5) & (values < 10.0)
    if values.ndim != 1 or np.count_nonzero(finite) < max(5, int(0.70 * len(values))):
        return None
    indices = np.arange(len(values), dtype=np.float64)
    interpolated = np.interp(indices, indices[finite], values[finite])
    if not np.isfinite(interpolated).all():
        return None
    return interpolated


def _evenly_spaced_ids(ids: np.ndarray, limit: int | None) -> np.ndarray:
    if limit is None or limit >= len(ids):
        return ids.copy()
    indices = np.rint(np.linspace(0, len(ids) - 1, limit)).astype(np.int64)
    return ids[np.unique(indices)]


def _not_applicable(*, cad_absent: bool, skin_embedded: bool) -> dict[str, Any]:
    if skin_embedded:
        reason = (
            "cad_absent_and_skin_embedded_unobservable"
            if cad_absent else "skin_embedded_unobservable"
        )
    else:
        reason = "intentionally_absent_in_specimen_cad"
    return {
        "stl_expected_present": not cad_absent,
        "cad_intentionally_absent": cad_absent,
        "skin_embedded": skin_embedded,
        "comparison_applicable": False,
        "measurement_valid": False,
        "has_error": None,
        "review_required": False,
        "decision_reason": reason,
        "failed_checks": [],
    }


def _projection_line(endpoint0: np.ndarray, endpoint1: np.ndarray, axes: tuple[int, int]):
    return (
        [endpoint0[axes[0]], endpoint1[axes[0]]],
        [endpoint0[axes[1]], endpoint1[axes[1]]],
    )


def _render_panel(
    volume: np.ndarray,
    strut_id: int,
    evidence: dict[str, Any],
    destination: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first = np.asarray(evidence["endpoint0_xyz_voxels"], dtype=np.float64)
    second = np.asarray(evidence["endpoint1_xyz_voxels"], dtype=np.float64)
    expected = np.asarray(evidence.get("station_expected_radius_voxels", [4.0]))
    padding = float(np.nanmax(expected) + 4.0)
    lower = np.maximum(np.floor(np.minimum(first, second) - padding).astype(int), 0)
    upper = np.minimum(
        np.ceil(np.maximum(first, second) + padding).astype(int) + 1,
        np.asarray(volume.shape[::-1]),
    )
    crop = np.asarray(
        volume[lower[2]:upper[2], lower[1]:upper[1], lower[0]:upper[0]]
    )
    if not crop.size:
        raise ValueError(f"strut {strut_id} panel crop is empty")
    low, high = np.percentile(crop, (2.0, 99.5))
    if high <= low:
        high = low + 1.0
    normalized = np.clip((crop.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    local_first, local_second = first - lower, second - lower
    figure, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    projections = (
        (normalized.max(axis=0), (0, 1), "XY max projection"),
        (normalized.max(axis=1), (0, 2), "XZ max projection"),
        (normalized.max(axis=2), (1, 2), "YZ max projection"),
    )
    for axis, (image, coordinate_axes, title) in zip(axes[0], projections):
        axis.imshow(image, cmap="gray", origin="lower", vmin=0.0, vmax=1.0)
        x_line, y_line = _projection_line(local_first, local_second, coordinate_axes)
        axis.plot(x_line, y_line, color="cyan", linewidth=1.5, label="corrected CAD axis")
        axis.set_title(title)
        axis.legend(loc="upper right", fontsize=7)
    axial = np.asarray(evidence["station_axial_position_voxels"])
    support = np.asarray(evidence["station_supported"], dtype=bool)
    axes[1, 0].step(axial, support.astype(float), where="mid", color="tab:blue")
    axes[1, 0].set_ylim(-0.1, 1.1)
    axes[1, 0].set_title("Axial support used by decision")
    axes[1, 0].set_xlabel("distance along strut (voxels)")
    observed = np.asarray([
        np.nan if item is None else float(item)
        for item in evidence["station_observed_radius_voxels"]
    ])
    axes[1, 1].plot(axial, expected, label="STL expected radius", color="black")
    axes[1, 1].plot(axial, observed, label="CT ISO-50 radius", color="tab:orange")
    axes[1, 1].set_title("Radial surface comparison")
    axes[1, 1].set_xlabel("distance along strut (voxels)")
    axes[1, 1].legend(fontsize=7)
    center = np.asarray([
        np.nan if item is None else float(item)
        for item in evidence["station_center_displacement_voxels"]
    ])
    contrast = np.asarray([
        np.nan if item is None else float(item)
        for item in evidence["station_local_contrast"]
    ])
    axes[1, 2].plot(axial, center, color="tab:red", label="center displacement")
    contrast_axis = axes[1, 2].twinx()
    contrast_axis.plot(axial, contrast, color="tab:green", alpha=0.6, label="local contrast")
    axes[1, 2].set_title("Location and observability")
    axes[1, 2].set_xlabel("distance along strut (voxels)")
    axes[1, 2].set_ylabel("displacement (voxels)")
    contrast_axis.set_ylabel("intensity contrast")
    figure.suptitle(
        f"Strut {strut_id} | has_error={evidence.get('has_error')} | "
        f"reason={evidence.get('decision_reason')}",
        fontsize=12,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=140)
    plt.close(figure)


def _panel_ids(results: dict[int, dict[str, Any]], count: int) -> list[int]:
    applicable = [
        (strut_id, evidence) for strut_id, evidence in results.items()
        if evidence.get("comparison_applicable") is True
    ]
    ranked = sorted(
        applicable,
        key=lambda item: (
            0 if item[1].get("has_error") is True else 1 if item[1].get("has_error") is None else 2,
            item[0],
        ),
    )
    return [strut_id for strut_id, _evidence in ranked[:count]]


def _write_markdown_summary(
    path: Path,
    comparison: dict[str, Any],
    panel_paths: list[Path],
) -> None:
    summary = comparison["summary"]
    registration = comparison["registration_refinement"]
    lines = [
        "# Compact STL-to-TIFF strut metrology",
        "",
        "## Result scope",
        "",
        "`0.5.stl` is the specimen CAD used for printing. Its deliberate omissions are",
        "reported as non-applicable design absences; only additional TIFF mismatches are",
        "candidate errors. Missing-versus-broken subtype is not assigned.",
        "",
        "## Registration",
        "",
        f"- Independent rigid correction: {registration['rotation_degrees']:.6f} degrees, "
        f"{registration['translation_magnitude_voxels']:.6f} voxels.",
        f"- Held-out median absolute local ISO-50 offset: "
        f"{registration['after_held_out']['median_absolute_offset_voxels']} voxels.",
        f"- Conservative registration uncertainty used by decisions: "
        f"{registration['registration_uncertainty_voxels']} voxels.",
        "",
        "## Counts",
        "",
        f"- Processed: {summary['processed_count']:,}",
        f"- Error candidates: {summary['error_candidate_count']:,}",
        f"- Clearly inside tolerance: {summary['healthy_count']:,}",
        f"- Review-required: {summary['undecided_count']:,}",
        f"- Non-applicable design/skin members: {summary['not_applicable_count']:,}",
        "",
        "## Evidence panels",
        "",
        "Max projections can visually hide a gap; the axial support/radius plots below",
        "each projection are the actual decision evidence.",
        "",
    ]
    for panel in panel_paths:
        lines.extend((f"![{panel.stem}]({panel.as_posix()})", ""))
    lines.extend((
        "## Limitations", "",
        "- Synthetic tests establish numerical behavior, not real defect accuracy.",
        "- Registration uncertainty includes CT noise and manufacturing surface variation.",
        "- Candidate errors require scientific/manual review; no subtype is claimed.",
        "- The segmented TIFF is not used as ground truth.", "",
    ))
    atomic_write_bytes(path, "\n".join(lines).encode("utf-8"), create_parents=True)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    started = time.perf_counter()
    directory = Path(arguments.output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    maximum_rss = int(arguments.maximum_rss_gib * 1024 ** 3)
    tiff_metadata = inspect_tiff(arguments.tiff)
    if tiff_metadata.axes != "ZYX" or len(tiff_metadata.shape) != 3:
        raise RuntimeError(f"expected a ZYX TIFF, got {tiff_metadata.axes} {tiff_metadata.shape}")
    if not tiff_metadata.memory_mappable:
        raise RuntimeError("TIFF must be memory-mappable; refusing a full-volume allocation")
    _rss_gate(maximum_rss, "input validation")
    print(f"TIFF header valid: {tiff_metadata.shape} {tiff_metadata.dtype}")
    initial = build_stl_to_ct_registration(
        arguments.stl, arguments.design_json, arguments.registered_json,
        mm_per_design_unit=2.28,
        nominal_strut_diameter_mm=0.424,
    )
    print(f"sampling {arguments.surface_samples:,} STL surface points by physical area")
    surface = sample_stl_surface_by_area(
        arguments.stl, initial["matrix"], sample_count=arguments.surface_samples
    )
    volume = read_tiff(arguments.tiff, mmap_mode="r")
    print("refining a bounded rigid correction directly against native TIFF intensities")
    refinement = refine_rigid_registration(
        volume,
        np.asarray(surface["points_xyz"]),
        np.asarray(surface["normals_xyz"]),
        maximum_iterations=arguments.registration_iterations,
        minimum_end_contrast=arguments.minimum_registration_contrast,
        maximum_translation_voxels=arguments.maximum_registration_translation,
        maximum_rotation_degrees=arguments.maximum_registration_rotation_deg,
        minimum_valid_fraction=arguments.minimum_registration_valid_fraction,
    )
    corrected_transform = np.asarray(refinement["correction_matrix"]) @ np.asarray(initial["matrix"])
    hashes = {
        "specimen_stl": file_sha256(arguments.stl),
        "complete_stl": file_sha256(arguments.complete_stl),
        "tiff": file_sha256(arguments.tiff),
        "registered_json": file_sha256(arguments.registered_json),
        "design_json": file_sha256(arguments.design_json),
    }
    registration_report = {
        "algorithm_version": ALGORITHM_VERSION,
        "scope": "independent small rigid refinement; JSON fit is initialization only",
        "inputs_sha256": hashes,
        "tiff_shape_zyx": list(tiff_metadata.shape),
        "initial_registration": json_safe(initial),
        "surface_sampling": {
            key: json_safe(value) for key, value in surface.items()
            if key not in {"points_xyz", "normals_xyz"}
        },
        "refinement": json_safe(refinement),
        "corrected_stl_to_ct_matrix": corrected_transform.tolist(),
        "elapsed_seconds": time.perf_counter() - started,
        "peak_observed_rss_bytes": _rss_gate(maximum_rss, "registration refinement"),
    }
    registration_path = write_json(
        directory / "registration_report.json", registration_report, create_parents=True
    )
    print(f"wrote {registration_path}")
    if arguments.registration_only:
        return 0

    del surface
    gc.collect()
    registered_graph = load_lattice_graph(arguments.registered_json)
    design_graph = load_lattice_graph(arguments.design_json)
    source_payload = load_json(arguments.registered_json)
    atlas = build_registered_centerline_atlas(registered_graph, axial_bins=45)
    corrected_atlas = _correct_atlas(atlas, np.asarray(refinement["correction_matrix"]))
    print("mapping complete CAD triangles to corrected strut stations")
    complete_surface = sample_stl_surface_against_atlas(
        arguments.complete_stl,
        corrected_transform,
        corrected_atlas,
        workers=arguments.workers,
        retain_nearest_points=False,
    )
    print("mapping specimen CAD triangles and retaining its expected surface radii")
    specimen_surface = sample_stl_surface_against_atlas(
        arguments.stl,
        corrected_transform,
        corrected_atlas,
        workers=arguments.workers,
        retain_nearest_points=True,
    )
    intent = infer_specimen_cad_omissions(
        complete_surface, specimen_surface, corrected_atlas["strut_ids"]
    )
    removed_ids = {int(value) for value in intent["removed_strut_ids"]}
    skin_ids = {
        int(value) for value in identify_skin_embedded_struts(design_graph)
    }
    strut_ids = np.asarray(corrected_atlas["strut_ids"], dtype=np.int64)
    present_ids = np.asarray([
        value for value in strut_ids if int(value) not in removed_ids and int(value) not in skin_ids
    ], dtype=np.int64)
    selected_ids = _evenly_spaced_ids(present_ids, arguments.limit_struts)
    selected_set = {int(value) for value in selected_ids}
    row_by_id = {int(value): index for index, value in enumerate(strut_ids)}
    results: dict[int, dict[str, Any]] = {}
    if arguments.limit_struts is None:
        for raw_id in strut_ids:
            strut_id = int(raw_id)
            if strut_id in removed_ids or strut_id in skin_ids:
                results[strut_id] = _not_applicable(
                    cad_absent=strut_id in removed_ids,
                    skin_embedded=strut_id in skin_ids,
                )
    print(f"measuring {len(selected_ids):,} CAD-expected struts from local native-TIFF crops")
    for number, raw_id in enumerate(selected_ids, start=1):
        strut_id = int(raw_id)
        row = row_by_id[strut_id]
        radius = _radius_profile(specimen_surface["nearest_surface_distance"][row])
        if radius is None:
            evidence = {
                "stl_expected_present": True,
                "cad_intentionally_absent": False,
                "skin_embedded": False,
                "comparison_applicable": True,
                "measurement_valid": False,
                "has_error": None,
                "review_required": True,
                "decision_reason": "insufficient_specimen_stl_radius_samples",
                "failed_checks": [],
            }
        else:
            measurement = measure_strut_cross_sections(
                volume,
                corrected_atlas["endpoint0_xyz"][row],
                corrected_atlas["endpoint1_xyz"][row],
                radius,
                minimum_local_contrast=arguments.minimum_local_contrast,
            )
            decision = classify_strut_measurement(
                measurement,
                registration_uncertainty_voxels=float(
                    refinement["registration_uncertainty_voxels"]
                ),
                minimum_axial_fraction=arguments.minimum_axial_fraction,
                maximum_gap_voxels=arguments.maximum_gap_voxels,
                manufacturing_radial_tolerance_voxels=arguments.radial_tolerance_voxels,
                manufacturing_centerline_tolerance_voxels=arguments.centerline_tolerance_voxels,
            )
            evidence = {
                **measurement,
                **decision,
                "stl_expected_present": True,
                "cad_intentionally_absent": False,
                "skin_embedded": False,
                "comparison_applicable": True,
                "expected_radius_median_voxels": float(np.median(radius)),
                "registration_uncertainty_voxels": float(
                    refinement["registration_uncertainty_voxels"]
                ),
            }
        results[strut_id] = evidence
        if number % 100 == 0 or number == len(selected_ids):
            rss = _rss_gate(maximum_rss, f"strut {number}")
            print(f"measured {number:,}/{len(selected_ids):,}; RSS={rss / 1024**3:.2f} GiB")
    comparison_metadata = {
        "schema_version": "compact-stl-tiff-strut-map.v1",
        "algorithm_version": ALGORITHM_VERSION,
        "comparison": "0.5.stl specimen CAD versus raw native-resolution TIFF",
        "design_absence_semantics": (
            "members deliberately removed from 0.5.stl are expected absences, not CT errors"
        ),
        "coordinate_frame": {
            "geometry_order": "xyz", "tiff_index_order": "zyx",
            "units": "native_ct_voxel", "tiff_shape_zyx": list(tiff_metadata.shape),
        },
        "inputs_sha256": hashes,
        "initial_registration": json_safe(initial),
        "registration_refinement": json_safe(refinement),
        "corrected_stl_to_ct_matrix": corrected_transform.tolist(),
        "cad_identity": {
            "intentionally_absent_count": int(intent["removed_count"]),
            "split_threshold": float(intent["split_threshold"]),
            "cluster_gap": float(intent["cluster_gap"]),
            "skin_embedded_count": len(skin_ids),
        },
        "parameters": {
            "minimum_local_contrast": arguments.minimum_local_contrast,
            "minimum_axial_fraction": arguments.minimum_axial_fraction,
            "maximum_gap_voxels": arguments.maximum_gap_voxels,
            "manufacturing_radial_tolerance_voxels": arguments.radial_tolerance_voxels,
            "manufacturing_centerline_tolerance_voxels": arguments.centerline_tolerance_voxels,
            "native_resolution": True,
            "whole_volume_stl_mask": False,
            "defect_subtype_assigned": False,
        },
        "limitations": [
            "candidate labels are not manually confirmed ground truth",
            "max-projection panels can hide depth-specific gaps",
            "STL radius stations use dense triangle vertex/centroid surface samples",
        ],
    }
    payload = build_augmented_lattice_payload(
        source_payload,
        results,
        comparison_metadata,
        require_all_struts=arguments.limit_struts is None,
    )
    suffix = "" if arguments.limit_struts is None else f"_diagnostic_{len(selected_set)}"
    output_json = write_json(
        directory / f"strut_metrology{suffix}.json", payload, create_parents=True
    )
    panel_directory = directory / f"panels{suffix}"
    panel_paths = []
    for strut_id in _panel_ids(results, arguments.panel_count):
        evidence = results[strut_id]
        if "station_axial_position_voxels" not in evidence:
            continue
        destination = panel_directory / f"strut_{strut_id:05d}.png"
        _render_panel(volume, strut_id, evidence, destination)
        panel_paths.append(destination.relative_to(directory))
    comparison = payload["_comparison"]
    write_json(directory / f"summary{suffix}.json", comparison, create_parents=True)
    _write_markdown_summary(
        directory / f"summary{suffix}.md", comparison, panel_paths
    )
    write_json(
        panel_directory / "index.json",
        {"strut_ids": [int(path.stem.split("_")[-1]) for path in panel_paths]},
        create_parents=True,
    )
    print(f"wrote {output_json}")
    print(f"wrote {len(panel_paths)} evidence panels")
    print(f"finished in {time.perf_counter() - started:.2f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
