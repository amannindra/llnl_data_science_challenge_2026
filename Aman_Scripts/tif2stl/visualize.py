"""Side-by-side visuals: what the grid *should* look like (STL) vs the CT scan.

For a set of axial (z), coronal (y), and sagittal (x) slices, writes a three-up
panel per slice:

    [ STL design (expected) | CT scan (actual) | overlay ]

Overlay colors match validate.py: red = CT only, green = STL only,
yellow = agreement.

Run:
    conda run -n DSC python Aman_Scripts/tif2stl/visualize.py
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
from tif2stl.registration import (  # noqa: E402
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
    stl_to_design_matrix,
)
from tif2stl.validate import (  # noqa: E402
    build_ct_mask,
    sample_stl_points_mm,
    score_orientations,
)
from tif2stl.voxelize import voxelize_stl  # noqa: E402
from Components.tiff_mesh import (  # noqa: E402
    otsu_threshold_from_histogram,
    streaming_integer_histogram,
)

BACKGROUND = (18, 18, 24)
STL_COLOR = (70, 205, 95)      # design intent
CT_COLOR = (225, 225, 230)     # scanned material
CT_ONLY = (235, 70, 70)
STL_ONLY = (70, 205, 95)
BOTH = (245, 225, 80)
LABEL_COLOR = (255, 255, 255)
MARGIN = 8
LABEL_BAND = 22


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
    parser.add_argument("--output-dir", default=None,
                        help="default: Aman_Scripts/outputs/tif2stl/visuals")
    parser.add_argument("--downsample", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=None, help="default: streaming Otsu")
    parser.add_argument("--design-span", type=float, default=18.0)
    parser.add_argument("--stl-rotation", default="auto")
    parser.add_argument("--z-fractions", type=float, nargs="+",
                        default=(0.15, 0.3, 0.5, 0.7, 0.85))
    parser.add_argument("--scale", type=int, default=2,
                        help="integer upscale factor for readability")
    arguments = parser.parse_args(argv)
    if arguments.downsample < 1:
        parser.error("--downsample must be >= 1")
    if arguments.scale < 1:
        parser.error("--scale must be >= 1")
    return arguments


def plane_rgb(plane: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """Render one boolean plane as an RGB image on the dark background."""

    plane = np.asarray(plane, dtype=bool)
    rgb = np.empty((*plane.shape, 3), dtype=np.uint8)
    rgb[:] = BACKGROUND
    rgb[plane] = color
    return rgb


def overlay_rgb(ct_plane: np.ndarray, stl_plane: np.ndarray) -> np.ndarray:
    """Agreement map: red = CT only, green = STL only, yellow = both."""

    ct_plane = np.asarray(ct_plane, dtype=bool)
    stl_plane = np.asarray(stl_plane, dtype=bool)
    if ct_plane.shape != stl_plane.shape:
        raise ValueError(f"plane shapes differ: {ct_plane.shape} vs {stl_plane.shape}")
    rgb = np.empty((*ct_plane.shape, 3), dtype=np.uint8)
    rgb[:] = BACKGROUND
    rgb[ct_plane & ~stl_plane] = CT_ONLY
    rgb[~ct_plane & stl_plane] = STL_ONLY
    rgb[ct_plane & stl_plane] = BOTH
    return rgb


def compose_panel(stl_plane: np.ndarray, ct_plane: np.ndarray) -> np.ndarray:
    """Three-up [STL | CT | overlay] RGB array with margins and a label band."""

    tiles = [
        plane_rgb(stl_plane, STL_COLOR),
        plane_rgb(ct_plane, CT_COLOR),
        overlay_rgb(ct_plane, stl_plane),
    ]
    height, width = tiles[0].shape[:2]
    total_width = 3 * width + 4 * MARGIN
    total_height = height + 2 * MARGIN + LABEL_BAND
    panel = np.empty((total_height, total_width, 3), dtype=np.uint8)
    panel[:] = BACKGROUND
    for column, tile in enumerate(tiles):
        left = MARGIN + column * (width + MARGIN)
        panel[LABEL_BAND + MARGIN:LABEL_BAND + MARGIN + height, left:left + width] = tile
    return panel


def annotate_and_save(panel: np.ndarray, titles: tuple[str, str, str],
                      caption: str, destination: Path, scale: int) -> None:
    from PIL import Image, ImageDraw

    image = Image.fromarray(panel)
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    draw = ImageDraw.Draw(image)
    tile_width = (panel.shape[1] - 4 * MARGIN) // 3
    for column, title in enumerate(titles):
        left = (MARGIN + column * (tile_width + MARGIN)) * scale
        draw.text((left, 3 * scale), title, fill=LABEL_COLOR)
    draw.text((MARGIN * scale, (panel.shape[0] - LABEL_BAND + 8) * scale),
              caption, fill=LABEL_COLOR)
    image.save(destination)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    started = time.perf_counter()
    output_directory = (
        Path(arguments.output_dir).expanduser().resolve()
        if arguments.output_dir
        else output_path("tif2stl", "visuals", create=True)
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    tiff_metadata = inspect_tiff(arguments.tiff)
    if tiff_metadata.axes != "ZYX":
        raise ValueError(f"expected a ZYX TIFF series, got axes {tiff_metadata.axes!r}")
    stl_metadata = inspect_stl(arguments.stl)
    print(f"[1/5] inputs ok: TIFF {tiff_metadata.shape} {tiff_metadata.dtype}, "
          f"STL {stl_metadata.triangles:,} triangles", flush=True)

    volume = read_tiff(arguments.tiff)
    if arguments.threshold is None:
        histogram, offset = streaming_integer_histogram(volume)
        threshold = otsu_threshold_from_histogram(histogram, offset=offset)
    else:
        threshold = float(arguments.threshold)
    ct_mask = build_ct_mask(volume, threshold, arguments.downsample)
    print(f"[2/5] CT mask {ct_mask.shape} at threshold {threshold}: "
          f"{int(ct_mask.sum()):,} occupied cells", flush=True)

    design_graph = load_lattice_graph(arguments.design_json)
    registered_graph = load_lattice_graph(arguments.registered_json)
    design_points, registered_points = paired_junction_positions(design_graph, registered_graph)
    fit = similarity_transform(design_points, registered_points)
    extent_x = stl_metadata.bounding_box_max[0] - stl_metadata.bounding_box_min[0]
    mm_per_design_unit = extent_x / arguments.design_span
    stl_center = tuple(
        (low + high) / 2.0
        for low, high in zip(stl_metadata.bounding_box_min, stl_metadata.bounding_box_max)
    )
    half_span = arguments.design_span / 2.0
    design_center = (half_span, half_span, half_span)

    rotations = dict(proper_cube_rotations())
    requested = "+x+y+z" if arguments.stl_rotation == "identity" else arguments.stl_rotation
    if requested == "auto":
        sample_mm = sample_stl_points_mm(arguments.stl)
        scores = score_orientations(
            ct_mask, sample_mm,
            fit_matrix=fit.matrix,
            mm_per_design_unit=mm_per_design_unit,
            stl_center=stl_center,
            design_center=design_center,
            downsample=arguments.downsample,
        )
        chosen_name = str(scores[0]["name"])
        print(f"[3/5] orientation {chosen_name} "
              f"(hit fraction {scores[0]['score']:.4f})", flush=True)
    elif requested in rotations:
        chosen_name = requested
        print(f"[3/5] orientation {chosen_name} (user-requested)", flush=True)
    else:
        raise ValueError(
            f"unknown --stl-rotation {arguments.stl_rotation!r}; "
            f"use 'auto', 'identity', or one of {sorted(rotations)}"
        )
    stl_to_voxel = compose_transforms(
        stl_to_design_matrix(
            mm_per_design_unit=mm_per_design_unit,
            stl_center_xyz=stl_center,
            design_center_xyz=design_center,
            rotation=rotations[chosen_name],
        ),
        fit.matrix,
    )

    half_cell = arguments.downsample / 2.0
    voxelized = voxelize_stl(
        arguments.stl,
        pitch=float(arguments.downsample),
        transform=stl_to_voxel,
        origin_xyz=(-half_cell, -half_cell, -half_cell),
        grid_shape_zyx=ct_mask.shape,
    )
    stl_mask = voxelized.grid
    print(f"[4/5] voxelized STL: {voxelized.occupied_voxels:,} cells", flush=True)

    titles = ("STL design (expected)", "CT scan (actual)",
              "overlay (yellow=match, red=CT only, green=STL only)")
    z_size, y_size, x_size = ct_mask.shape
    ds = arguments.downsample
    written: list[Path] = []
    for fraction in arguments.z_fractions:
        index = min(int(z_size * fraction), z_size - 1)
        panel = compose_panel(stl_mask[index], ct_mask[index])
        destination = output_directory / f"compare_z{index * ds:04d}.png"
        annotate_and_save(panel, titles,
                          f"axial slice z={index * ds} (native voxels), "
                          f"orientation {chosen_name}",
                          destination, arguments.scale)
        written.append(destination)
    for axis, index, tag in (("y", y_size // 2, "coronal"), ("x", x_size // 2, "sagittal")):
        if axis == "y":
            stl_plane, ct_plane = stl_mask[:, index, :], ct_mask[:, index, :]
        else:
            stl_plane, ct_plane = stl_mask[:, :, index], ct_mask[:, :, index]
        panel = compose_panel(stl_plane, ct_plane)
        destination = output_directory / f"compare_{axis}{index * ds:04d}.png"
        annotate_and_save(panel, titles,
                          f"{tag} slice {axis}={index * ds} (native voxels), "
                          f"orientation {chosen_name}",
                          destination, arguments.scale)
        written.append(destination)

    runtime = time.perf_counter() - started
    print(f"[5/5] wrote {len(written)} comparison panels to {output_directory} "
          f"in {runtime:.0f} s", flush=True)
    for path in written:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
