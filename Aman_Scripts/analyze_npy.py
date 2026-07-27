#!/usr/bin/env python3
"""Analyze ``unitcell.npy`` without performing work when the module is imported.

The default command preserves the original histogram, center-slice, and
isosurface artifact names under ``Aman_Scripts/outputs``. Reusable I/O and numeric
validation live in ``Aman_Scripts/Components``; this file only coordinates the
analysis and plotting steps.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:  # Package import.
    from .Components.asset_io import load_npy
    from .Components.coordinates import zyx_to_xyz
    from .Components.paths import data_path, find_repository_root, output_path
    from .Components.segmentation import validate_numeric_volume
except ImportError:  # Direct execution.
    from Components.asset_io import load_npy
    from Components.coordinates import zyx_to_xyz
    from Components.paths import data_path, find_repository_root, output_path
    from Components.segmentation import validate_numeric_volume


ROOT = find_repository_root(__file__)
OUT = output_path(root=ROOT)
DEFAULT_NPY = data_path("unitcell", "unitcell.npy", root=ROOT)


def normalize_minmax(volume: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Return a float32 [0, 1] view-copy and the original finite range."""

    validate_numeric_volume(volume, require_3d=True, require_finite=True)
    minimum, maximum = float(np.min(volume)), float(np.max(volume))
    if maximum == minimum:
        return np.zeros(volume.shape, dtype=np.float32), minimum, maximum
    normalized = (np.asarray(volume, dtype=np.float32) - minimum) / (maximum - minimum)
    return normalized, minimum, maximum


def volume_summary(volume: np.ndarray) -> dict[str, Any]:
    """Calculate deterministic descriptive statistics for a finite 3D volume."""

    metadata = validate_numeric_volume(volume, require_3d=True, require_finite=True)
    percentiles = np.percentile(volume, [1, 5, 25, 50, 75, 95, 99])
    return {
        "shape": metadata.shape,
        "dtype": metadata.dtype,
        "nbytes": int(volume.nbytes),
        "min": float(np.min(volume)),
        "max": float(np.max(volume)),
        "mean": float(np.mean(volume)),
        "std": float(np.std(volume)),
        "percentiles": tuple(float(value) for value in percentiles),
    }


def save_histogram(volume: np.ndarray, destination: Path) -> None:
    """Write the historical log-count density histogram."""

    fig, axis = plt.subplots(figsize=(7, 4))
    axis.hist(np.asarray(volume).ravel(), bins=100, color="steelblue")
    axis.set_yscale("log")
    axis.set_title("unitcell.npy density histogram (log y)")
    axis.set_xlabel("density")
    axis.set_ylabel("voxel count")
    fig.tight_layout()
    fig.savefig(destination, dpi=120)
    plt.close(fig)


def save_center_slices(volume: np.ndarray, destination: Path) -> None:
    """Write the three native-orientation center slices."""

    middle = tuple(size // 2 for size in volume.shape)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for axis, dimension, index in zip(axes, range(3), middle):
        axis.imshow(np.take(volume, index, axis=dimension), cmap="gray")
        axis.set_title(f"axis {dimension}, slice {index}")
        axis.axis("off")
    fig.tight_layout()
    fig.savefig(destination, dpi=120)
    plt.close(fig)


def extract_isosurface_xyz(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract the half-resolution 0.5 mesh with vertices returned in XYZ order."""

    from skimage import measure

    downsampled = np.asarray(volume[::2, ::2, ::2], dtype=np.float32)
    normalized, _, _ = normalize_minmax(downsampled)
    if not (float(normalized.min()) <= 0.5 <= float(normalized.max())):
        raise ValueError("normalized volume does not cross isosurface level 0.5")
    vertices_zyx, faces, _, _ = measure.marching_cubes(normalized, level=0.5)
    return zyx_to_xyz(vertices_zyx), faces


def save_isosurface(volume: np.ndarray, destination: Path) -> tuple[int, int]:
    """Write the original half-resolution 0.5 isosurface and return mesh counts."""

    vertices, faces = extract_isosurface_xyz(volume)
    fig = plt.figure(figsize=(8, 8))
    axis = fig.add_subplot(111, projection="3d")
    axis.plot_trisurf(
        vertices[:, 0], vertices[:, 1], faces, vertices[:, 2],
        cmap="viridis", lw=0.1, edgecolor="none",
    )
    axis.view_init(elev=30, azim=45)
    axis.set_axis_off()
    axis.set_title("unitcell 3D isosurface (thr=0.5)")
    fig.tight_layout()
    fig.savefig(destination, dpi=120)
    plt.close(fig)
    return int(len(vertices)), int(len(faces))


def analyze_volume(
    source: str | Path = DEFAULT_NPY,
    output_directory: str | Path = OUT,
    *,
    include_isosurface: bool = True,
) -> dict[str, Any]:
    """Analyze one NPY volume and create the established plot artifacts."""

    destination = Path(output_directory).expanduser().resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    volume = load_npy(source)
    summary = volume_summary(volume)
    normalized, minimum, maximum = normalize_minmax(volume)
    thresholds = {}
    for threshold in (0.3, 0.4, 0.5, 0.6, 0.7):
        thresholds[str(threshold)] = {
            "raw_threshold": minimum + threshold * (maximum - minimum),
            "foreground_fraction": float(np.mean(normalized >= threshold)),
        }
    summary["normalized_thresholds"] = thresholds

    save_histogram(volume, destination / "npy_histogram.png")
    save_center_slices(volume, destination / "npy_center_slices.png")
    if include_isosurface:
        try:
            vertices, faces = save_isosurface(volume, destination / "npy_isosurface.png")
            summary["isosurface"] = {"vertices": vertices, "faces": faces}
        except Exception as exc:  # Plot failure should remain visible but not hide statistics.
            summary["isosurface_error"] = str(exc)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a 3D NumPy CT volume.")
    parser.add_argument("--input", default=str(DEFAULT_NPY), help="Input .npy volume")
    parser.add_argument("--output-dir", default=str(OUT), help="Artifact directory")
    parser.add_argument("--skip-isosurface", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = analyze_volume(
        args.input, args.output_dir, include_isosurface=not args.skip_isosurface
    )
    print("=" * 60)
    print("unitcell.npy")
    print("=" * 60)
    print(f"shape      : {summary['shape']}")
    print(f"dtype      : {summary['dtype']}")
    print(f"min/max    : {summary['min']:.4f} / {summary['max']:.4f}")
    print(f"mean/std   : {summary['mean']:.4f} / {summary['std']:.4f}")
    print(f"nbytes     : {summary['nbytes']/1e6:.1f} MB")
    print("percentiles 1/5/25/50/75/95/99: " + str(np.round(summary["percentiles"], 4)))
    print("foreground fraction by normalized threshold (raw-equivalent shown):")
    for threshold, result in summary["normalized_thresholds"].items():
        print(
            f"  normalized={float(threshold):.1f}; raw={result['raw_threshold']:.6f}; "
            f"fraction={result['foreground_fraction']:.4f}"
        )
    if "isosurface" in summary:
        mesh = summary["isosurface"]
        print(f"isosurface : {mesh['vertices']} verts, {mesh['faces']} faces")
    elif "isosurface_error" in summary:
        print(f"isosurface failed: {summary['isosurface_error']}")
    print(f"\nOutputs written to {Path(args.output_dir).resolve(strict=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
