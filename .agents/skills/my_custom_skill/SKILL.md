---
name: threshold-optimizer
description: Compare and visualize multiple CT segmentation thresholds by calling the segment_ct_dataset and visualize_slice MCP tools repeatedly, saving a separate mask and slice image for each threshold. Use when the user asks to test, compare, sweep, visualize, or optimize segmentation thresholds for a volumetric .npy dataset.
---

# Threshold Optimization Workflow

## Inputs

Obtain:

- The path to the raw 3D `.npy` dataset.
- Threshold values supplied by the user.
- An output directory.
- An optional slice index and axis for visualization.

If a user does not provide thresholds, use `0.003`, `0.005`, and `0.007`.

If the user does not provide a slice index, use the middle slice along the selected axis. If the user does not provide an axis, use axis `0`.

For the unit-cell dataset, do not use thresholds outside the range `0.0001` to `0.01` unless the user explicitly requests them.

## Procedure

1. Confirm that the input file exists and is a three-dimensional NumPy array.
2. Create the output directory if it does not exist.
3. Call the `segment_ct_dataset` MCP tool once for each threshold.
4. Save every mask to a different file. Include the threshold in its filename.
5. Do not overwrite the original dataset.
6. Call the `visualize_slice` MCP tool once for each generated mask, using the same slice index and axis for every threshold.
7. Save each slice visualization as a separate PNG whose filename includes the threshold, slice index, and axis.
8. Confirm that every expected mask and PNG file was created.
9. Load each mask and calculate:
   - Array shape
   - Foreground voxel count
   - Background voxel count
   - Foreground percentage
10. Present the results and visualization paths in a Markdown comparison table.
11. Identify thresholds that produce empty or nearly full masks. Note when their slice images are blank.
12. Do not claim that a threshold is optimal without a ground-truth mask or another evaluation criterion.

## Output Naming

Convert the decimal point in a threshold to `p`.

For example:

- Threshold `0.003` → `unitcell_threshold_0p003.npy`
- Threshold `0.005` → `unitcell_threshold_0p005.npy`
- Threshold `0.007` → `unitcell_threshold_0p007.npy`

Name slice images with the same threshold token. For slice `128` along axis `0`:

- Threshold `0.003` → `unitcell_threshold_0p003_slice_128_axis_0.png`
- Threshold `0.005` → `unitcell_threshold_0p005_slice_128_axis_0.png`
- Threshold `0.007` → `unitcell_threshold_0p007_slice_128_axis_0.png`

## Output Directory

If the user does not provide an output directory, create and use `data/unitcell/threshold_comparison`.

## Comparison Table

Return results in this form:

| Threshold | Mask file | Slice image | Foreground voxels | Background voxels | Foreground percentage |
|---:|---|---|---:|---:|---:|
| 0.003 | path/to/mask | path/to/image | value | value | value |
| 0.005 | path/to/mask | path/to/image | value | value | value |
| 0.007 | path/to/mask | path/to/image | value | value | value |

Finish with a brief interpretation of how increasing the threshold changed the segmentation.
