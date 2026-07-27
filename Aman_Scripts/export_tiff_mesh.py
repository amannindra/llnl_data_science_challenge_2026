#!/usr/bin/env python3
"""Convert a 3D raw CT TIFF into a validated MeshLab-compatible binary PLY."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

try:  # Package import.
    from .Components.asset_io import inspect_tiff, read_tiff
    from .Components.paths import data_path, find_repository_root, output_path
    from .Components.reporting import file_sha256, write_json
    from .Components.tiff_mesh import (
        TIFFMeshError,
        available_memory_bytes,
        estimate_resources,
        extract_surface_slabbed,
        foreground_profile,
        inspect_binary_ply,
        otsu_threshold_from_histogram,
        streaming_integer_histogram,
        validate_foreground_profile,
        validate_resources,
        write_binary_ply,
    )
except ImportError:  # Direct execution.
    from Components.asset_io import inspect_tiff, read_tiff
    from Components.paths import data_path, find_repository_root, output_path
    from Components.reporting import file_sha256, write_json
    from Components.tiff_mesh import (
        TIFFMeshError,
        available_memory_bytes,
        estimate_resources,
        extract_surface_slabbed,
        foreground_profile,
        inspect_binary_ply,
        otsu_threshold_from_histogram,
        streaming_integer_histogram,
        validate_foreground_profile,
        validate_resources,
        write_binary_ply,
    )


ROOT = find_repository_root(__file__)
DEFAULT_INPUT = data_path(
    "missing_struts", "tif_stacks",
    "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
    root=ROOT,
)
DEFAULT_OUTPUT = output_path(
    "meshlab", "raw_ct_0point5dash1_full_resolution.ply", root=ROOT
)


def parse_threshold(value: str) -> str | float:
    """Parse ``auto`` or one finite numeric CT intensity."""

    if value.strip().lower() == "auto":
        return "auto"
    try:
        threshold = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("threshold must be 'auto' or a number") from exc
    if not np.isfinite(threshold):
        raise argparse.ArgumentTypeError("threshold must be finite")
    return threshold


def parse_spacing(value: str) -> tuple[float, float, float]:
    """Parse comma-separated positive XYZ voxel spacing."""

    try:
        spacing = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("spacing must be X,Y,Z numbers") from exc
    if len(spacing) != 3 or not np.isfinite(spacing).all() or any(item <= 0 for item in spacing):
        raise argparse.ArgumentTypeError("spacing must contain three finite positive values")
    return spacing


def build_preflight(
    source: str | Path,
    *,
    threshold_spec: str | float = "auto",
    chunk_depth: int = 16,
    padding: int = 2,
    output_directory: str | Path = DEFAULT_OUTPUT.parent,
) -> tuple[dict[str, Any], np.ndarray, float, Any]:
    """Profile the TIFF and validate that native-resolution meshing is safe."""

    metadata = inspect_tiff(source)
    if metadata.axes != "ZYX" or len(metadata.shape) != 3:
        raise TIFFMeshError(
            f"expected one 3D ZYX TIFF series, received axes={metadata.axes!r}, "
            f"shape={metadata.shape}"
        )
    if metadata.dtype.kind not in "ui":
        raise TIFFMeshError(
            f"automatic raw-CT profiling requires an integer TIFF, received {metadata.dtype}"
        )
    if not metadata.memory_mappable:
        raise TIFFMeshError("TIFF is not memory-mappable; refusing a hidden full-volume allocation")
    volume = read_tiff(source)
    if threshold_spec == "auto":
        histogram, offset = streaming_integer_histogram(volume, chunk_depth=chunk_depth)
        threshold = otsu_threshold_from_histogram(histogram, offset=offset)
        threshold_method = "global_otsu_exact_histogram"
    else:
        threshold = float(threshold_spec)
        threshold_method = "explicit"
    profile = foreground_profile(
        volume, threshold, chunk_depth=chunk_depth, padding=padding
    )
    validate_foreground_profile(profile)
    resources = estimate_resources(profile)
    destination = Path(output_directory).expanduser().resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(destination)
    memory = available_memory_bytes()
    validate_resources(
        resources,
        free_disk_bytes=int(disk.free),
        available_memory_bytes=memory,
    )
    report = {
        "source": str(metadata.path),
        "tiff": {
            "shape_zyx": metadata.shape,
            "axes": metadata.axes,
            "dtype": str(metadata.dtype),
            "pages": metadata.page_count,
            "memory_mappable": metadata.memory_mappable,
        },
        "threshold": {"value": threshold, "method": threshold_method},
        "foreground": asdict(profile),
        "resources": asdict(resources),
        "available": {
            "disk_bytes": int(disk.free),
            "memory_bytes": memory,
        },
        "coordinate_convention": "input ZYX array indices; output XYZ voxel coordinates",
        "quality_gate": "passed",
    }
    return report, volume, threshold, profile


def save_threshold_preview(
    volume: np.ndarray,
    threshold: float,
    destination: str | Path,
    *,
    z_indices: Sequence[int] | None = None,
) -> Path:
    """Save representative raw slices beside transparent threshold overlays.

    Only the selected 2D pages are materialized.  This makes the automatic
    threshold auditable without turning the 3D conversion into a second full
    in-memory volume.
    """

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if volume.ndim != 3:
        raise ValueError("preview volume must be 3D ZYX")
    if z_indices is None:
        z_indices = tuple(
            sorted({0, volume.shape[0] // 4, volume.shape[0] // 2,
                    3 * volume.shape[0] // 4, volume.shape[0] - 1})
        )
    indices = tuple(int(index) for index in z_indices)
    if not indices or any(index < 0 or index >= volume.shape[0] for index in indices):
        raise IndexError("preview Z indices must lie inside the volume")
    output = Path(destination).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, len(indices), figsize=(4 * len(indices), 8), squeeze=False)
    for column, index in enumerate(indices):
        image = np.asarray(volume[index])
        low, high = np.percentile(image, (1, 99.5))
        axes[0, column].imshow(image, cmap="gray", vmin=low, vmax=high)
        axes[0, column].set_title(f"raw Z={index}")
        axes[1, column].imshow(image, cmap="gray", vmin=low, vmax=high)
        axes[1, column].imshow(
            image > threshold,
            cmap="autumn",
            alpha=np.where(image > threshold, 0.55, 0.0),
            interpolation="nearest",
        )
        axes[1, column].set_title(f"> {threshold:g}")
        axes[0, column].axis("off")
        axes[1, column].axis("off")
    figure.suptitle("Raw CT and automatic foreground overlay")
    figure.tight_layout()
    figure.savefig(output, dpi=140)
    plt.close(figure)
    return output


def convert_tiff_to_ply(
    source: str | Path,
    destination: str | Path,
    *,
    threshold_spec: str | float = "auto",
    histogram_chunk_depth: int = 16,
    slab_depth: int = 64,
    padding: int = 2,
    voxel_spacing_xyz: Sequence[float] = (1.0, 1.0, 1.0),
    preflight_only: bool = False,
) -> dict[str, Any]:
    """Run preflight, optionally extract the mesh, and persist audit manifests."""

    started = time.monotonic()
    output = Path(destination).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    preflight, volume, threshold, profile = build_preflight(
        source,
        threshold_spec=threshold_spec,
        chunk_depth=histogram_chunk_depth,
        padding=padding,
        output_directory=output.parent,
    )
    preflight_path = output.with_suffix(".preflight.json")
    write_json(preflight_path, preflight)
    preview_path = save_threshold_preview(
        volume, threshold, output.with_suffix(".threshold_preview.png")
    )
    print(f"Preflight passed: threshold={threshold:g}, foreground={profile.fraction:.4%}")
    print(f"Foreground bounds ZYX: {profile.bounds.start} -> {profile.bounds.stop}")
    if preflight_only:
        return {
            "preflight": preflight,
            "preflight_path": str(preflight_path),
            "threshold_preview_path": str(preview_path),
        }

    print(f"Extracting native-resolution surface in {slab_depth}-cell Z slabs...")
    mesh = extract_surface_slabbed(
        volume,
        threshold,
        profile.bounds,
        slab_depth=slab_depth,
        voxel_spacing_xyz=voxel_spacing_xyz,
    )
    write_binary_ply(
        output,
        mesh,
        comments=(
            f"source {Path(source).name}",
            f"threshold {threshold:g}",
            "coordinates XYZ voxel space",
        ),
    )
    verified = inspect_binary_ply(output)
    if verified.vertex_count != mesh.vertex_count or verified.face_count != mesh.face_count:
        raise TIFFMeshError("saved PLY counts do not match the extracted mesh")
    if verified.bounds_min_xyz != mesh.bounds_min_xyz or verified.bounds_max_xyz != mesh.bounds_max_xyz:
        raise TIFFMeshError("saved PLY bounds do not match the extracted mesh")

    manifest = {
        **preflight,
        "source_sha256": file_sha256(source),
        "threshold_preview": str(preview_path),
        "voxel_spacing_xyz": tuple(float(item) for item in voxel_spacing_xyz),
        "mesh": {
            "format": "binary_little_endian_ply",
            "path": str(output),
            "bytes": verified.bytes,
            "sha256": file_sha256(output),
            "vertices": verified.vertex_count,
            "faces": verified.face_count,
            "bounds_min_xyz": verified.bounds_min_xyz,
            "bounds_max_xyz": verified.bounds_max_xyz,
            "slabs_processed": mesh.slabs_processed,
            "seam_vertices_reused": mesh.seam_vertices_reused,
        },
        "runtime_seconds": time.monotonic() - started,
        "validation": {
            "header_and_payload_re_read": "passed",
            "count_match": "passed",
            "bounds_match": "passed",
            "meshlab_target": "/Applications/MeshLab2025.07.app",
        },
    }
    manifest_path = output.with_suffix(".manifest.json")
    write_json(manifest_path, manifest)
    print(f"Mesh saved: {output}")
    print(f"Manifest: {manifest_path}")
    print(f"Vertices/faces: {verified.vertex_count:,}/{verified.face_count:,}")
    return manifest


def _parser() -> argparse.ArgumentParser:
    """Build the command-line contract for reproducible TIFF conversion."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=parse_threshold, default="auto")
    parser.add_argument("--histogram-chunk-depth", type=int, default=16)
    parser.add_argument("--slab-depth", type=int, default=64)
    parser.add_argument("--padding", type=int, default=2)
    parser.add_argument("--voxel-spacing", type=parse_spacing, default=(1.0, 1.0, 1.0))
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--open-meshlab", action="store_true",
        help="Open the validated PLY in the installed MeshLab GUI after conversion",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the converter and return a shell-friendly status code."""

    args = _parser().parse_args(argv)
    try:
        result = convert_tiff_to_ply(
            args.input,
            args.output,
            threshold_spec=args.threshold,
            histogram_chunk_depth=args.histogram_chunk_depth,
            slab_depth=args.slab_depth,
            padding=args.padding,
            voxel_spacing_xyz=args.voxel_spacing,
            preflight_only=args.preflight_only,
        )
    except (OSError, ValueError, TIFFMeshError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.open_meshlab and not args.preflight_only:
        app = Path("/Applications/MeshLab2025.07.app")
        if not app.is_dir():
            print(f"ERROR: MeshLab application not found at {app}", file=sys.stderr)
            return 1
        subprocess.Popen(["open", "-a", str(app), str(args.output)])
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
