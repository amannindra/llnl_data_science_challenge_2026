#!/usr/bin/env python3
"""Export visual, metric-specific TIFF-vs-STL comparisons for MeshLab.

The numerical values are exact voxel counts in the lattice-window region.  PLY
layers are deterministic samples of those exact sets, limited so MeshLab stays
interactive.  Open one `.mlp` project at a time and use MeshLab's layer panel
to toggle colored evidence layers.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
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
from Components.reporting import json_safe, write_json  # noqa: E402
from Components.tiff_mesh import (  # noqa: E402
    otsu_threshold_from_histogram,
    streaming_integer_histogram,
)
from tif2stl.meshlab_export import (  # noqa: E402
    PointLayer,
    export_mask_layer,
    merge_colored_points_ply,
    write_meshlab_project,
)
from tif2stl.metrics import mask_overlap, window_slices_zyx  # noqa: E402
from tif2stl.registration import (  # noqa: E402
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
    stl_to_design_matrix,
)
from tif2stl.validate import build_ct_mask  # noqa: E402
from tif2stl.voxelize import voxelize_stl  # noqa: E402


MESHLAB_APP = Path("/Applications/MeshLab2025.07.app")
COLORS = {
    "exact_overlap": (245, 225, 80),
    "ct_only": (235, 70, 70),
    "stl_only": (70, 205, 95),
    "ct_near_design": (80, 190, 255),
    "ct_far_design": (235, 70, 70),
    "design_realized": (245, 225, 80),
    "design_unrealized": (70, 205, 95),
    "stl_reference": (90, 220, 120),
    "ct_reference": (220, 220, 225),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    missing = data_path("missing_struts")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tiff",
        default=str(
            missing
            / "tif_stacks"
            / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
        ),
    )
    parser.add_argument("--stl", default=str(missing / "stls" / "0.5.stl"))
    parser.add_argument(
        "--design-json", default=str(missing / "octet_truss_9x9x9.json")
    )
    parser.add_argument(
        "--registered-json",
        default=str(
            missing
            / "registered_jsons"
            / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(output_path("tif2stl_plate", "meshlab_metrics", create=False)),
    )
    parser.add_argument("--downsample", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--design-span", type=float, default=18.0)
    parser.add_argument("--stl-rotation", default="+z+x+y")
    parser.add_argument("--tolerance-cells", type=int, default=1)
    parser.add_argument("--window-padding-cells", type=int, default=2)
    parser.add_argument("--max-points-per-layer", type=int, default=200_000)
    parser.add_argument(
        "--open-meshlab",
        action="store_true",
        help="open the exact-Dice project after export",
    )
    arguments = parser.parse_args(argv)
    if arguments.downsample < 1:
        parser.error("--downsample must be >= 1")
    if arguments.tolerance_cells < 0:
        parser.error("--tolerance-cells must be >= 0")
    if arguments.window_padding_cells < 0:
        parser.error("--window-padding-cells must be >= 0")
    if arguments.max_points_per_layer < 1:
        parser.error("--max-points-per-layer must be >= 1")
    return arguments


def _window_offset(slices_zyx: tuple[slice, slice, slice]) -> tuple[int, int, int]:
    return tuple(int(part.start or 0) for part in slices_zyx)


def _layer(
    directory: Path,
    filename: str,
    mask_zyx: np.ndarray,
    label: str,
    color_name: str,
    *,
    offset_zyx: tuple[int, int, int],
    downsample: int,
    max_points: int,
    note: str,
    sampling_stride: int | None,
) -> PointLayer:
    return export_mask_layer(
        mask_zyx,
        destination=directory / filename,
        label=label,
        color_rgb=COLORS[color_name],
        offset_zyx=offset_zyx,
        native_voxels_per_cell=downsample,
        max_points=max_points,
        metric_note=note,
        sampling_stride=sampling_stride,
    )


def _shared_sampling_stride(
    masks: tuple[np.ndarray, ...],
    *,
    max_points_per_layer: int,
) -> int:
    """Return one display stride shared by exclusive classes of one metric.

    Independent per-class caps would make the three MeshLab colors look equally
    common even when their true voxel counts differ.  A common stride preserves
    each class's relative density while still limiting every individual layer.
    """

    if not masks:
        raise ValueError("at least one metric mask is required")
    largest_class = max(int(np.count_nonzero(mask)) for mask in masks)
    return max(1, math.ceil(largest_class / max_points_per_layer))


def _write_markdown(
    path: Path,
    *,
    exact_dice: float,
    ct_near_design: float,
    design_realized: float,
    tolerance_cells: int,
    layers: list[PointLayer],
    project_names: list[str],
    direct_views: dict[str, int],
) -> None:
    rows = [
        "# MeshLab TIFF vs STL metric viewer",
        "",
        "Each percentage below was calculated from all downsampled voxels in the lattice-window region. The PLY files contain deterministic display samples, so MeshLab remains responsive without changing the metric. Within each colored metric partition, every layer uses the same stride, preserving the source-count proportions in the visible clouds.",
        "",
        f"For the exact comparison, the yellow layer is labelled Dice {exact_dice:.2%}, but yellow's share of the red+yellow+green union is IoU rather than Dice. The union-share is recorded in `metrics.json`; use the yellow layer label for the Dice value.",
        "",
        "| Direct MeshLab file | What to view | Exact lattice-window metric |",
        "| --- | --- | ---: |",
        f"| `01_exact_dice_{exact_dice:.2%}.ply` | yellow exact overlap; red CT-only; green STL-only | Dice = {exact_dice:.2%} |",
        f"| `02_ct_within_design_{ct_near_design:.2%}.ply` | blue CT within tolerance of STL; red CT farther away | CT within STL +{tolerance_cells} cell = {ct_near_design:.2%} |",
        f"| `03_design_realized_{design_realized:.2%}.ply` | yellow STL supported by CT; green STL not supported | STL realized in CT +{tolerance_cells} cell = {design_realized:.2%} |",
        "",
        "## How to inspect",
        "",
        "1. Open one direct `.ply` file in MeshLab (File → Import Mesh); these are the recommended viewer artifacts.",
        "2. The PLY header comments retain the exact metric and source counts; `metrics.json` is the complete machine-readable record.",
        "3. Set Render → Point Size higher if individual points are hard to see.",
        "4. Interpret red/green as a discrepancy to investigate, not automatically as a defect: segmentation, thickness variation, tolerance, and cropped plates all contribute.",
        "",
        "## Display-layer provenance",
        "",
        "| PLY layer | Exact source voxels | Display points | Sampling stride |",
        "| --- | ---: | ---: | ---: |",
    ]
    rows.extend(
        f"| `{layer.path.name}` | {layer.source_voxel_count:,} | {layer.sampled_point_count:,} | {layer.sampling_stride} |"
        for layer in layers
    )
    rows += [
        "",
        "## Direct-view PLYs",
        "",
        "| File | Display points |",
        "| --- | ---: |",
    ]
    rows.extend(f"| `{name}` | {count:,} |" for name, count in direct_views.items())
    rows += ["", "Optional MeshLab projects: " + ", ".join(f"`{name}`" for name in project_names), ""]
    path.write_text("\n".join(rows), encoding="utf-8")


def export_metrics(arguments: argparse.Namespace) -> dict[str, object]:
    """Build exact mask metrics and MeshLab projects from the same plate baseline."""

    started = time.perf_counter()
    output_directory = Path(arguments.output_dir).expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    metadata = inspect_tiff(arguments.tiff)
    if metadata.axes != "ZYX":
        raise ValueError(f"expected a ZYX TIFF, got {metadata.axes!r}")
    stl_metadata = inspect_stl(arguments.stl)
    print(f"[1/6] inputs: TIFF {metadata.shape} and STL {stl_metadata.triangles:,} triangles")

    volume = read_tiff(arguments.tiff)
    if arguments.threshold is None:
        histogram, offset = streaming_integer_histogram(volume)
        threshold = otsu_threshold_from_histogram(histogram, offset=offset)
        threshold_source = "otsu"
    else:
        threshold = float(arguments.threshold)
        threshold_source = "user"
    ct_mask = build_ct_mask(volume, threshold, arguments.downsample)
    del volume
    print(f"[2/6] CT mask: {ct_mask.shape} at {threshold:g} ({threshold_source})")

    design = load_lattice_graph(arguments.design_json)
    registered = load_lattice_graph(arguments.registered_json)
    design_points, registered_points = paired_junction_positions(design, registered)
    fit = similarity_transform(design_points, registered_points)
    extent_x = stl_metadata.bounding_box_max[0] - stl_metadata.bounding_box_min[0]
    stl_center = tuple(
        (low + high) / 2.0
        for low, high in zip(stl_metadata.bounding_box_min, stl_metadata.bounding_box_max)
    )
    rotations = dict(proper_cube_rotations())
    if arguments.stl_rotation not in rotations:
        raise ValueError(
            f"unknown --stl-rotation {arguments.stl_rotation!r}; choose one of {sorted(rotations)}"
        )
    stl_to_voxel = compose_transforms(
        stl_to_design_matrix(
            mm_per_design_unit=extent_x / arguments.design_span,
            stl_center_xyz=stl_center,
            design_center_xyz=(arguments.design_span / 2.0,) * 3,
            rotation=rotations[arguments.stl_rotation],
        ),
        fit.matrix,
    )
    half_cell = arguments.downsample / 2.0
    stl_mask = voxelize_stl(
        arguments.stl,
        pitch=float(arguments.downsample),
        transform=stl_to_voxel,
        origin_xyz=(-half_cell, -half_cell, -half_cell),
        grid_shape_zyx=ct_mask.shape,
    ).grid
    print(f"[3/6] STL voxelized with {arguments.stl_rotation}; registration RMS {fit.rms_error:.2e} vox")

    window = window_slices_zyx(
        registered_points,
        origin_xyz=(-half_cell, -half_cell, -half_cell),
        pitch=float(arguments.downsample),
        shape_zyx=ct_mask.shape,
        padding_cells=arguments.window_padding_cells,
    )
    offset_zyx = _window_offset(window)
    ct_window = ct_mask[window]
    stl_window = stl_mask[window]
    del ct_mask, stl_mask

    exact = mask_overlap(ct_window, stl_window)
    from scipy import ndimage

    stl_dilated = ndimage.binary_dilation(
        stl_window, iterations=arguments.tolerance_cells
    )
    ct_dilated = ndimage.binary_dilation(
        ct_window, iterations=arguments.tolerance_cells
    )
    exact_overlap = ct_window & stl_window
    exact_ct_only = ct_window & ~stl_window
    exact_stl_only = stl_window & ~ct_window
    ct_near_design = ct_window & stl_dilated
    ct_far_design = ct_window & ~stl_dilated
    design_realized = stl_window & ct_dilated
    design_unrealized = stl_window & ~ct_dilated
    print(
        f"[4/6] exact Dice {exact.dice:.4f}; CT near STL {ct_near_design.sum() / exact.a_voxels:.4f}; "
        f"STL realized {design_realized.sum() / exact.b_voxels:.4f}"
    )

    note = "Metrics use every voxel in the lattice-window region; PLY points are display samples only."
    exact_stride = _shared_sampling_stride(
        (exact_overlap, exact_ct_only, exact_stl_only),
        max_points_per_layer=arguments.max_points_per_layer,
    )
    ct_stride = _shared_sampling_stride(
        (ct_near_design, ct_far_design),
        max_points_per_layer=arguments.max_points_per_layer,
    )
    design_stride = _shared_sampling_stride(
        (design_realized, design_unrealized),
        max_points_per_layer=arguments.max_points_per_layer,
    )
    layers = [
        _layer(output_directory, "exact_overlap_yellow.ply", exact_overlap,
               f"Exact overlap (yellow) | lattice-window Dice {exact.dice:.2%}", "exact_overlap",
               offset_zyx=offset_zyx, downsample=arguments.downsample,
               max_points=arguments.max_points_per_layer, note=note, sampling_stride=exact_stride),
        _layer(output_directory, "exact_ct_only_red.ply", exact_ct_only,
               "Exact mismatch: CT only (red)", "ct_only", offset_zyx=offset_zyx,
               downsample=arguments.downsample, max_points=arguments.max_points_per_layer, note=note,
               sampling_stride=exact_stride),
        _layer(output_directory, "exact_stl_only_green.ply", exact_stl_only,
               "Exact mismatch: STL only (green)", "stl_only", offset_zyx=offset_zyx,
               downsample=arguments.downsample, max_points=arguments.max_points_per_layer, note=note,
               sampling_stride=exact_stride),
        _layer(output_directory, "ct_near_design_blue.ply", ct_near_design,
               f"CT within STL +{arguments.tolerance_cells} cell (blue) | {ct_near_design.sum() / exact.a_voxels:.2%}",
               "ct_near_design", offset_zyx=offset_zyx, downsample=arguments.downsample,
               max_points=arguments.max_points_per_layer, note=note, sampling_stride=ct_stride),
        _layer(output_directory, "ct_far_design_red.ply", ct_far_design,
               f"CT farther than STL +{arguments.tolerance_cells} cell (red) | {ct_far_design.sum() / exact.a_voxels:.2%}",
               "ct_far_design", offset_zyx=offset_zyx, downsample=arguments.downsample,
               max_points=arguments.max_points_per_layer, note=note, sampling_stride=ct_stride),
        _layer(output_directory, "ct_reference_gray.ply", ct_window,
               "CT reference (gray)", "ct_reference", offset_zyx=offset_zyx,
               downsample=arguments.downsample, max_points=arguments.max_points_per_layer, note=note,
               sampling_stride=None),
        _layer(output_directory, "design_realized_yellow.ply", design_realized,
               f"STL realized in CT +{arguments.tolerance_cells} cell (yellow) | {design_realized.sum() / exact.b_voxels:.2%}",
               "design_realized", offset_zyx=offset_zyx, downsample=arguments.downsample,
               max_points=arguments.max_points_per_layer, note=note, sampling_stride=design_stride),
        _layer(output_directory, "design_unrealized_green.ply", design_unrealized,
               f"STL not realized in CT +{arguments.tolerance_cells} cell (green) | {design_unrealized.sum() / exact.b_voxels:.2%}",
               "design_unrealized", offset_zyx=offset_zyx, downsample=arguments.downsample,
               max_points=arguments.max_points_per_layer, note=note, sampling_stride=design_stride),
        _layer(output_directory, "stl_reference_green.ply", stl_window,
               "STL reference (green)", "stl_reference", offset_zyx=offset_zyx,
               downsample=arguments.downsample, max_points=arguments.max_points_per_layer, note=note,
               sampling_stride=None),
    ]
    projects = {
        "01_exact_dice.mlp": layers[0:3],
        "02_ct_within_design.mlp": [layers[3], layers[4]],
        "03_design_realized.mlp": [layers[6], layers[7]],
    }
    project_paths = {
        name: write_meshlab_project(output_directory / name, project_layers)
        for name, project_layers in projects.items()
    }
    direct_specs = {
        f"01_exact_dice_{exact.dice:.2%}.ply": (
            layers[0:3],
            f"Direct MeshLab evidence | exact lattice-window Dice {exact.dice:.2%}",
        ),
        f"02_ct_within_design_{ct_near_design.sum() / exact.a_voxels:.2%}.ply": (
            layers[3:5],
            f"Direct MeshLab evidence | CT within STL +{arguments.tolerance_cells} cell {ct_near_design.sum() / exact.a_voxels:.2%}",
        ),
        f"03_design_realized_{design_realized.sum() / exact.b_voxels:.2%}.ply": (
            layers[6:8],
            f"Direct MeshLab evidence | STL realized in CT +{arguments.tolerance_cells} cell {design_realized.sum() / exact.b_voxels:.2%}",
        ),
    }
    direct_view_paths: dict[str, Path] = {}
    direct_view_counts: dict[str, int] = {}
    for filename, (view_layers, label) in direct_specs.items():
        path, count = merge_colored_points_ply(
            output_directory / filename,
            [layer.path for layer in view_layers],
            comments=(
                label,
                note,
                "Merged display layers: " + ", ".join(layer.path.name for layer in view_layers),
            ),
        )
        direct_view_paths[filename] = path
        direct_view_counts[filename] = count
    print(
        f"[5/6] wrote {len(layers)} colored evidence layers, {len(direct_view_paths)} direct PLY views, "
        f"and {len(project_paths)} optional MeshLab projects"
    )

    metrics = {
        "lattice_window": {
            "slices_zyx": [[part.start, part.stop] for part in window],
            "downsample": arguments.downsample,
            "tolerance_cells": arguments.tolerance_cells,
            "exact_dice": exact.dice,
            "exact_iou": exact.iou,
            "exact_overlap_fraction_of_union": exact.iou,
            "ct_within_design_tolerant": float(ct_near_design.sum() / exact.a_voxels),
            "design_realized_in_ct_tolerant": float(design_realized.sum() / exact.b_voxels),
            "ct_window_voxels": exact.a_voxels,
            "stl_window_voxels": exact.b_voxels,
        },
        "registration": {
            "rotation_degrees": fit.rotation_angle_degrees,
            "scale_voxels_per_design_unit": fit.scale,
            "rms_error_voxels": fit.rms_error,
            "stl_rotation": arguments.stl_rotation,
        },
        "threshold": {"value": threshold, "source": threshold_source},
        "layers": [
            {
                "file": layer.path.name,
                "label": layer.label,
                "color_rgb": layer.color_rgb,
                "source_voxel_count": layer.source_voxel_count,
                "sampled_point_count": layer.sampled_point_count,
                "sampling_stride": layer.sampling_stride,
            }
            for layer in layers
        ],
        "display_sampling": {
            "method": "common deterministic stride within each exclusive metric partition",
            "exact_dice_stride": exact_stride,
            "ct_within_design_stride": ct_stride,
            "design_realized_stride": design_stride,
            "note": "The visual class densities preserve source-count proportions. Exact Dice is shown in the layer label; the yellow fraction of the exact-union display equals IoU, not Dice.",
        },
        "projects": {name: str(path) for name, path in project_paths.items()},
        "direct_ply_views": {
            name: {"path": str(path), "display_point_count": direct_view_counts[name]}
            for name, path in direct_view_paths.items()
        },
        "runtime_seconds": round(time.perf_counter() - started, 1),
    }
    write_json(output_directory / "metrics.json", json_safe(metrics))
    _write_markdown(
        output_directory / "README.md",
        exact_dice=exact.dice,
        ct_near_design=metrics["lattice_window"]["ct_within_design_tolerant"],
        design_realized=metrics["lattice_window"]["design_realized_in_ct_tolerant"],
        tolerance_cells=arguments.tolerance_cells,
        layers=layers,
        project_names=list(project_paths),
        direct_views=direct_view_counts,
    )
    print(f"[6/6] saved metrics.json and README.md to {output_directory}")
    return metrics


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    result = export_metrics(arguments)
    if arguments.open_meshlab:
        if not MESHLAB_APP.is_dir():
            raise SystemExit(f"MeshLab application not found: {MESHLAB_APP}")
        subprocess.Popen(
            [
                "open",
                "-a",
                str(MESHLAB_APP),
                str(result["direct_ply_views"][f"01_exact_dice_{result['lattice_window']['exact_dice']:.2%}.ply"]["path"]),
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
