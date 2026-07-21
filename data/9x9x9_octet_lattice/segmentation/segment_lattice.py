#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import imageio.v3 as iio
import numpy as np
from scipy import ndimage as ndi
from tifffile import imwrite, memmap


def parse_slice_list(raw_value, z_limit):
    if not raw_value:
        return []
    slices = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        value = int(item)
        if value < 0 or value >= z_limit:
            raise ValueError(f"slice index {value} is out of bounds for axis 0 with size {z_limit}")
        slices.append(value)
    return sorted(set(slices))


def validate_input(input_path):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input TIFF does not exist: {input_path}")
    if path.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError(f"input is not a TIFF volume: {input_path}")
    volume = memmap(str(path))
    if volume.ndim != 3:
        raise ValueError(f"input volume must be 3D, got ndim={volume.ndim}")
    if volume.shape[0] <= 380:
        raise ValueError(
            f"input volume does not contain slice index 380 on axis 0; shape is {volume.shape}"
        )
    return volume


def make_structure(rank):
    return ndi.generate_binary_structure(rank, 1)


def segment_slice(
    slice_array,
    threshold,
    sigma,
    closing_iters,
    opening_iters,
    background_sigma,
    min_intensity,
):
    base = slice_array.astype(np.float32, copy=False)
    work = base
    if sigma > 0:
        work = ndi.gaussian_filter(base, sigma=sigma)
    if background_sigma > 0:
        background = ndi.gaussian_filter(base, sigma=background_sigma)
        score = work - background
    else:
        score = work
    mask = score >= threshold
    if min_intensity > 0:
        mask &= work >= min_intensity
    if closing_iters > 0:
        mask = ndi.binary_closing(mask, structure=make_structure(2), iterations=closing_iters)
    if opening_iters > 0:
        mask = ndi.binary_opening(mask, structure=make_structure(2), iterations=opening_iters)
    return mask


def compute_component_metrics(metric_mask, slice_380_mask):
    metrics = {
        "foreground_fraction_metric_region": float(metric_mask.mean()),
        "metric_region_voxel_count": int(metric_mask.size),
        "metric_region_foreground_voxels": int(metric_mask.sum()),
        "metric_region_background_voxels": int(metric_mask.size - metric_mask.sum()),
    }

    labels_3d, num_components_3d = ndi.label(metric_mask, structure=make_structure(3))
    component_sizes_3d = np.bincount(labels_3d.ravel())[1:]
    if component_sizes_3d.size:
        largest_3d = int(component_sizes_3d.max())
        metrics.update(
            {
                "metric_region_component_count_3d": int(num_components_3d),
                "metric_region_largest_component_voxels_3d": largest_3d,
                "metric_region_largest_component_fraction_3d": float(
                    largest_3d / max(1, int(metric_mask.sum()))
                ),
                "metric_region_small_component_count_3d_lt_64": int(
                    np.count_nonzero(component_sizes_3d < 64)
                ),
            }
        )
    else:
        metrics.update(
            {
                "metric_region_component_count_3d": 0,
                "metric_region_largest_component_voxels_3d": 0,
                "metric_region_largest_component_fraction_3d": 0.0,
                "metric_region_small_component_count_3d_lt_64": 0,
            }
        )

    labels_2d, num_components_2d = ndi.label(slice_380_mask, structure=make_structure(2))
    component_sizes_2d = np.bincount(labels_2d.ravel())[1:]
    if component_sizes_2d.size:
        largest_2d = int(component_sizes_2d.max())
        metrics.update(
            {
                "slice_380_component_count_2d": int(num_components_2d),
                "slice_380_largest_component_pixels_2d": largest_2d,
                "slice_380_largest_component_fraction_2d": float(
                    largest_2d / max(1, int(slice_380_mask.sum()))
                ),
                "slice_380_small_component_count_2d_lt_16": int(
                    np.count_nonzero(component_sizes_2d < 16)
                ),
            }
        )
    else:
        metrics.update(
            {
                "slice_380_component_count_2d": 0,
                "slice_380_largest_component_pixels_2d": 0,
                "slice_380_largest_component_fraction_2d": 0.0,
                "slice_380_small_component_count_2d_lt_16": 0,
            }
        )
    return metrics


def save_mask_png(mask, output_path):
    png = (mask.astype(np.uint8) * 255)
    iio.imwrite(output_path, png)


def run_preview(volume, args):
    metric_slices = parse_slice_list(args.metric_slices, volume.shape[0])
    sample_slices = parse_slice_list(args.sample_slices, volume.shape[0])
    if 380 not in metric_slices and 380 not in sample_slices:
        sample_slices = sorted(set(sample_slices + [380]))

    needed = sorted(set(metric_slices + sample_slices))
    metric_masks = []
    slice_380_mask = None
    for z_index in needed:
        mask = segment_slice(
            np.asarray(volume[z_index]),
            threshold=args.threshold,
            sigma=args.sigma,
            closing_iters=args.closing_iters,
            opening_iters=args.opening_iters,
            background_sigma=args.background_sigma,
            min_intensity=args.min_intensity,
        )
        if z_index in metric_slices:
            metric_masks.append(mask)
        if z_index == 380:
            slice_380_mask = mask

    if slice_380_mask is None:
        raise RuntimeError("preview run did not produce slice 380")
    if not metric_masks:
        raise RuntimeError("preview run requires at least one metric slice")

    metric_mask = np.stack(metric_masks, axis=0)
    metrics = compute_component_metrics(metric_mask, slice_380_mask)
    metrics.update(
        {
            "mode": "preview",
            "threshold": args.threshold,
            "sigma": args.sigma,
            "closing_iters": args.closing_iters,
            "opening_iters": args.opening_iters,
            "background_sigma": args.background_sigma,
            "min_intensity": args.min_intensity,
            "metric_slices": metric_slices,
            "sample_slices": sample_slices,
        }
    )

    if args.preview_path:
        save_mask_png(slice_380_mask, args.preview_path)
    if args.metrics_json:
        with open(args.metrics_json, "w", encoding="utf-8") as handle:
            json.dump(metrics, handle, indent=2)
    return metrics


def run_full(volume, args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_mask_path = output_dir / "_temp_segmented_mask.uint8.dat"
    metric_slices = parse_slice_list(args.metric_slices, volume.shape[0])
    if not metric_slices:
        raise RuntimeError("full run requires metric_slices for topology/noise reporting")

    temp_mask = np.memmap(
        temp_mask_path,
        mode="w+",
        dtype=np.uint8,
        shape=volume.shape,
    )

    metric_masks = []
    slice_380_mask = None
    foreground_voxels = 0

    for z_index in range(volume.shape[0]):
        mask = segment_slice(
            np.asarray(volume[z_index]),
            threshold=args.threshold,
            sigma=args.sigma,
            closing_iters=args.closing_iters,
            opening_iters=args.opening_iters,
            background_sigma=args.background_sigma,
            min_intensity=args.min_intensity,
        )
        temp_mask[z_index] = mask.astype(np.uint8)
        fg = int(mask.sum())
        foreground_voxels += fg
        if z_index in metric_slices:
            metric_masks.append(mask)
        if z_index == 380:
            slice_380_mask = mask

    temp_mask.flush()
    if slice_380_mask is None:
        raise RuntimeError("full run did not produce slice 380")

    final_mask_path = output_dir / args.mask_name
    imwrite(
        final_mask_path,
        temp_mask,
        dtype=np.uint8,
        compression="zlib",
        photometric="minisblack",
    )
    if args.slice_image_name:
        save_mask_png(slice_380_mask, output_dir / args.slice_image_name)

    metric_mask = np.stack(metric_masks, axis=0)
    total_voxels = int(np.prod(volume.shape))
    background_voxels = total_voxels - foreground_voxels
    metrics = compute_component_metrics(metric_mask, slice_380_mask)
    metrics.update(
        {
            "mode": "full",
            "threshold": args.threshold,
            "sigma": args.sigma,
            "closing_iters": args.closing_iters,
            "opening_iters": args.opening_iters,
            "background_sigma": args.background_sigma,
            "min_intensity": args.min_intensity,
            "metric_slices": metric_slices,
            "input_shape": list(volume.shape),
            "input_dtype": str(volume.dtype),
            "mask_shape": list(volume.shape),
            "mask_dtype": "uint8",
            "total_voxels": total_voxels,
            "foreground_voxels": int(foreground_voxels),
            "background_voxels": int(background_voxels),
            "foreground_fraction_full_volume": float(foreground_voxels / total_voxels),
            "background_fraction_full_volume": float(background_voxels / total_voxels),
            "mask_path": str(final_mask_path),
            "slice_380_path": str(output_dir / args.slice_image_name),
        }
    )

    if args.metrics_json:
        with open(args.metrics_json, "w", encoding="utf-8") as handle:
            json.dump(metrics, handle, indent=2)

    del temp_mask
    if temp_mask_path.exists():
        temp_mask_path.unlink()
    return metrics


def build_parser():
    parser = argparse.ArgumentParser(description="Segment a CT lattice TIFF volume.")
    parser.add_argument("input_path", help="Path to the 3D TIFF input volume.")
    parser.add_argument("output_dir", help="Directory for outputs.")
    parser.add_argument("--threshold", type=float, required=True, help="Intensity threshold.")
    parser.add_argument("--sigma", type=float, default=0.0, help="Gaussian sigma before thresholding.")
    parser.add_argument(
        "--background-sigma",
        type=float,
        default=0.0,
        help="Large Gaussian sigma for slice-wise background subtraction; 0 disables it.",
    )
    parser.add_argument(
        "--min-intensity",
        type=float,
        default=0.0,
        help="Optional minimum smoothed intensity gate to suppress dark artifacts.",
    )
    parser.add_argument("--closing-iters", type=int, default=0, help="2D binary closing iterations.")
    parser.add_argument("--opening-iters", type=int, default=0, help="2D binary opening iterations.")
    parser.add_argument(
        "--sample-slices",
        default="190,285,380,475,570",
        help="Comma-separated representative slices for preview.",
    )
    parser.add_argument(
        "--metric-slices",
        default="372,374,376,378,380,382,384,386,388",
        help="Comma-separated slices used for component and noise metrics.",
    )
    parser.add_argument("--preview-only", action="store_true", help="Process only sample/metric slices.")
    parser.add_argument("--preview-path", default="", help="PNG path for mask slice 380.")
    parser.add_argument("--metrics-json", default="", help="Optional JSON output for run metrics.")
    parser.add_argument("--mask-name", default="segmented_mask.tif", help="Final mask TIFF filename.")
    parser.add_argument("--slice-image-name", default="slice_380.png", help="Final slice PNG filename.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    volume = validate_input(args.input_path)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if args.preview_only:
        run_preview(volume, args)
    else:
        run_full(volume, args)


if __name__ == "__main__":
    main()
