#!/usr/bin/env python3
"""Measure raw-CT threshold stability along native TIFF X without downsampling."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import tifffile


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.paths import data_path, output_path  # noqa: E402
from Components.reporting import write_json  # noqa: E402
from Components.tiff_mesh import otsu_threshold_from_histogram  # noqa: E402


def histogram_for_x_band(
    volume_zyx: np.ndarray,
    x_begin: int,
    x_end: int,
    *,
    z_chunk: int = 16,
) -> np.ndarray:
    """Read every native voxel in one X band into a uint16 histogram."""

    histogram = np.zeros(65_536, dtype=np.int64)
    for z_begin in range(0, volume_zyx.shape[0], z_chunk):
        block = np.asarray(
            volume_zyx[z_begin : z_begin + z_chunk, :, x_begin:x_end]
        )
        histogram += np.bincount(block.reshape(-1), minlength=65_536)
    return histogram


def histogram_quantile(histogram: np.ndarray, fraction: float) -> int:
    cumulative = np.cumsum(histogram)
    target = fraction * int(cumulative[-1])
    return int(np.searchsorted(cumulative, target, side="left"))


def main() -> int:
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
    parser.add_argument("--band-width", type=int, default=80)
    parser.add_argument("--global-threshold", type=int, default=40_054)
    parser.add_argument(
        "--output",
        default=str(output_path("stl_tiff_strut_errors", "ct_x_threshold_diagnostic.json")),
    )
    arguments = parser.parse_args()
    if arguments.band_width < 1:
        parser.error("--band-width must be positive")

    volume = tifffile.memmap(arguments.tiff, mode="r")
    rows = []
    for x_begin in range(0, volume.shape[2], arguments.band_width):
        x_end = min(volume.shape[2], x_begin + arguments.band_width)
        histogram = histogram_for_x_band(volume, x_begin, x_end)
        total = int(histogram.sum())
        threshold = int(otsu_threshold_from_histogram(histogram, offset=0))
        above = int(histogram[arguments.global_threshold :].sum())
        material_values = np.arange(arguments.global_threshold, 65_536, dtype=np.float64)
        material_histogram = histogram[arguments.global_threshold :]
        material_mean = (
            float(material_values @ material_histogram / above) if above else None
        )
        rows.append({
            "x_begin": x_begin,
            "x_end_exclusive": x_end,
            "native_voxel_count": total,
            "otsu_threshold": threshold,
            "q50_intensity": histogram_quantile(histogram, 0.50),
            "q99_intensity": histogram_quantile(histogram, 0.99),
            "above_global_threshold_count": above,
            "above_global_threshold_fraction": float(above / total),
            "above_global_threshold_mean": material_mean,
        })
        print(
            f"X[{x_begin:3d},{x_end:3d}): Otsu={threshold}, "
            f">={arguments.global_threshold} {100.0 * above / total:.4f}%"
        )
    write_json(
        arguments.output,
        {
            "tiff": str(Path(arguments.tiff).resolve()),
            "shape_zyx": list(volume.shape),
            "dtype": str(volume.dtype),
            "downsampled": False,
            "global_threshold": arguments.global_threshold,
            "bands": rows,
        },
        create_parents=True,
    )
    print(f"wrote {Path(arguments.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
