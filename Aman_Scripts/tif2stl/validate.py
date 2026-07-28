"""Validate a CT TIFF stack against its STL design mesh.

Pipeline: Otsu-segment the raw CT volume (streamed, downsampled grid), recover
the design->CT similarity transform from the design and registered lattice
JSONs (junction ids correspond record-for-record), map the STL through that
transform, voxelize it onto the CT grid, and score the overlap.  Artifacts are
written deterministically through ``Components.reporting``.

Run:
    conda run -n DSC python Aman_Scripts/tif2stl/validate.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.asset_io import inspect_stl, inspect_tiff, read_tiff  # noqa: E402
from Components.coordinates import compose_transforms  # noqa: E402
from Components.lattice_graph import load_lattice_graph  # noqa: E402
from Components.paths import data_path, output_path  # noqa: E402
from Components.reporting import (  # noqa: E402
    atomic_write_bytes,
    build_manifest,
    json_safe,
    write_csv,
    write_json,
)
from Components.segmentation import threshold_mask  # noqa: E402
from Components.tiff_mesh import (  # noqa: E402
    otsu_threshold_from_histogram,
    streaming_integer_histogram,
)
from Components.coordinates import apply_transform  # noqa: E402
from tif2stl.metrics import (  # noqa: E402
    fraction_inside_mask,
    mask_overlap,
    per_slab_overlap,
    window_slices_zyx,
)
from tif2stl.registration import (  # noqa: E402
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
    stl_to_design_matrix,
)
from tif2stl.stl_geometry import (  # noqa: E402
    read_stl_triangles,
    stl_enclosed_volume,
    triangle_surface_points,
)
from tif2stl.voxelize import voxelize_stl  # noqa: E402


NOMINAL_PITCH_MM = 0.0581
SLAB_FIELDS = ("z_start", "z_stop", "ct_voxels", "stl_voxels", "intersection_voxels", "dice")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    missing = data_path("missing_struts")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tiff",
        default=str(missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"),
    )
    parser.add_argument("--stl", default=str(missing / "stls" / "0.5.stl"))
    parser.add_argument("--design-json", default=str(missing / "octet_truss_9x9x9.json"))
    parser.add_argument(
        "--registered-json",
        default=str(missing / "registered_jsons" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"),
    )
    parser.add_argument("--output-dir", default=None, help="default: Aman_Scripts/outputs/tif2stl")
    parser.add_argument("--downsample", type=int, default=2, help="native voxels per grid cell")
    parser.add_argument("--threshold", type=float, default=None, help="default: streaming Otsu")
    parser.add_argument("--design-span", type=float, default=18.0, help="design lattice units per axis")
    parser.add_argument("--mm-per-design-unit", type=float, default=None,
                        help="default: STL bounding-box X extent / design span")
    parser.add_argument("--stl-rotation", default="auto",
                        help="STL->design axis orientation: 'auto' scores all 24 proper "
                             "cube rotations against the CT mask; or a name like '+x+z-y'")
    parser.add_argument("--tolerance-cells", type=int, default=1,
                        help="dilation radius (grid cells) for tolerant containment metrics")
    parser.add_argument("--slab-depth", type=int, default=32, help="grid cells per CSV slab row")
    parser.add_argument("--min-dice", type=float, default=0.0, help="strict-Dice gate")
    parser.add_argument("--max-rms", type=float, default=1.0,
                        help="registration RMS gate, CT voxels")
    parser.add_argument("--max-outside-fraction", type=float, default=0.15,
                        help="gate on STL surface points landing outside the CT grid")
    parser.add_argument("--max-grid-voxels", type=int, default=400_000_000)
    parser.add_argument("--no-fill", action="store_true", help="score the STL shell only")
    parser.add_argument("--no-overlays", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.downsample < 1:
        parser.error("--downsample must be >= 1")
    if arguments.tolerance_cells < 0:
        parser.error("--tolerance-cells must be >= 0")
    return arguments


def native_foreground_count(histogram: np.ndarray, offset: int, threshold: float) -> int:
    """Count native voxels with value >= threshold straight from the histogram."""

    first_value = int(threshold) if float(threshold).is_integer() else int(np.ceil(threshold))
    first_index = max(0, first_value - offset)
    if first_index >= histogram.size:
        return 0
    return int(histogram[first_index:].sum())


def build_ct_mask(volume: np.ndarray, threshold: float, downsample: int) -> np.ndarray:
    """Threshold a strided (every ``downsample``-th voxel) view of the volume."""

    z_size = volume.shape[0]
    slices = []
    for z_index in range(0, z_size, downsample):
        page = np.asarray(volume[z_index, ::downsample, ::downsample])
        slices.append(threshold_mask(page, threshold).astype(bool))
    return np.stack(slices)


def sample_stl_points_mm(
    path: str,
    *,
    chunk_faces: int = 100_000,
    chunk_stride: int = 10,
    max_points: int = 2_000_000,
) -> np.ndarray:
    """Deterministic sparse sample of STL surface points (native STL units)."""

    collected = []
    for index, chunk in enumerate(read_stl_triangles(path, chunk_faces=chunk_faces)):
        if index % chunk_stride == 0:
            collected.append(triangle_surface_points(chunk))
    sample = np.concatenate(collected)
    if len(sample) > max_points:
        sample = sample[:: int(np.ceil(len(sample) / max_points))]
    return sample


def score_orientations(
    ct_mask: np.ndarray,
    sample_mm: np.ndarray,
    *,
    fit_matrix: np.ndarray,
    mm_per_design_unit: float,
    stl_center: tuple[float, float, float],
    design_center: tuple[float, float, float],
    downsample: int,
) -> list[dict[str, object]]:
    """Score every proper cube rotation by CT-mask hit fraction, best first."""

    half_cell = downsample / 2.0
    rows = []
    for name, rotation in proper_cube_rotations():
        matrix = compose_transforms(
            stl_to_design_matrix(
                mm_per_design_unit=mm_per_design_unit,
                stl_center_xyz=stl_center,
                design_center_xyz=design_center,
                rotation=rotation,
            ),
            fit_matrix,
        )
        score = fraction_inside_mask(
            ct_mask,
            apply_transform(sample_mm, matrix),
            origin_xyz=(-half_cell, -half_cell, -half_cell),
            pitch=float(downsample),
        )
        rows.append({"name": name, "score": score})
    return sorted(rows, key=lambda row: -row["score"])


def write_overlays(directory: Path, ct: np.ndarray, stl: np.ndarray, downsample: int) -> list[Path]:
    """RGB agreement maps: red = CT only, green = STL only, yellow = both."""

    from PIL import Image

    written: list[Path] = []
    z_size, y_size, _ = ct.shape
    panels = [("z", int(z_size * fraction)) for fraction in (0.25, 0.5, 0.75)]
    panels.append(("y", y_size // 2))
    for axis, index in panels:
        if axis == "z":
            ct_plane, stl_plane = ct[index], stl[index]
        else:
            ct_plane, stl_plane = ct[:, index, :], stl[:, index, :]
        rgb = np.zeros((*ct_plane.shape, 3), dtype=np.uint8)
        rgb[ct_plane & ~stl_plane] = (235, 70, 70)
        rgb[~ct_plane & stl_plane] = (70, 205, 95)
        rgb[ct_plane & stl_plane] = (245, 225, 80)
        destination = directory / f"overlay_{axis}{index * downsample:04d}.png"
        Image.fromarray(rgb).save(destination)
        written.append(destination)
    return written


def render_markdown(report: dict, overlays: list[Path]) -> str:
    registration = report["registration"]
    orientation = report["orientation"]
    metrics = report["metrics"]
    window = metrics["lattice_window"]
    volumes = report["volumes"]
    gates = report["gates"]
    lines = [
        "# TIFF vs STL validation",
        "",
        f"Generated {report['generated_utc']} in {report['runtime_seconds']} s.",
        "",
        "## Inputs",
        "",
        f"- CT TIFF: `{report['inputs']['tiff']['path']}` "
        f"{report['inputs']['tiff']['shape']} {report['inputs']['tiff']['dtype']}",
        f"- STL: `{report['inputs']['stl']['path']}` "
        f"({report['inputs']['stl']['triangles']:,} triangles)",
        f"- Design JSON: `{report['inputs']['design_json']}`",
        f"- Registered JSON: `{report['inputs']['registered_json']}`",
        "",
        "## Registration (design units -> CT voxels)",
        "",
        f"- Scale: {registration['scale_voxels_per_design_unit']:.6f} voxels/design unit",
        f"- Rotation: {registration['rotation_degrees']:.4f} deg; translation "
        f"{[round(value, 3) for value in registration['translation_voxels_xyz']]} voxels",
        f"- Residuals over {registration['point_count']} junction pairs: "
        f"RMS {registration['rms_error_voxels']:.3e} vox, max {registration['max_error_voxels']:.3e} vox",
        f"- Implied voxel pitch: {registration['implied_pitch_um']:.3f} um "
        f"(nominal {registration['nominal_pitch_um']} um, "
        f"deviation {registration['pitch_deviation_percent']:+.2f}%)",
        f"- STL modelling orientation: `{orientation['chosen']}` "
        f"({orientation['requested']!r} requested), CT hit fraction "
        f"{orientation['hit_fraction']:.4f} over {orientation['sample_points']:,} "
        f"sampled surface points; runner-up "
        f"`{orientation['top_candidates'][1]['name']}` at "
        f"{orientation['top_candidates'][1]['score']:.4f}",
        "",
        "## Agreement",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| lattice-window Dice | {window['dice']:.4f} |",
        f"| lattice-window IoU | {window['iou']:.4f} |",
        f"| lattice-window CT within design (+{metrics['tolerance_cells']} cell) "
        f"| {window['ct_in_design_tolerant']:.4f} |",
        f"| lattice-window design realized in CT (+{metrics['tolerance_cells']} cell) "
        f"| {window['design_in_ct_tolerant']:.4f} |",
        f"| full-grid strict Dice | {metrics['strict']['dice']:.4f} |",
        f"| full-grid strict IoU | {metrics['strict']['iou']:.4f} |",
        f"| full-grid CT within design (+{metrics['tolerance_cells']} cell) "
        f"| {metrics['ct_in_design_tolerant']:.4f} |",
        f"| full-grid design realized in CT (+{metrics['tolerance_cells']} cell) "
        f"| {metrics['design_in_ct_tolerant']:.4f} |",
        f"| CT material volume | {volumes['ct_mm3_implied_pitch']:,.0f} mm^3 |",
        f"| STL solid volume | {volumes['stl_enclosed_mm3']:,.0f} mm^3 |",
        f"| voxelized STL volume | {volumes['voxelized_stl_mm3']:,.0f} mm^3 |",
        "",
        "## Gates",
        "",
    ]
    for name, gate in gates.items():
        verdict = "PASS" if gate["passed"] else "FAIL"
        lines.append(f"- **{verdict}** {name}: {gate['detail']}")
    lines += [
        "",
        "## Notes",
        "",
        "- The registered JSON already stores junction positions in CT voxel",
        "  coordinates; the design->CT transform is fitted from id-matched",
        "  junction pairs, never tuned against the segmentation.",
        "- The STL models its build plates on its +-Y axis, while the scanned",
        "  part's plates lie at the CT +-Z extremes; the orientation search",
        "  scores all 24 proper cube rotations against the CT mask to recover",
        "  this modelling-frame rotation (near-cubic lattices make bounding",
        "  boxes useless for it).",
        "- The CT field of view crops the build plates; crop-opened solids",
        "  cannot be morphologically filled, so full-grid metrics and the",
        "  voxelized STL volume undercount plate material. The lattice-window",
        "  numbers (junction bounding box + 2 cells) are the meaningful ones.",
        "- CT solid volume differs from the design volume because printed struts",
        "  differ from nominal thickness; that gap is signal, not error.",
        "",
        "## Overlays",
        "",
        "Red = CT only, green = STL only, yellow = agreement.",
        "",
    ]
    lines += [f"![{path.stem}]({path.name})" for path in overlays]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    started = time.perf_counter()
    output_directory = (
        Path(arguments.output_dir).expanduser().resolve()
        if arguments.output_dir
        else output_path("tif2stl", create=True)
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    tiff_metadata = inspect_tiff(arguments.tiff)
    if tiff_metadata.axes != "ZYX":
        raise ValueError(f"expected a ZYX TIFF series, got axes {tiff_metadata.axes!r}")
    stl_metadata = inspect_stl(arguments.stl)
    if stl_metadata.triangles == 0 or stl_metadata.bounding_box_min is None:
        raise ValueError(f"STL has no geometry: {arguments.stl}")
    print(f"[1/7] inputs ok: TIFF {tiff_metadata.shape} {tiff_metadata.dtype}, "
          f"STL {stl_metadata.triangles:,} triangles", flush=True)

    volume = read_tiff(arguments.tiff)
    if arguments.threshold is None:
        histogram, offset = streaming_integer_histogram(volume)
        threshold = otsu_threshold_from_histogram(histogram, offset=offset)
        threshold_source = "otsu"
    else:
        histogram, offset = streaming_integer_histogram(volume)
        threshold = float(arguments.threshold)
        threshold_source = "user"
    native_foreground = native_foreground_count(histogram, offset, threshold)
    print(f"[2/7] threshold {threshold} ({threshold_source}); native foreground "
          f"{native_foreground:,} voxels", flush=True)

    ct_mask = build_ct_mask(volume, threshold, arguments.downsample)
    print(f"[3/7] CT grid {ct_mask.shape} at downsample {arguments.downsample}: "
          f"{int(ct_mask.sum()):,} occupied cells", flush=True)

    design_graph = load_lattice_graph(arguments.design_json)
    registered_graph = load_lattice_graph(arguments.registered_json)
    design_points, registered_points = paired_junction_positions(design_graph, registered_graph)
    fit = similarity_transform(design_points, registered_points)

    if arguments.mm_per_design_unit is None:
        extent_x = stl_metadata.bounding_box_max[0] - stl_metadata.bounding_box_min[0]
        mm_per_design_unit = extent_x / arguments.design_span
        mm_source = "stl_bbox_x_extent"
    else:
        mm_per_design_unit = float(arguments.mm_per_design_unit)
        mm_source = "user"
    implied_pitch_mm = mm_per_design_unit / fit.scale
    stl_center = tuple(
        (low + high) / 2.0
        for low, high in zip(stl_metadata.bounding_box_min, stl_metadata.bounding_box_max)
    )
    half_span = arguments.design_span / 2.0
    design_center = (half_span, half_span, half_span)
    print(f"[4/7] registration: {fit.scale:.4f} vox/unit, rot "
          f"{fit.rotation_angle_degrees:.4f} deg, rms {fit.rms_error:.2e} vox; "
          f"implied pitch {implied_pitch_mm * 1000:.3f} um", flush=True)

    sample_mm = sample_stl_points_mm(arguments.stl)
    orientation_scores = score_orientations(
        ct_mask, sample_mm,
        fit_matrix=fit.matrix,
        mm_per_design_unit=mm_per_design_unit,
        stl_center=stl_center,
        design_center=design_center,
        downsample=arguments.downsample,
    )
    rotations = dict(proper_cube_rotations())
    requested = "+x+y+z" if arguments.stl_rotation == "identity" else arguments.stl_rotation
    if requested == "auto":
        chosen_name = str(orientation_scores[0]["name"])
    elif requested in rotations:
        chosen_name = requested
    else:
        raise ValueError(
            f"unknown --stl-rotation {arguments.stl_rotation!r}; "
            f"use 'auto', 'identity', or one of {sorted(rotations)}"
        )
    chosen_score = next(row["score"] for row in orientation_scores if row["name"] == chosen_name)
    stl_to_design = stl_to_design_matrix(
        mm_per_design_unit=mm_per_design_unit,
        stl_center_xyz=stl_center,
        design_center_xyz=design_center,
        rotation=rotations[chosen_name],
    )
    stl_to_voxel = compose_transforms(stl_to_design, fit.matrix)
    print(f"[5/7] orientation {chosen_name} "
          f"(hit fraction {chosen_score:.4f} over {len(sample_mm):,} sample points; "
          f"runner-up {orientation_scores[1]['name']} "
          f"{orientation_scores[1]['score']:.4f})", flush=True)

    half_cell = arguments.downsample / 2.0
    voxelized = voxelize_stl(
        arguments.stl,
        pitch=float(arguments.downsample),
        transform=stl_to_voxel,
        origin_xyz=(-half_cell, -half_cell, -half_cell),
        grid_shape_zyx=ct_mask.shape,
        fill=not arguments.no_fill,
        max_grid_voxels=arguments.max_grid_voxels,
    )
    print(f"[6/7] voxelized STL: {voxelized.occupied_voxels:,} cells, "
          f"{voxelized.points_outside:,}/{voxelized.surface_points:,} surface points "
          f"outside the grid", flush=True)

    strict = mask_overlap(ct_mask, voxelized.grid)
    window = window_slices_zyx(
        registered_points,
        origin_xyz=(-half_cell, -half_cell, -half_cell),
        pitch=float(arguments.downsample),
        shape_zyx=ct_mask.shape,
        padding_cells=2,
    )
    ct_window = ct_mask[window]
    stl_window = voxelized.grid[window]
    window_strict = mask_overlap(ct_window, stl_window)
    if arguments.tolerance_cells > 0:
        from scipy import ndimage

        stl_dilated = ndimage.binary_dilation(voxelized.grid, iterations=arguments.tolerance_cells)
        ct_dilated = ndimage.binary_dilation(ct_mask, iterations=arguments.tolerance_cells)
        ct_in_design = mask_overlap(ct_mask, stl_dilated).a_in_b_fraction
        design_in_ct = mask_overlap(ct_dilated, voxelized.grid).b_in_a_fraction
        window_ct_in_design = mask_overlap(ct_window, stl_dilated[window]).a_in_b_fraction
        window_design_in_ct = mask_overlap(ct_dilated[window], stl_window).b_in_a_fraction
    else:
        ct_in_design = strict.a_in_b_fraction
        design_in_ct = strict.b_in_a_fraction
        window_ct_in_design = window_strict.a_in_b_fraction
        window_design_in_ct = window_strict.b_in_a_fraction
    slab_rows = per_slab_overlap(ct_mask, voxelized.grid, slab_depth=arguments.slab_depth)

    cell_mm = arguments.downsample * implied_pitch_mm
    gates = {
        "registration_rms": {
            "passed": fit.rms_error <= arguments.max_rms,
            "detail": f"{fit.rms_error:.3e} vox <= {arguments.max_rms}",
        },
        "lattice_window_dice": {
            "passed": window_strict.dice >= arguments.min_dice,
            "detail": f"{window_strict.dice:.4f} >= {arguments.min_dice} "
                      f"(full grid: {strict.dice:.4f})",
        },
        "surface_points_in_grid": {
            "passed": voxelized.outside_fraction <= arguments.max_outside_fraction,
            "detail": f"outside fraction {voxelized.outside_fraction:.4f} "
                      f"<= {arguments.max_outside_fraction}",
        },
    }
    report = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {
            "tiff": {
                "path": str(tiff_metadata.path),
                "shape": list(tiff_metadata.shape),
                "dtype": str(tiff_metadata.dtype),
                "axes": tiff_metadata.axes,
            },
            "stl": {
                "path": str(stl_metadata.path),
                "triangles": stl_metadata.triangles,
                "bounding_box_min": list(stl_metadata.bounding_box_min),
                "bounding_box_max": list(stl_metadata.bounding_box_max),
            },
            "design_json": str(Path(arguments.design_json).resolve()),
            "registered_json": str(Path(arguments.registered_json).resolve()),
        },
        "threshold": {"value": threshold, "source": threshold_source},
        "registration": {
            "scale_voxels_per_design_unit": fit.scale,
            "rotation_degrees": fit.rotation_angle_degrees,
            "translation_voxels_xyz": list(fit.translation),
            "rms_error_voxels": fit.rms_error,
            "max_error_voxels": fit.max_error,
            "point_count": fit.point_count,
            "mm_per_design_unit": mm_per_design_unit,
            "mm_per_design_unit_source": mm_source,
            "implied_pitch_um": implied_pitch_mm * 1000.0,
            "nominal_pitch_um": NOMINAL_PITCH_MM * 1000.0,
            "pitch_deviation_percent":
                (implied_pitch_mm / NOMINAL_PITCH_MM - 1.0) * 100.0,
        },
        "orientation": {
            "requested": arguments.stl_rotation,
            "chosen": chosen_name,
            "hit_fraction": chosen_score,
            "sample_points": int(len(sample_mm)),
            "top_candidates": orientation_scores[:3],
        },
        "grid": {
            "downsample": arguments.downsample,
            "shape_zyx": list(ct_mask.shape),
            "cell_mm": cell_mm,
            "ct_cells": strict.a_voxels,
            "stl_cells": strict.b_voxels,
            "stl_filled": voxelized.filled,
        },
        "coverage": {
            "surface_points": voxelized.surface_points,
            "points_outside": voxelized.points_outside,
            "outside_fraction": voxelized.outside_fraction,
        },
        "volumes": {
            "ct_native_foreground_voxels": native_foreground,
            "ct_mm3_implied_pitch": native_foreground * implied_pitch_mm ** 3,
            "ct_mm3_nominal_pitch": native_foreground * NOMINAL_PITCH_MM ** 3,
            "stl_enclosed_mm3": None,
            "voxelized_stl_mm3": strict.b_voxels * cell_mm ** 3,
        },
        "metrics": {
            "strict": {
                "dice": strict.dice,
                "iou": strict.iou,
                "ct_in_design": strict.a_in_b_fraction,
                "design_in_ct": strict.b_in_a_fraction,
            },
            "tolerance_cells": arguments.tolerance_cells,
            "ct_in_design_tolerant": ct_in_design,
            "design_in_ct_tolerant": design_in_ct,
            "lattice_window": {
                "slices_zyx": [[part.start, part.stop] for part in window],
                "dice": window_strict.dice,
                "iou": window_strict.iou,
                "ct_in_design_tolerant": window_ct_in_design,
                "design_in_ct_tolerant": window_design_in_ct,
            },
        },
        "gates": gates,
    }
    report["volumes"]["stl_enclosed_mm3"] = stl_enclosed_volume(arguments.stl)
    report["runtime_seconds"] = round(time.perf_counter() - started, 1)

    overlays: list[Path] = []
    if not arguments.no_overlays:
        overlays = write_overlays(output_directory, ct_mask, voxelized.grid, arguments.downsample)
    report_json = write_json(output_directory / "report.json", json_safe(report))
    slabs_csv = write_csv(output_directory / "slab_overlap.csv", slab_rows, SLAB_FIELDS)
    report_md = atomic_write_bytes(
        output_directory / "report.md",
        render_markdown(report, overlays).encode("utf-8"),
    )
    artifacts = [report_json, slabs_csv, report_md, *overlays]
    write_json(
        output_directory / "manifest.json",
        build_manifest(artifacts, root=output_directory),
    )
    print(f"[7/7] wrote {len(artifacts) + 1} artifacts to {output_directory}", flush=True)

    all_passed = all(gate["passed"] for gate in gates.values())
    print(f"window dice {window_strict.dice:.4f} (full grid {strict.dice:.4f}) | "
          f"window CT-in-design(+tol) {window_ct_in_design:.4f} | "
          f"window design-in-CT(+tol) {window_design_in_ct:.4f}")
    print("VALIDATION " + ("PASS" if all_passed else "FAIL"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
