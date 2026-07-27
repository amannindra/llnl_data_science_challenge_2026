---
name: threshold-optimizer
description: Optimize segmentation thresholds for lattice CT .npy datasets. Use when Codex needs to compare raw CT thresholds, generate masks and skeletons, inspect connectivity, produce threshold metrics/plots, recommend a working threshold, or prepare evidence for downstream NDE reports and segmentation subagents.
---

# Threshold Optimizer

## Overview

Optimize raw CT segmentation thresholds for lattice datasets. Treat threshold choice as a scientific decision: compare masks, skeleton connectivity, raw-slice agreement, overlap with ground truth when available, and defect-risk interpretation before recommending a working value.

## Core Rule

Distinguish these two thresholds:

- Raw CT segmentation threshold, such as `0.003` or `0.004`: decide which raw CT voxels become material.
- Binary surface visualization level, usually `0.5`: draw a surface from an already binary `0/1` mask.

Sweep the raw CT segmentation threshold. Do not optimize the `0.5` visualization level unless the input is not binary.

## Workflow

1. Inspect the dataset first.
   - Load the `.npy` file.
   - Report shape, dtype, min, max, mean, and useful percentiles.
   - Reject assumptions that thresholds should be in `[0, 1]`; this project has raw values around `-0.003` to `0.015` for `unitcell.npy`.

2. Choose threshold candidates.
   - Start broad enough to show behavior, for example `0.001,0.002,0.003,0.004,0.005,0.007,0.010`.
   - If a transition appears, run a fine sweep around it, for example `0.0030` to `0.0040`.
   - For `uint16` TIFF data, do not reuse `.npy` thresholds. Inspect the intensity range and sweep around sampled Otsu, for example `0.90 * Otsu` through `1.10 * Otsu`.

3. Generate outputs for each threshold.
   - Save a binary mask.
   - Skeletonize the mask.
   - Compute foreground/material voxel count and fraction.
   - Compute mask connected components using 26-neighbor connectivity.
   - Compute skeleton connected components, endpoints, branchpoint-like voxels, and skeleton voxel count.
   - Save metrics as CSV and JSON.

4. Create visual evidence.
   - Save raw center slices for context.
   - Save mask center-slice comparison images.
   - Save mask projection comparison images.
   - Save skeleton projection comparison images.
   - Save a metrics summary chart.

5. Interpret conservatively.
   - A lower threshold can include noise and make false pieces.
   - A higher threshold can remove real low-intensity edge material and make struts thin or broken.
   - A threshold that gives one connected skeleton is useful, but not automatically final.
   - Compare against raw slices, ground truth/CAD geometry, and expected strut diameter before claiming defects.
   - If ground truth is available, compare Dice, IoU, precision, recall, false positives, and false negatives. High recall alone is not enough because an over-thick mask can include almost all real material while also inventing extra material.

6. Document the result.
   - Write a short threshold report under `outputs/`.
   - Update `notes/00-big-picture.md`.
   - Update `notes/sections/01-how-to-run-code.md` with commands.
   - Update `notes/sections/05-task-log-and-experiments.md` with what changed, why, what worked, what failed, and next steps.
   - Update `notes/sections/02-physics-materials-imaging.md` when the interpretation touches materials science.

## Preferred Project Script

Use the project script when available:

```bash
python3 src/threshold_inspection.py --input <RAW_NPY> --output-dir <OUTPUT_DIR> --thresholds 0.001,0.002,0.003,0.004,0.005,0.007,0.010
```

For the current unit cell:

```bash
python3 src/threshold_inspection.py --input data/unitcell/unitcell.npy --output-dir outputs/threshold_inspection_script_check --thresholds 0.001,0.002,0.003,0.004,0.005,0.007,0.010
```

If the project script is missing or insufficient, implement the same behavior directly with NumPy, SciPy `ndimage.label`, and `skimage.morphology.skeletonize`.

## Current Unit-Cell Baseline

For `data/unitcell/unitcell.npy`, the completed threshold inspection found:

```text
threshold,material_fraction,mask_components,skeleton_components
0.001,0.062205,7589,7128
0.002,0.050518,341,328
0.003,0.046527,17,17
0.004,0.044235,1,1
0.005,0.043021,1,1
0.007,0.042480,1,1
0.010,0.037085,1,1
```

Interpretation:

- `0.003` looks acceptable in a center slice but gives `17` skeleton components in full 3D.
- `0.004` is the first tested threshold where both mask and skeleton become one connected component.
- Do not count the `17` components at `0.003` as `17` defects.
- Use `0.004` as the next working threshold for unit-cell connectivity analysis unless new evidence contradicts it.

## Materials Science Checks

When explaining results, connect threshold behavior to physical interpretation:

- Brighter CT voxels usually mean material because solid material attenuates X-rays more than air.
- Dim strut edges can be real partial-volume effects, not necessarily missing material.
- Low thresholds can make struts look too thick or noisy.
- High thresholds can make struts look too thin or broken.
- Real thick/thin strut variation can come from laser power, scan speed, melt pool size, layer thickness, powder behavior, heat buildup, and strut orientation.
- Treat missing/broken/thin/thick struts, dross, porosity, and warping as candidate defect categories, not automatic conclusions from one threshold.

## Task 6 Preparation

For a future segmentation subagent, preserve these outputs:

- candidate thresholds,
- selected working threshold and reasoning,
- masks and skeletons,
- slice/projection comparison images,
- metrics CSV/JSON,
- notes explaining what worked and what failed.

The subagent should be able to reuse this threshold optimizer workflow as its inner loop.

## Current 9x9x9 TIFF Lesson

For `data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`, the first-pass Task 6 threshold was:

```text
selected_threshold = 36916
selected_rule = 0.90 * sampled Otsu
```

Task 7 scored this result `3/5` because it preserved the main topology but over-segmented the lattice: struts and dots were too thick, so false positives dominated.

Improved calibration against the provided slice-380 ground truth found:

```text
selected_threshold = 38557
postprocess = open_close2d
Dice from cropped rendered panels = 0.8976
Precision from cropped rendered panels = 0.8309
Recall from cropped rendered panels = 0.9759
```

Use this as a workflow lesson, not as a universal threshold. Future datasets need their own sweep and inspection.
