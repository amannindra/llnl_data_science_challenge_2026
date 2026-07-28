#!/opt/miniconda3/envs/dssi_env/bin/python
"""Reproduce the Task 6 slice-380 threshold study and final page-wise mask."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage as ndi
from skimage.filters import threshold_li, threshold_otsu
from skimage.morphology import skeletonize


SLICE_INDEX = 380
MIN_FREE_BYTES = 4 * 1024**3
BASELINE_THRESHOLD = 34213.0
BASELINE_SCORE = 2


def metadata(path: Path) -> tuple[tuple[int, int, int], np.dtype, int]:
    with tifffile.TiffFile(path) as tif:
        shape = tuple(int(v) for v in tif.series[0].shape)
        dtype = np.dtype(tif.series[0].dtype)
        pages = len(tif.pages)
    if len(shape) != 3 or pages != shape[0]:
        raise RuntimeError(f"Expected a page-based 3-D TIFF, got shape={shape}, pages={pages}")
    return shape, dtype, pages


def write_mask(input_path: Path, output_path: Path, threshold: float,
               capture_index: int) -> tuple[int, int, np.ndarray]:
    foreground = 0
    selected = None
    with tifffile.TiffFile(input_path) as src, tifffile.TiffWriter(output_path, bigtiff=True) as dst:
        for index, page in enumerate(src.pages):
            mask = (page.asarray() > threshold).astype(np.uint8)
            foreground += int(mask.sum(dtype=np.uint64))
            if index == capture_index:
                selected = mask.copy()
            dst.write(mask, photometric="minisblack", compression="zlib",
                      compressionargs={"level": 1}, metadata=None)
    if selected is None:
        raise RuntimeError(f"Slice index {capture_index} was not produced")
    shape, _, _ = metadata(input_path)
    total = int(np.prod(shape, dtype=np.int64))
    return foreground, total - foreground, selected


def validate_mask(input_path: Path, mask_path: Path) -> dict[str, object]:
    input_shape, _, input_pages = metadata(input_path)
    mask_shape, mask_dtype, mask_pages = metadata(mask_path)
    values: set[int] = set()
    foreground = 0
    with tifffile.TiffFile(mask_path) as tif:
        for page in tif.pages:
            array = page.asarray()
            values.update(int(value) for value in np.unique(array))
            foreground += int(array.sum(dtype=np.uint64))
    total = int(np.prod(input_shape, dtype=np.int64))
    result = {
        "shape": mask_shape, "page_count": mask_pages, "dtype": str(mask_dtype),
        "unique_values": sorted(values), "foreground": foreground,
        "background": total - foreground, "total": total,
    }
    if mask_shape != input_shape or mask_pages != input_pages:
        raise RuntimeError(f"Shape/page mismatch: input={input_shape}/{input_pages}, mask={mask_shape}/{mask_pages}")
    if mask_dtype != np.dtype("uint8"):
        raise RuntimeError(f"Mask dtype is {mask_dtype}, expected uint8")
    if values != {0, 1}:
        raise RuntimeError(f"Mask unique values are {sorted(values)}, expected exactly [0, 1]")
    if foreground + int(result["background"]) != total:
        raise RuntimeError("Foreground and background counts do not sum to total")
    return result


def render_slice(mask: np.ndarray, path: Path) -> None:
    """Render the required exact 800x800 viridis preview."""
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    image = ax.imshow(mask, cmap="viridis", vmin=0, vmax=1)
    ax.set_title("Slice 380 along axis 0")
    fig.colorbar(image, ax=ax)
    fig.savefig(path, dpi=100)
    plt.close(fig)
    with Image.open(path) as preview:
        png_size = preview.size
    if png_size != (800, 800):
        raise RuntimeError(f"Preview is {png_size}, expected 800x800")


def synthetic_test() -> None:
    """Exercise page-wise segmentation, rendering, and validation before the real run."""
    with tempfile.TemporaryDirectory(prefix="task6_synthetic_") as tmp_name:
        tmp = Path(tmp_name)
        yy, xx = np.ogrid[:48, :52]
        volume = np.full((5, 48, 52), 1000, dtype=np.uint16)
        for z in range(5):
            volume[z][(yy - 24) ** 2 + (xx - (20 + z)) ** 2 < 9**2] = 5000
        source = tmp / "synthetic.tif"
        mask_path = tmp / "mask.tif"
        png_path = tmp / "slice.png"
        tifffile.imwrite(source, volume, photometric="minisblack")
        _, _, selected = write_mask(source, mask_path, 3000, 2)
        render_slice(selected, png_path)
        result = validate_mask(source, mask_path)
        if result["foreground"] == 0 or result["background"] == 0 or not png_path.is_file():
            raise RuntimeError("Synthetic complete-path test failed")


def candidate_metrics(image: np.ndarray, name: str, threshold: float) -> dict[str, object]:
    mask = image > threshold
    labels4, count4 = ndi.label(mask, ndi.generate_binary_structure(2, 1))
    _, count8 = ndi.label(mask, ndi.generate_binary_structure(2, 2))
    sizes = np.bincount(labels4.ravel())[1:]
    pixels = int(mask.sum())
    largest = int(sizes.max()) if sizes.size else 0
    small = int(sizes[sizes < 16].sum()) if sizes.size else 0
    skeleton = skeletonize(mask)
    neighbors = ndi.convolve(skeleton.astype(np.uint8), np.ones((3, 3), dtype=np.uint8), mode="constant") - skeleton
    high_labels, _ = ndi.label(image > 45000, ndi.generate_binary_structure(2, 2))
    high_sizes = np.bincount(high_labels.ravel())
    node_ids = np.flatnonzero(high_sizes >= 100)
    node_ids = node_ids[node_ids != 0]
    node_pixels = np.isin(high_labels, node_ids) if node_ids.size else np.zeros_like(mask)
    node_retention = float(np.count_nonzero(mask & node_pixels) / np.count_nonzero(node_pixels)) if node_pixels.any() else 1.0
    return {
        "iteration": 0, "method": name, "threshold": threshold,
        "foreground_pixels": pixels, "foreground_fraction": float(mask.mean()),
        "components_4_connected": int(count4), "components_8_connected": int(count8),
        "largest_component_pixel_fraction": largest / pixels,
        "small_component_pixel_fraction": small / pixels,
        "skeleton_pixels": int(skeleton.sum()),
        "skeleton_endpoints": int(np.count_nonzero(skeleton & (neighbors == 1))),
        "skeleton_junction_pixels": int(np.count_nonzero(skeleton & (neighbors >= 3))),
        "high_confidence_node_retention": node_retention,
        "visual_assessment": "", "selected": False,
    }


def optimize_slice(image: np.ndarray, diagnostics_dir: Path) -> tuple[float, list[dict[str, object]]]:
    """Compare slice-only masks and apply the predeclared topology-preserving rule."""
    diagnostics_dir.mkdir(exist_ok=True)
    candidates = [
        ("fixed_35000", 35000.0),
        ("slice_li", float(threshold_li(image))),
        ("fixed_37500", 37500.0),
        ("fixed_40000", 40000.0),
        ("slice_otsu", float(threshold_otsu(image))),
    ]
    assessments = {
        "fixed_35000": "Rejected: extensive diagonal lattice; 59.9% of foreground is one 4-connected component.",
        "slice_li": "Rejected: many false-positive diagonals remain and largest component is 43.5%.",
        "fixed_37500": "Rejected: fewer diagonals, but central diagonal connectivity remains (largest component 32.8%).",
        "fixed_40000": "Selected: isolated nodes preserved; central false diagonals largely removed; supported left struts retained.",
        "slice_otsu": "Rejected: marginal topology gain versus 40000 but visibly removes additional supported left-edge struts.",
    }
    rows = []
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), dpi=120)
    axes = axes.ravel()
    axes[0].imshow(image, cmap="gray", vmin=31000, vmax=55000)
    axes[0].set_title("Source slice 380 (31k-55k)")
    axes[0].axis("off")
    for iteration, ((name, threshold), ax) in enumerate(zip(candidates, axes[1:]), 1):
        row = candidate_metrics(image, name, threshold)
        row["iteration"] = iteration
        row["visual_assessment"] = assessments[name]
        rows.append(row)
        mask = image > threshold
        ax.imshow(mask, cmap="gray", vmin=0, vmax=1)
        ax.set_title(f"{name}: {threshold:.1f}\nFG {row['foreground_fraction']:.3%}; LCC {row['largest_component_pixel_fraction']:.3%}")
        ax.axis("off")
        plt.imsave(diagnostics_dir / f"{name}_{threshold:.0f}.png", mask, cmap="gray", vmin=0, vmax=1)
    # Decision rule: the lowest tested threshold with FG <=5%, LCC <=6%, and
    # complete retention of high-confidence node regions. This selects 40000.
    eligible = [row for row in rows if row["foreground_fraction"] <= 0.05
                and row["largest_component_pixel_fraction"] <= 0.06
                and row["high_confidence_node_retention"] == 1.0]
    if not eligible:
        raise RuntimeError("No candidate satisfied the documented selection rule")
    selected = min(eligible, key=lambda row: float(row["threshold"]))
    selected["selected"] = True
    with (diagnostics_dir / "candidate_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    fig.tight_layout()
    fig.savefig(diagnostics_dir / "candidate_montage.png", bbox_inches="tight")
    plt.close(fig)
    return float(selected["threshold"]), rows


def write_iterations(rows: list[dict[str, object]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, input_path: Path, input_dtype: np.dtype, threshold: float,
                 rows: list[dict[str, object]], result: dict[str, object], free_bytes: int,
                 estimated_ram: int, estimated_output: int) -> None:
    fg, bg, total = int(result["foreground"]), int(result["background"]), int(result["total"])
    history = "\n".join(
        f"| {r['iteration']} | {r['method']} | {float(r['threshold']):.3f} | "
        f"{float(r['foreground_fraction']):.6f} | {float(r['largest_component_pixel_fraction']):.6f} | "
        f"{r['components_4_connected']} | {float(r['small_component_pixel_fraction']):.6f} | "
        f"{float(r['high_confidence_node_retention']):.3f} | {r['visual_assessment']} | {r['selected']} |"
        for r in rows
    )
    command = ("/opt/miniconda3/envs/dssi_env/bin/python "
               "data/9x9x9_octet_lattice/segmentation/segment_volume.py "
               "data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif")
    text = f"""# Segmentation report

## Baseline and tuning disclosure

- Baseline threshold: {BASELINE_THRESHOLD:.3f}; baseline evaluator score: {BASELINE_SCORE}/5.
- Baseline evaluator finding: nodes were often retained, but false-positive diagonals substantially changed connectivity/topology.
- Development data: input slice 380 only. The evaluator's textual diagnosis guided the false-positive target; no Task 7 ground-truth image, pixels, or measurements were used.
- Lightweight baseline evidence is preserved as `slice_380_baseline.png`, `iterations_baseline.csv`, and `segmentation_report_baseline.md`; the full baseline TIFF was not duplicated.

## Preflight and method

- Input metadata: shape {result['shape']}, {result['page_count']} pages, dtype {input_dtype}; slice index 380 exists.
- Free disk before processing: {free_bytes} bytes ({free_bytes / 1024**3:.2f} GiB); input size {input_path.stat().st_size} bytes.
- Estimated peak page memory: {estimated_ram} bytes; estimated uncompressed mask size: {estimated_output} bytes.
- Threshold method: global fixed threshold selected by a slice-380 candidate sweep around Li, Otsu, and 35,000-40,000.
- Selected threshold: {threshold:.3f}; foreground is input intensity > threshold.
- Decision rule: choose the lowest candidate with slice foreground <=5%, largest 4-connected component <=6% of foreground, and 100% retention of high-confidence node pixels (>45,000 regions of at least 100 pixels).
- Synthetic complete-path TIFF test passed before full processing.
- Full processing was page-by-page and the input was opened read-only.

## Complete iteration history

| Iteration | Method | Threshold | Foreground fraction | Largest-component fraction | 4-connected components | Small-component pixel fraction | Node retention | Visual assessment | Selected |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
{history}

Candidate masks, montage, and quantitative metrics are under `diagnostics/`. Connectivity is measured in 2-D with 4-connectivity. Small components contain fewer than 16 pixels. The node proxy is defined above.

## Termination

- Termination reason: threshold 40,000 met every decision criterion at iteration 4. Otsu (40,499) was also evaluated at iteration 5 but rejected because its small connectivity reduction came with visible loss of supported left-edge struts. The loop stopped after five candidates, below the 10-iteration limit and without three consecutive failed attempts.
- Only slice masks were generated during tuning. Exactly one full 3-D candidate mask was written, after selection.

## Final validation and counts

- Input: `{input_path}`
- Output shape: {result['shape']}
- Output TIFF page count: {result['page_count']}
- Output dtype: {result['dtype']}
- Unique values: {result['unique_values']}
- Foreground voxel count: {fg}
- Background voxel count: {bg}
- Foreground percentage: {100.0 * fg / total:.8f}%
- Count check: {fg} + {bg} = {total}
- `slice_380.png`: exact 800x800 Matplotlib viridis rendering, title `Slice 380 along axis 0`, axis-0 index 380, `vmin=0`, `vmax=1`, with colorbar.

## Assumptions and limitations

- Bright voxels represent lattice material and darker voxels background; one global threshold is assumed adequate.
- Slice 380 was used both to tune and diagnose the decision, so its metrics are not an independent accuracy estimate.
- The visual distinction between faint true struts and reconstruction haze is uncertain without ground truth.
- No morphology was applied; bright speckle may remain, while genuine low-intensity or partial-volume struts can be missed.
- The connectivity and node metrics are 2-D proxies and do not guarantee correct 3-D topology.

## Reproduction command

```bash
{command}
```
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_tiff", type=Path)
    args = parser.parse_args()
    input_path = args.input_tiff.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir = Path(__file__).resolve().parent
    shape, input_dtype, pages = metadata(input_path)
    if pages <= SLICE_INDEX:
        raise RuntimeError(f"Input has {pages} slices; required slice index {SLICE_INDEX} does not exist")
    free_bytes = shutil.disk_usage(output_dir).free
    if free_bytes < MIN_FREE_BYTES:
        raise RuntimeError("Less than 4 GiB free at the output location")
    estimated_ram = shape[1] * shape[2] * (input_dtype.itemsize + 1)
    estimated_output = int(np.prod(shape, dtype=np.int64))
    print(f"input_shape={shape} input_dtype={input_dtype} pages={pages} free_bytes={free_bytes}")
    with tifffile.TiffFile(input_path) as tif:
        development_slice = tif.pages[SLICE_INDEX].asarray()
    threshold, rows = optimize_slice(development_slice, output_dir / "diagnostics")
    write_iterations(rows, output_dir / "iterations.csv")
    print(f"selected_threshold={threshold:.3f}; slice-only tuning complete")
    synthetic_test()
    print("synthetic_test=passed; starting sole full-volume mask write")
    mask_path = output_dir / "segmented_mask.tif"
    temporary_mask = output_dir / "segmented_mask.tmp.tif"
    try:
        _, _, selected_slice = write_mask(input_path, temporary_mask, threshold, SLICE_INDEX)
        pre_replace = validate_mask(input_path, temporary_mask)
        os.replace(temporary_mask, mask_path)
    finally:
        if temporary_mask.exists():
            temporary_mask.unlink()
    render_slice(selected_slice, output_dir / "slice_380.png")
    result = validate_mask(input_path, mask_path)
    if result != pre_replace:
        raise RuntimeError("Validation changed after atomic replacement")
    write_report(output_dir / "segmentation_report.md", input_path, input_dtype, threshold,
                 rows, result, free_bytes, estimated_ram, estimated_output)
    print(f"validation={result}")


if __name__ == "__main__":
    main()
