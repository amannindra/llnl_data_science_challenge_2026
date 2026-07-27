#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mplconfig"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage as ndi


def load_volume(input_path: Path) -> np.ndarray:
    try:
        return tifffile.memmap(input_path)
    except Exception:
        return tifffile.imread(input_path)


def validate_volume(volume: np.ndarray, slice_index: int) -> None:
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D TIFF volume, got ndim={volume.ndim}")
    if not (0 <= slice_index < volume.shape[0]):
        raise IndexError(
            f"Slice index {slice_index} is outside axis-0 range 0..{volume.shape[0] - 1}"
        )


def remove_small_components(mask: np.ndarray, min_size: int) -> np.ndarray:
    labeled, num = ndi.label(mask)
    if num == 0:
        return mask
    counts = np.bincount(labeled.ravel())
    keep = counts >= min_size
    keep[0] = False
    return keep[labeled]


def segment_slice(image: np.ndarray, threshold: float, sigma: float, min_size: int) -> np.ndarray:
    image_f = image.astype(np.float32, copy=False)
    if sigma > 0:
        image_f = ndi.gaussian_filter(image_f, sigma=sigma)
    mask = image_f > threshold
    mask = remove_small_components(mask, min_size=min_size)
    return mask.astype(bool, copy=False)


def connectivity_stats(mask: np.ndarray) -> dict[str, float | int]:
    foreground_count = int(mask.sum())
    background_count = int(mask.size - foreground_count)
    if foreground_count == 0:
        return {
            "foreground_fraction": 0.0,
            "foreground_count": 0,
            "background_count": background_count,
            "component_count": 0,
            "largest_component_fraction": 0.0,
        }
    labeled, num = ndi.label(mask)
    counts = np.bincount(labeled.ravel())[1:]
    largest = int(counts.max()) if counts.size else 0
    return {
        "foreground_fraction": float(foreground_count / mask.size),
        "foreground_count": foreground_count,
        "background_count": background_count,
        "component_count": int(num),
        "largest_component_fraction": float(largest / foreground_count),
    }


def save_mask_png(mask: np.ndarray, output_path: Path) -> None:
    Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(output_path)


def save_raw_png(image: np.ndarray, output_path: Path) -> None:
    image_f = image.astype(np.float32, copy=False)
    imin = float(image_f.min())
    imax = float(image_f.max())
    if imax <= imin:
        scaled = np.zeros_like(image_f, dtype=np.uint8)
    else:
        scaled = ((image_f - imin) * (255.0 / (imax - imin))).clip(0, 255).astype(np.uint8)
    Image.fromarray(scaled, mode="L").save(output_path)


def inspect_volume(
    volume: np.ndarray,
    output_dir: Path,
    slice_index: int,
    representative_indices: list[int],
) -> dict[str, object]:
    raw_slice_path = output_dir / "raw_slice_380.png"
    histogram_path = output_dir / "inspection_histogram.png"
    slices_path = output_dir / "inspection_slices.png"

    save_raw_png(volume[slice_index], raw_slice_path)

    sample = volume[::8, ::8, ::8].astype(np.float32, copy=False).ravel()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(sample, bins=256, color="black")
    ax.set_title("Sampled Intensity Histogram")
    ax.set_xlabel("Intensity")
    ax.set_ylabel("Voxel count")
    fig.tight_layout()
    fig.savefig(histogram_path, dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(representative_indices), figsize=(16, 4))
    for ax, idx in zip(axes, representative_indices):
        ax.imshow(volume[idx], cmap="gray")
        ax.set_title(f"Slice {idx}")
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(slices_path, dpi=150)
    plt.close(fig)

    return {
        "raw_slice_path": str(raw_slice_path.resolve()),
        "histogram_path": str(histogram_path.resolve()),
        "representative_slices_path": str(slices_path.resolve()),
        "representative_indices": representative_indices,
        "sampled_histogram_voxels": int(sample.size),
    }


def run_preview(
    volume: np.ndarray,
    output_dir: Path,
    slice_index: int,
    threshold: float,
    sigma: float,
    min_size: int,
    preview_path: Path | None,
) -> dict[str, object]:
    preview_mask = segment_slice(volume[slice_index], threshold=threshold, sigma=sigma, min_size=min_size)
    if preview_path is not None:
        save_mask_png(preview_mask, preview_path)
    return {
        "method": "global",
        "params": {
            "threshold": threshold,
            "sigma": sigma,
            "min_size": min_size,
        },
        "preview": connectivity_stats(preview_mask),
        "preview_path": str(preview_path.resolve()) if preview_path is not None else None,
        "input_path": str(output_dir.parent.parent.joinpath("9x9x9_octet_lattice.tif").resolve()),
        "output_dir": str(output_dir.resolve()),
    }


def run_full(
    volume: np.ndarray,
    slice_index: int,
    threshold: float,
    sigma: float,
    min_size: int,
    mask_path: Path,
    slice_image_path: Path,
) -> dict[str, object]:
    full_mask = np.zeros(volume.shape, dtype=np.uint8)
    foreground_total = 0
    for idx in range(volume.shape[0]):
        mask = segment_slice(volume[idx], threshold=threshold, sigma=sigma, min_size=min_size)
        mask_u8 = mask.astype(np.uint8, copy=False)
        full_mask[idx] = mask_u8
        foreground_total += int(mask_u8.sum())
        if idx == slice_index:
            save_mask_png(mask, slice_image_path)
    tifffile.imwrite(mask_path, full_mask, photometric="minisblack")

    total_voxels = int(np.prod(volume.shape))
    background_total = int(total_voxels - foreground_total)
    return {
        "mask_path": str(mask_path.resolve()),
        "slice_image_path": str(slice_image_path.resolve()),
        "mask_shape": [int(v) for v in full_mask.shape],
        "mask_dtype": str(full_mask.dtype),
        "foreground_count": foreground_total,
        "background_count": background_total,
        "foreground_fraction": float(foreground_total / total_voxels),
        "background_fraction": float(background_total / total_voxels),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Focused global-threshold lattice segmentation.")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--mode", choices=["inspect", "preview", "full"], required=True)
    parser.add_argument("--slice-index", type=int, default=380)
    parser.add_argument("--threshold", type=float, default=39000.0)
    parser.add_argument("--sigma", type=float, default=1.0)
    parser.add_argument("--min-size", type=int, default=8)
    parser.add_argument("--preview-path", type=Path)
    parser.add_argument("--mask-path", type=Path)
    parser.add_argument("--slice-image-path", type=Path)
    parser.add_argument("--stats-path", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    volume = load_volume(args.input_path)
    validate_volume(volume, args.slice_index)

    result: dict[str, object] = {
        "input_path": str(args.input_path.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "shape": [int(v) for v in volume.shape],
        "input_dtype": str(volume.dtype),
        "intensity_min": int(np.min(volume)),
        "intensity_max": int(np.max(volume)),
        "slice_index": args.slice_index,
        "mode": args.mode,
    }

    if args.mode == "inspect":
        representative_indices = sorted(
            {
                0,
                args.slice_index // 2,
                args.slice_index,
                min(volume.shape[0] - 1, (args.slice_index + volume.shape[0] - 1) // 2),
                volume.shape[0] - 1,
            }
        )
        result["inspection"] = inspect_volume(
            volume=volume,
            output_dir=args.output_dir,
            slice_index=args.slice_index,
            representative_indices=representative_indices,
        )
    elif args.mode == "preview":
        result.update(
            run_preview(
                volume=volume,
                output_dir=args.output_dir,
                slice_index=args.slice_index,
                threshold=args.threshold,
                sigma=args.sigma,
                min_size=args.min_size,
                preview_path=args.preview_path,
            )
        )
    else:
        if args.mask_path is None or args.slice_image_path is None:
            raise ValueError("--mask-path and --slice-image-path are required in full mode")
        result["method"] = "global"
        result["params"] = {
            "threshold": args.threshold,
            "sigma": args.sigma,
            "min_size": args.min_size,
        }
        result["preview"] = connectivity_stats(
            segment_slice(
                volume[args.slice_index],
                threshold=args.threshold,
                sigma=args.sigma,
                min_size=args.min_size,
            )
        )
        result["full"] = run_full(
            volume=volume,
            slice_index=args.slice_index,
            threshold=args.threshold,
            sigma=args.sigma,
            min_size=args.min_size,
            mask_path=args.mask_path,
            slice_image_path=args.slice_image_path,
        )

    if args.stats_path is not None:
        args.stats_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
