---
title: How To Run Code
created: 2026-07-21
tags:
  - run-commands
  - python
  - learning
---

# How To Run Code

This note is the quick-access place for commands you can run yourself.

Run all commands from the repository root:

```bash
cd "/Users/haseebahmad/Library/CloudStorage/OneDrive-UniversityofCaliforniaMerced/UCM - Academics/Research/LEAP/Calculations/LLNL/LLNL_Summer_26/DSC/llnl_data_science_challenge_2026"
```

## Check Where You Are

Print the current folder:

```bash
pwd
```

Check Git status:

```bash
git status --short --ignored
```

Check the current branch:

```bash
git branch --show-current
```

Expected branch right now:

```text
haseeb
```

## Task 1 - Run segment_ct_dataset

What this does:

It loads a 3D CT `.npy` file, applies a threshold, and saves a binary mask.

Important:

`unitcell.npy` is only the first example dataset. For other `.npy` datasets, replace the input path and choose a matching output path.

Run:

```bash
python3 -c "from src.mcp_server import segment_ct_dataset; print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/task1/unitcell_mask_threshold_0p003.npy', 0.003))"
```

General pattern:

```bash
python3 -c "from src.mcp_server import segment_ct_dataset; print(segment_ct_dataset('<INPUT_NPY_PATH>', '<OUTPUT_MASK_NPY_PATH>', <THRESHOLD>))"
```

What each part means:

- `python3 -c "..."` runs a short Python command directly from the terminal.
- `from src.mcp_server import segment_ct_dataset` imports the function we wrote.
- `data/unitcell/unitcell.npy` is the input CT volume.
- `outputs/task1/unitcell_mask_threshold_0p003.npy` is the output mask.
- `0.003` is the threshold.
- `print(...)` shows the function's returned message.

Expected output:

```text
Saved segmentation mask to outputs/task1/unitcell_mask_threshold_0p003.npy. shape=(256, 256, 256), dtype=uint8, threshold=0.003, foreground_voxels=780596, total_voxels=16777216, foreground_fraction=0.046527
```

## Validate The Saved Mask

Run:

```bash
python3 -c "import numpy as np; p='outputs/task1/unitcell_mask_threshold_0p003.npy'; a=np.load(p, mmap_mode='r'); vals, counts=np.unique(a, return_counts=True); print('shape', a.shape); print('dtype', a.dtype); print('unique_counts', dict(zip(vals.tolist(), counts.tolist()))); print('sum', int(a.sum()))"
```

Expected output:

```text
shape (256, 256, 256)
dtype uint8
unique_counts {0: 15996620, 1: 780596}
sum 780596
```

Meaning:

- Shape matches the original volume.
- Type is `uint8`, which stores small integers.
- Values are only `0` and `1`.
- `1` means foreground/material.
- `0` means background.

## Try A Different Threshold

Try threshold `0.005`:

```bash
python3 -c "from src.mcp_server import segment_ct_dataset; print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/task1/unitcell_mask_threshold_0p005.npy', 0.005))"
```

Try threshold `0.001`:

```bash
python3 -c "from src.mcp_server import segment_ct_dataset; print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/task1/unitcell_mask_threshold_0p001.npy', 0.001))"
```

Interpretation:

- Lower threshold usually marks more voxels as material.
- Higher threshold usually marks fewer voxels as material.
- The best threshold is not just the one with nice numbers. We need to visualize slices to judge quality.

## Quick Threshold Comparison

Run:

```bash
python3 -c "import numpy as np; a=np.load('data/unitcell/unitcell.npy', mmap_mode='r'); total=a.size; print('threshold,foreground_voxels,foreground_fraction');\nfor t in [0.001,0.002,0.003,0.005,0.01]:\n    c=int(np.count_nonzero(a>=t)); print(f'{t},{c},{c/total:.6f}')"
```

Known result:

```text
threshold,foreground_voxels,foreground_fraction
0.001,1043622,0.062205
0.002,847544,0.050518
0.003,780596,0.046527
0.005,721774,0.043021
0.01,622182,0.037085
```

## What Not To Run For Manual Testing

Do not use this while learning Task 1:

```bash
python3 src/mcp_server.py
```

Why:

That starts the MCP server and waits for an MCP client. For learning, directly importing and calling the function is clearer.

## MCP Config Check

The README/PDF also asks you to add this project as a Codex CLI MCP server.

This is now registered.

Check current MCP servers:

```bash
codex mcp list
```

Expected entry:

```text
segmentation-tools
```

If `segmentation-tools` is listed, Codex CLI can call these project functions as MCP tools.

The direct Python commands above still work because they bypass MCP and call the functions directly. Direct commands are still useful for learning and debugging.

## Task 2 - Visualize A Raw CT Slice

What this does:

It loads a 3D `.npy` file, extracts one 2D slice, and saves that slice as a PNG image.

Important:

For future datasets, replace the input path, output path, slice index, and axis.

Run:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('data/unitcell/unitcell.npy', 'outputs/task2/unitcell_raw_axis0_slice128.png', 128, 0))"
```

General pattern:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('<INPUT_NPY_PATH>', '<OUTPUT_IMAGE_PATH>', <SLICE_INDEX>, <AXIS>))"
```

What each part means:

- `visualize_slice` is the function we wrote for Task 2.
- `data/unitcell/unitcell.npy` is the raw CT input volume.
- `outputs/task2/unitcell_raw_axis0_slice128.png` is the PNG image that will be saved.
- `128` is the slice index.
- `0` is the axis, meaning we slice through axis 0.

Expected output:

```text
Saved slice visualization to outputs/task2/unitcell_raw_axis0_slice128.png. input_shape=(256, 256, 256), slice_shape=(256, 256), axis=0, slice_index=128, binary_mask=False, slice_min=-0.00168765, slice_max=0.0138864, slice_mean=0.00140412
```

What the image shows:

- A grayscale CT slice.
- Bright/white regions are higher-intensity material.
- Dark regions are lower-intensity background.

## Task 2 - Visualize A Mask Slice

Run:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('outputs/task1/unitcell_mask_threshold_0p003.npy', 'outputs/task2/unitcell_mask_t0p003_axis0_slice128.png', 128, 0))"
```

What each part means:

- `outputs/task1/unitcell_mask_threshold_0p003.npy` is the binary mask from Task 1.
- `outputs/task2/unitcell_mask_t0p003_axis0_slice128.png` is the saved mask image.
- `128` is the same slice index as the raw image.
- `0` is the same axis as the raw image.

Expected output:

```text
Saved slice visualization to outputs/task2/unitcell_mask_t0p003_axis0_slice128.png. input_shape=(256, 256, 256), slice_shape=(256, 256), axis=0, slice_index=128, binary_mask=True, slice_min=0, slice_max=1, slice_mean=0.11763
```

What the image shows:

- Black means mask value `0`, or background.
- White means mask value `1`, or segmented material.
- For this slice, threshold `0.003` captures the main diamond-shaped lattice cross-section cleanly.

## View The Generated Images

List the generated images:

```bash
ls -lh outputs/task2
```

Open the raw slice image on macOS:

```bash
open outputs/task2/unitcell_raw_axis0_slice128.png
```

Open the mask slice image on macOS:

```bash
open outputs/task2/unitcell_mask_t0p003_axis0_slice128.png
```

Note:

The `open` command launches a macOS app to view the image. Codex may ask for approval before running GUI-opening commands, but you can run them yourself in Terminal.

## Try A Different Slice Or Axis

Try slice `64` along axis `0`:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('data/unitcell/unitcell.npy', 'outputs/task2/unitcell_raw_axis0_slice064.png', 64, 0))"
```

Try slice `128` along axis `1`:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('data/unitcell/unitcell.npy', 'outputs/task2/unitcell_raw_axis1_slice128.png', 128, 1))"
```

Try slice `128` along axis `2`:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('data/unitcell/unitcell.npy', 'outputs/task2/unitcell_raw_axis2_slice128.png', 128, 2))"
```

Axis meaning:

- Axis `0`: fix the first dimension and view the other two.
- Axis `1`: fix the second dimension and view the other two.
- Axis `2`: fix the third dimension and view the other two.

For a volume with shape `(256, 256, 256)`, valid slice indices are `0` through `255` for every axis.

## Generate A Slice Survey

What this does:

It makes raw and mask images for:

```text
axes:   0, 1, 2
slices: 64, 128, 192
```

This creates `18` individual images:

```text
9 raw CT images
9 mask images
```

Run:

```bash
python3 - <<'PY'
from src.mcp_server import visualize_slice

axes = [0, 1, 2]
slices = [64, 128, 192]
raw_input = 'data/unitcell/unitcell.npy'
mask_input = 'outputs/task1/unitcell_mask_threshold_0p003.npy'

for axis in axes:
    for slice_index in slices:
        raw_output = f'outputs/task2/slice_survey/raw/unitcell_raw_axis{axis}_slice{slice_index:03d}.png'
        mask_output = f'outputs/task2/slice_survey/mask_t0p003/unitcell_mask_t0p003_axis{axis}_slice{slice_index:03d}.png'
        print(visualize_slice(raw_input, raw_output, slice_index, axis))
        print(visualize_slice(mask_input, mask_output, slice_index, axis))
PY
```

Outputs:

```text
outputs/task2/slice_survey/raw/
outputs/task2/slice_survey/mask_t0p003/
```

## Generate Contact Sheets

What this does:

It combines the slice survey images into two overview images:

```text
outputs/task2/slice_survey/raw_contact_sheet.png
outputs/task2/slice_survey/mask_t0p003_contact_sheet.png
```

Run:

```bash
python3 - <<'PY'
from PIL import Image, ImageDraw
from pathlib import Path

base = Path('outputs/task2/slice_survey')
configs = [
    ('raw', 'unitcell_raw_axis{axis}_slice{slice_index:03d}.png', 'raw_contact_sheet.png', 'Raw CT slices'),
    ('mask_t0p003', 'unitcell_mask_t0p003_axis{axis}_slice{slice_index:03d}.png', 'mask_t0p003_contact_sheet.png', 'Mask slices, threshold 0.003'),
]
axes = [0, 1, 2]
slices = [64, 128, 192]
thumb_size = (360, 360)
label_height = 36
margin = 20
header_height = 50

for folder, pattern, output_name, title in configs:
    images = []
    for axis in axes:
        row = []
        for slice_index in slices:
            path = base / folder / pattern.format(axis=axis, slice_index=slice_index)
            img = Image.open(path).convert('RGB')
            img.thumbnail(thumb_size)
            canvas = Image.new('RGB', (thumb_size[0], thumb_size[1] + label_height), 'white')
            x = (thumb_size[0] - img.width) // 2
            canvas.paste(img, (x, label_height))
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 10), f'axis {axis}, slice {slice_index}', fill='black')
            row.append(canvas)
        images.append(row)

    sheet_width = margin * 2 + thumb_size[0] * len(slices)
    sheet_height = margin * 2 + header_height + (thumb_size[1] + label_height) * len(axes)
    sheet = Image.new('RGB', (sheet_width, sheet_height), 'white')
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), title, fill='black')

    y = margin + header_height
    for row in images:
        x = margin
        for img in row:
            sheet.paste(img, (x, y))
            x += thumb_size[0]
        y += thumb_size[1] + label_height

    output_path = base / output_name
    sheet.save(output_path)
    print(output_path)
PY
```

Open the contact sheets on macOS:

```bash
open outputs/task2/slice_survey/raw_contact_sheet.png
open outputs/task2/slice_survey/mask_t0p003_contact_sheet.png
```

## Task 3 - Run skeletonize

What this does:

It loads a binary segmentation mask and creates a thin centerline skeleton.

Input:

```text
outputs/task1/unitcell_mask_threshold_0p003.npy
```

This is the Task 1 binary mask:

```text
0 = background
1 = material
```

Output:

```text
outputs/task3/unitcell_skeleton_t0p003.npy
```

This is the Task 3 skeleton:

```text
False = background
True = skeleton centerline
```

Run:

```bash
python3 -c "from src.mcp_server import skeletonize; print(skeletonize('outputs/task1/unitcell_mask_threshold_0p003.npy', 'outputs/task3/unitcell_skeleton_t0p003.npy'))"
```

Expected output:

```text
Saved skeleton to outputs/task3/unitcell_skeleton_t0p003.npy. shape=(256, 256, 256), dtype=bool, mask_voxels=780596, skeleton_voxels=3314, total_voxels=16777216, skeleton_fraction_of_mask=0.004245
```

Meaning:

- `mask_voxels=780596`: number of material voxels in the segmentation mask.
- `skeleton_voxels=3314`: number of voxels left after reducing the structure to centerlines.
- `skeleton_fraction_of_mask=0.004245`: the skeleton is much smaller than the full mask, as expected.

Important:

Do not use the raw CT file as input to `skeletonize()`.

Wrong input:

```text
data/unitcell/unitcell.npy
```

Correct input:

```text
outputs/task1/unitcell_mask_threshold_0p003.npy
```

Reason:

Skeletonization expects a binary mask, not grayscale CT intensity data.

## Validate The Skeleton

Run:

```bash
python3 -c "import numpy as np; p='outputs/task3/unitcell_skeleton_t0p003.npy'; a=np.load(p, mmap_mode='r'); vals, counts=np.unique(a, return_counts=True); print('shape', a.shape); print('dtype', a.dtype); print('unique_counts', dict(zip(vals.tolist(), counts.tolist()))); print('skeleton_voxels', int(np.count_nonzero(a)))"
```

Expected output:

```text
shape (256, 256, 256)
dtype bool
unique_counts {False: 16773902, True: 3314}
skeleton_voxels 3314
```

## Visualize A Skeleton Slice

Run:

```bash
python3 -c "from src.mcp_server import visualize_slice; print(visualize_slice('outputs/task3/unitcell_skeleton_t0p003.npy', 'outputs/task3/unitcell_skeleton_t0p003_axis0_slice128.png', 128, 0))"
```

Expected output:

```text
Saved slice visualization to outputs/task3/unitcell_skeleton_t0p003_axis0_slice128.png. input_shape=(256, 256, 256), slice_shape=(256, 256), axis=0, slice_index=128, binary_mask=True, slice_min=0, slice_max=1, slice_mean=0.00270081
```

Open the image on macOS:

```bash
open outputs/task3/unitcell_skeleton_t0p003_axis0_slice128.png
```

Important visual interpretation:

A 3D skeleton can look broken in a single 2D slice because the centerline may move above or below that slice. A single slice only shows where the 3D skeleton intersects that plane.

## Task 4 - Generate NDE Report

Task 4 uses the project skill in:

```text
.agents/skills/nde_report_expert/
```

Simple meaning:

- NDE means non-destructive evaluation.
- Here, it means inspecting the lattice using CT data without cutting the sample open.
- The report combines the raw CT volume, the binary mask, the skeleton, and 3D pictures.

Current input files:

```text
data/unitcell/unitcell.npy
outputs/task1/unitcell_mask_threshold_0p003.npy
outputs/task3/unitcell_skeleton_t0p003.npy
```

Current output files:

```text
outputs/task4/unitcell_nde_report.md
outputs/task4/unitcell_nde_metrics.json
outputs/task4/unitcell_nde_view_a_elev30_azim45.png
outputs/task4/unitcell_nde_view_b_elev60_azim45.png
```

Open the report on macOS:

```bash
open outputs/task4/unitcell_nde_report.md
```

Open the output folder on macOS:

```bash
open outputs/task4
```

Recreate the two 3D visualization images:

```bash
python3 -c "from pathlib import Path; import importlib.util, os; out=Path('outputs/task4'); out.mkdir(parents=True, exist_ok=True); os.environ.setdefault('MPLCONFIGDIR', str(out / '.matplotlib-cache')); spec=importlib.util.spec_from_file_location('skill_visualize_3d', '.agents/skills/nde_report_expert/scripts/3d_visualize.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.visualize_3d_with_skeleton('outputs/task1/unitcell_mask_threshold_0p003.npy', 'outputs/task3/unitcell_skeleton_t0p003.npy', 'outputs/task4/unitcell_nde_view_a_elev30_azim45.png', threshold=0.5, downsample_factor=2, elev=30.0, azim=45.0); mod.visualize_3d_with_skeleton('outputs/task1/unitcell_mask_threshold_0p003.npy', 'outputs/task3/unitcell_skeleton_t0p003.npy', 'outputs/task4/unitcell_nde_view_b_elev60_azim45.png', threshold=0.5, downsample_factor=2, elev=60.0, azim=45.0)"
```

Important command meaning:

- `visualize_3d_with_skeleton(...)` draws the mask as a transparent 3D surface and overlays the skeleton in red.
- `threshold=0.5` is used because the input here is a binary mask with values `0` and `1`.
- `downsample_factor=2` uses every second voxel to make the 3D plot faster.
- `elev` means camera height angle.
- `azim` means camera rotation angle around the object.

Current report result:

```text
foreground_voxels = 780,596
material_fraction = 0.046527
skeleton_voxels = 3,314
connected_skeleton_components = 17
endpoints = 73
branchpoints = 158
mean_intensity_inside_mask = 0.011069
mean_intensity_outside_mask = 0.000025
```

Simple interpretation:

The mask selected bright CT material because the average raw intensity inside the mask is much larger than the average raw intensity outside the mask.

## Threshold Inspection - Completed Run

Important:

- Sweep the Task 1 segmentation threshold, not the Task 4 visualization level.
- Task 1 threshold examples: `0.002`, `0.003`, `0.004`, `0.005`, `0.007`, `0.01`.
- Task 4 visualization `threshold=0.5` is only for drawing the surface of a binary mask with values `0` and `1`.

Simple meaning:

```text
0.003 asks: which raw CT voxels are material?
0.5 asks: where is the surface between mask value 0 and mask value 1?
```

Suggested next run:

```bash
python3 -c "import numpy as np; a=np.load('data/unitcell/unitcell.npy', mmap_mode='r'); total=a.size; print('threshold,foreground_voxels,foreground_fraction'); [print(f'{t},{int(np.count_nonzero(a>=t))},{np.count_nonzero(a>=t)/total:.6f}') for t in [0.001,0.002,0.003,0.004,0.005,0.007,0.01]]"
```

After that, create masks for the most interesting thresholds:

```bash
python3 -c "from src.mcp_server import segment_ct_dataset; print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/threshold_inspection/unitcell_mask_t0p002.npy', 0.002)); print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/threshold_inspection/unitcell_mask_t0p003.npy', 0.003)); print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/threshold_inspection/unitcell_mask_t0p005.npy', 0.005)); print(segment_ct_dataset('data/unitcell/unitcell.npy', 'outputs/threshold_inspection/unitcell_mask_t0p010.npy', 0.01))"
```

Then compare:

- foreground voxel counts,
- slice images across the same axes and slice indices,
- skeleton voxel counts,
- skeleton connected components,
- whether lower thresholds connect noisy background,
- whether higher thresholds break thin struts.

Reusable script added:

```text
src/threshold_inspection.py
```

Run the same main threshold inspection again:

```bash
python3 src/threshold_inspection.py --input data/unitcell/unitcell.npy --output-dir outputs/threshold_inspection_script_check --thresholds 0.001,0.002,0.003,0.004,0.005,0.007,0.010
```

Arguments:

- `--input`: raw `.npy` CT volume to analyze.
- `--output-dir`: folder where masks, skeletons, metrics, and summary plot are saved.
- `--thresholds`: comma-separated raw CT thresholds to test.

Main completed outputs:

```text
outputs/threshold_inspection/threshold_inspection_report.md
outputs/threshold_inspection/threshold_metrics.csv
outputs/threshold_inspection/threshold_metrics.json
outputs/threshold_inspection/threshold_metrics_summary.png
outputs/threshold_inspection/raw_intensity_histogram_thresholds.png
outputs/threshold_inspection/mask_center_slices_threshold_comparison.png
outputs/threshold_inspection/mask_projection_threshold_comparison.png
outputs/threshold_inspection/skeleton_projection_threshold_comparison.png
```

Open the threshold report:

```bash
open outputs/threshold_inspection/threshold_inspection_report.md
```

Open the output folder:

```bash
open outputs/threshold_inspection
```

Main result:

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

Fine sweep around `0.003` to `0.004`:

```text
threshold,material_fraction,mask_components,skeleton_components
0.0030,0.046527,17,17
0.0032,0.046034,12,12
0.0034,0.045587,9,8
0.0036,0.045133,6,6
0.0038,0.044668,2,2
0.0040,0.044235,1,1
```

Simple conclusion:

`0.004` is the first tested threshold that gives one connected mask and one connected skeleton for `unitcell.npy`.

## Task 5 - Custom Threshold Optimizer Skill

Task 5 created a project-specific Codex skill:

```text
.agents/skills/threshold-optimizer/SKILL.md
```

Simple meaning:

A skill is a reusable instruction card for Codex. It tells a future Codex session how to do one kind of work consistently.

This skill teaches Codex how to:

- inspect a raw `.npy` CT dataset,
- sweep raw CT segmentation thresholds,
- create masks and skeletons,
- compute connectivity metrics,
- make visual comparisons,
- avoid confusing threshold artifacts with real defects,
- update the project notebook,
- prepare evidence for Task 6's segmentation subagent.

Validate the skill:

```bash
python3 /Users/haseebahmad/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/threshold-optimizer
```

Expected output:

```text
Skill is valid!
```

Important:

After adding or editing a project skill, restart Codex from the repo root.

Run:

```bash
cd "/Users/haseebahmad/Library/CloudStorage/OneDrive-UniversityofCaliforniaMerced/UCM - Academics/Research/LEAP/Calculations/LLNL/LLNL_Summer_26/DSC/llnl_data_science_challenge_2026"
codex
```

Then you can ask:

```text
Use $threshold-optimizer to compare thresholds for data/unitcell/unitcell.npy and recommend a working segmentation threshold.
```

Why restart:

Codex only discovers new local project skills when it starts from the repository root. The current running session may not automatically reload newly created skills.

## Task 6 - Segmentation Subagent

Task 6 created this subagent config:

```text
.codex/agents/segmentation_agent.toml
```

Simple meaning:

A subagent is a specialized worker. This one is designed to segment a `.tif` or `.tiff` CT lattice dataset, save the mask, save slice `380`, compute metrics, and write a report.

Model settings:

```toml
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
```

Why use this:

- Task 6 is more autonomous than the earlier tools.
- The subagent has its own instructions and stopping rules.
- It must stop after `10` total iterations or `3` failed attempts.
- It must not fake results if the `.tif` file is only a Git LFS pointer.

Validate the TOML file:

```bash
python3 -c "import tomllib; from pathlib import Path; p=Path('.codex/agents/segmentation_agent.toml'); data=tomllib.loads(p.read_text()); print(data['name'], data['model'], data['model_reasoning_effort'])"
```

Expected output:

```text
segmentation_agent gpt-5.5 xhigh
```

Current blocker:

```text
data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif
```

is currently a Git LFS pointer, not the real CT data. It is only about `135` bytes.

Check it:

```bash
ls -lh data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif
head -n 1 data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif
```

If the first line is:

```text
version https://git-lfs.github.com/spec/v1
```

then the real data has not been downloaded yet.

Current status:

The real Task 6 TIFF has now been downloaded. It is about `990 MB`.

Run Task 6 segmentation again:

```bash
python3 data/9x9x9_octet_lattice/segmentation/segment_lattice.py --input data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif --output-dir data/9x9x9_octet_lattice/segmentation --slice-index 380 --sample-step 40
```

Expected important output:

```text
Selected threshold: 36916
Foreground fraction: 0.149986
```

Task 6 output files:

```text
data/9x9x9_octet_lattice/segmentation/segment_lattice.py
data/9x9x9_octet_lattice/segmentation/mask.tif
data/9x9x9_octet_lattice/segmentation/slice_380.png
data/9x9x9_octet_lattice/segmentation/metrics.json
data/9x9x9_octet_lattice/segmentation/report.md
data/9x9x9_octet_lattice/segmentation/intensity_histogram.png
data/9x9x9_octet_lattice/segmentation/threshold_preview_slice_380.png
```

Open the result image:

```bash
open data/9x9x9_octet_lattice/segmentation/slice_380.png
```

Open the report:

```bash
open data/9x9x9_octet_lattice/segmentation/report.md
```

Task 6 result:

```text
input_shape = (761, 815, 837)
input_dtype = uint16
sampled_otsu_threshold = 41018
selected_threshold = 36916
foreground_voxels = 77860468
background_voxels = 441259487
total_voxels = 519119955
foreground_fraction = 0.149986
slice_380_foreground_fraction = 0.077230
slice_380_components_2d = 297
```

Simple interpretation:

- The TIFF intensity scale is much larger than `unitcell.npy`; values are `uint16`.
- Otsu threshold `41018` was too strict for slice `380` because it removed many thin struts.
- Threshold `36916`, which is `0.9 * Otsu`, preserved more visible lattice struts.
- This is a first-pass global-threshold segmentation, not a final defect diagnosis.

If using the subagent after restarting Codex, ask:

```text
Use the segmentation_agent subagent to segment data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif and save the required Task 6 outputs.
```

## Task 7 - Segmentation Evaluation Rubric

Task 7 created this rubric:

```text
evals/rubric_segmentation_1.md
```

Simple meaning:

The rubric is the grading rule. It tells an evaluator how to compare our segmentation result against the ground truth.

Images compared:

```text
ground truth = data/9x9x9_octet_lattice/ground_truth_segmentation_slice_380.png
result       = data/9x9x9_octet_lattice/segmentation/slice_380.png
```

Run the Codex CLI evaluation manually:

```bash
codex \
  -i data/9x9x9_octet_lattice/ground_truth_segmentation_slice_380.png \
  -i data/9x9x9_octet_lattice/segmentation/slice_380.png \
  "Use evals/rubric_segmentation_1.md as the rubric. The first attached image is the ground truth. The second attached image is the result. Return only JSON with reasoning and score."
```

Current saved evaluation:

```text
evals/segmentation_eval_slice_380_result.json
evals/segmentation_eval_slice_380_report.md
evals/segmentation_eval_slice_380_metrics.json
evals/segmentation_slice_380_data_panel_comparison.png
```

Open the evaluation report:

```bash
open evals/segmentation_eval_slice_380_report.md
```

Open the comparison image:

```bash
open evals/segmentation_slice_380_data_panel_comparison.png
```

Result:

```json
{
  "score": 3
}
```

Simple interpretation:

- The segmentation found almost all real material.
- It did not miss much of the lattice.
- But it added extra material and made many struts/dots too thick.
- So the result is useful but not final.

Helper metrics:

```text
Dice = 0.765548
IoU = 0.620152
Precision = 0.620886
Recall = 0.998097
```

Simple metric meanings:

- High recall means we captured almost all ground-truth material.
- Lower precision means we also captured too much extra material.
- This matches the visual result: over-segmentation dominates.

## Improve Task 7 Segmentation

Use this when you want to improve the 9x9x9 segmentation using the provided slice-380 ground truth.

Run from the repository root:

```bash
python3 data/9x9x9_octet_lattice/segmentation/segment_lattice.py \
  --input data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif \
  --output-dir data/9x9x9_octet_lattice/segmentation_improved \
  --slice-index 380 \
  --sample-step 40 \
  --ground-truth-slice data/9x9x9_octet_lattice/ground_truth_segmentation_slice_380.png \
  --ground-truth-panel-bbox 164,645,101,596 \
  --postprocess open_close2d
```

What the important inputs mean:

- `--input` is the raw 3D TIFF CT scan.
- `--output-dir` is where the improved mask, slice image, metrics, and report are saved.
- `--ground-truth-slice` is the answer-key image for slice `380`.
- `--ground-truth-panel-bbox` crops only the actual data panel from the rendered ground-truth PNG.
- `--postprocess open_close2d` removes tiny extra bits and fills tiny holes on each 2D slice.

Important caution:

Do not use ground truth for a normal Task 6 first-pass segmentation unless the task allows it. Ground truth is usually for evaluation. Here we used it because we were explicitly debugging why Task 7 scored `3/5`.

Improved outputs:

```text
data/9x9x9_octet_lattice/segmentation_improved/mask.tif
data/9x9x9_octet_lattice/segmentation_improved/slice_380.png
data/9x9x9_octet_lattice/segmentation_improved/metrics.json
data/9x9x9_octet_lattice/segmentation_improved/candidate_metrics.csv
data/9x9x9_octet_lattice/segmentation_improved/report.md
evals/segmentation_eval_slice_380_improved_report.md
evals/segmentation_slice_380_improved_data_panel_comparison.png
```

Improved result:

```text
selected_threshold = 38557
postprocess = open_close2d
Dice = 0.897587
IoU = 0.814202
Precision = 0.830945
Recall = 0.975851
false positives = 2713
false negatives = 330
```

Simple interpretation:

- The old result was like drawing the lattice with a marker that was too thick.
- The improved result uses a thinner marker.
- It removes much of the extra material while still keeping most real material.
- It is better, but not automatically perfect.

## Missing-Struts Data Inspection

Run from the repository root:

```bash
python3 src/inspect_missing_struts_data.py
```

What this does:

- Reads the missing-struts TIFF metadata and sampled intensities.
- Reads the nominal and registered JSON graph files.
- Reads STL triangle counts and bounding boxes.
- Computes the nominal-to-registered JSON transform.
- Estimates how many struts each STL design removes from triangle-count changes.
- Converts the paper's reported missing/disconnected percentages into approximate strut counts.
- Quantifies the small tilt between the registered lattice graph and the image slice grid.
- Saves a beginner-friendly report and visual checks.

Outputs:

```text
outputs/missing_struts_inventory/report.md
outputs/missing_struts_inventory/summary.json
outputs/missing_struts_inventory/tif_sample_slices.png
outputs/missing_struts_inventory/registered_json_overlay_z380.png
```

Open the detailed report:

```bash
open outputs/missing_struts_inventory/report.md
```

Open the visual checks:

```bash
open outputs/missing_struts_inventory/tif_sample_slices.png
open outputs/missing_struts_inventory/registered_json_overlay_z380.png
```

Simple interpretation:

- The TIFF is the actual CT scan.
- The registered JSON is already aligned to this TIFF.
- The STL files are design meshes and are not directly aligned to the TIFF.
- Use registered JSON plus TIFF for first defect analysis.
- The current scan is specimen `0.5% (#1)`.
- The paper reports about `105` missing struts and about `918` disconnected struts for this specimen, using our JSON strut count as an approximate denominator.

## Part 2 Phase 0 - Canonical Graph Foundation

Use this when you want to rerun the Part 2 preflight and canonical graph adapter.

Run from the repository root:

```bash
python3 -m src.part2.phase0
```

What this does:

- Checks the required Part 2 data files.
- Detects Git LFS pointer files versus real local data.
- Reads the actual JSON schema.
- Builds canonical physical graphs from the 8x8 fixture, nominal 9x9 JSON, and registered 9x9 JSON.
- Merges raw junction aliases into physical nodes.
- Preserves raw junction, strut, and unit-cell IDs for provenance.
- Computes nominal-to-registered graph transform/residuals.
- Saves Phase 0 reports under `outputs/part2/phase0/`.

Main outputs:

```text
outputs/part2/phase0/data_inventory.json
outputs/part2/phase0/graph_schema_report.md
outputs/part2/phase0/canonical_graph_summary.json
outputs/part2/phase0/nominal_registered_transform.json
outputs/part2/phase0/qc/nominal_registered_residuals.csv
outputs/part2/phase0/qc/nominal_registered_residual_histogram.png
```

Canonical graph outputs:

```text
outputs/part2/phase0/canonical_graphs/fixture_8x8.canonical_graph.json
outputs/part2/phase0/canonical_graphs/nominal_9x9.canonical_graph.json
outputs/part2/phase0/canonical_graphs/registered_9x9.canonical_graph.json
```

Run the tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected result:

```text
Ran 6 tests
OK
```

Compile-check the Part 2 files:

```bash
python3 -m py_compile src/part2/io/lattice_graph.py src/part2/phase0.py tests/part2/test_lattice_graph.py
```

Open the report:

```bash
open outputs/part2/phase0/graph_schema_report.md
```

Open the QC histogram:

```bash
open outputs/part2/phase0/qc/nominal_registered_residual_histogram.png
```

Simple interpretation:

- The JSON graph has many raw junction labels that point to fewer real physical nodes.
- The adapter merges those labels, like combining duplicate names for the same street corner.
- After merging, the 9x9 graph has `3430` physical nodes and `18468` physical struts.
- The registered graph is the same network placed into the CT voxel coordinate system.

## Part 2 Phase 1 - STL Design Intent And CT Sampler Skeleton

Use this when you want to rerun the STL design-intent mapping.

Run from the repository root:

```bash
python3 -m src.part2.phase1
```

What this does:

- Verifies required Phase 0 graph outputs exist.
- Reads `data/missing_struts/stls/0.stl`.
- Reads `data/missing_struts/stls/0.5.stl`.
- Checks whether direct triangle-set difference is clean enough.
- Maps likely intentionally removed `0.5.stl` struts to canonical 9x9 edge IDs.
- Prepares registered CT edge sample coordinates.
- Saves outputs under `outputs/part2/phase1/`.

Main outputs:

```text
outputs/part2/phase1/stl_inspection.json
outputs/part2/phase1/triangle_difference_audit.json
outputs/part2/phase1/design_intent_edge_map.json
outputs/part2/phase1/design_intent_edges.csv
outputs/part2/phase1/design_intent_ranked_scores.csv
outputs/part2/phase1/registered_edge_sampler_preview.json
outputs/part2/phase1/qc/design_intent_score_histogram.png
outputs/part2/phase1/design_intent_review_panels.json
outputs/part2/phase1/qc/review_panels/
outputs/part2/phase1/phase1_summary.md
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected result:

```text
Ran 14 tests
OK
```

Compile-check Phase 1 code:

```bash
python3 -m py_compile src/part2/design_intent/stl_design_mapping.py src/part2/ct_features/edge_sampler.py src/part2/phase1.py
```

Open the Phase 1 summary:

```bash
open outputs/part2/phase1/phase1_summary.md
```

Open the score histogram:

```bash
open outputs/part2/phase1/qc/design_intent_score_histogram.png
```

Open the visual review panels folder:

```bash
open outputs/part2/phase1/qc/review_panels
```

Open the strongest flagged example:

```bash
open outputs/part2/phase1/qc/review_panels/rank_001_E_N000357_N001495.png
```

Open the weakest flagged example:

```bash
open outputs/part2/phase1/qc/review_panels/rank_092_E_N004612_N005752.png
```

Open the strongest unflagged near miss:

```bash
open outputs/part2/phase1/qc/review_panels/rank_093_E_N007944_N007950.png
```

Simple interpretation:

- `0.stl` is the full design.
- `0.5.stl` is the design with about `0.5%` of struts intentionally removed.
- Phase 1 found `92` likely intentionally removed canonical edges.
- These are design labels, not final CT defect labels.
- Phase 2 must check the actual CT image before saying what was printed.

## Part 2 CT Review Index - Find Edges In The TIFF

Use this when you want exact TIFF slice/window locations for Phase 1 edge IDs.

Run:

```bash
python3 -m src.part2.visual_review.ct_review_index
```

Outputs:

```text
outputs/part2/phase1/ct_review/ct_review_summary.json
outputs/part2/phase1/ct_review/ct_review_index_selected_edges.csv
outputs/part2/phase1/ct_review/ct_review_index_flagged_edges.csv
outputs/part2/phase1/ct_review/ct_review_points_selected_edges.csv
```

What this does:

- Reads the registered canonical graph.
- Reads the Phase 1 edge score table.
- Reads only TIFF metadata, not the full CT intensity volume.
- Writes a table with `z` slice range, `x/y` window, endpoints, midpoint, raw junction IDs, and source strut ID.

Important:

This does not classify CT defects. It only tells you where to look.

Example selected review row:

```text
rank 1, edge E_N000357_N001495:
center z slice = 125
z range = 97 to 153
y range = 222 to 311
x range = 668 to 717
```

Open the selected review CSV:

```bash
open outputs/part2/phase1/ct_review/ct_review_index_selected_edges.csv
```

Open the full 92 flagged-edge review CSV:

```bash
open outputs/part2/phase1/ct_review/ct_review_index_flagged_edges.csv
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected current result:

```text
Ran 21 tests
OK
```

## Part 2 CT Edge Panels - Easier Than Manual Slice Hunting

Use this when Napari scrolling is too confusing and you want focused review images for selected registered edges.

Run:

```bash
python3 -m src.part2.visual_review.ct_edge_panels
```

Outputs:

```text
outputs/part2/phase1/ct_review/panels/rank_001_E_N000357_N001495_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_020_E_N000357_N000361_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_091_E_N007819_N008957_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_092_E_N004612_N005752_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_093_E_N007944_N007950_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_094_E_N006880_N006900_ct_panel.png
outputs/part2/phase1/ct_review/panels/rank_100_E_N003004_N004143_ct_panel.png
outputs/part2/phase1/ct_review/panels/ct_edge_panel_summary.json
outputs/part2/phase1/ct_review/panels/ct_edge_panel_summary.csv
```

Generate only a few ranks:

```bash
python3 -m src.part2.visual_review.ct_edge_panels --ranks 1,92,93,100
```

Disable the yellow visual threshold contour:

```bash
python3 -m src.part2.visual_review.ct_edge_panels --material-threshold -1
```

Create the simplified rank 001 versus rank 100 comparison:

```bash
python3 -m src.part2.visual_review.ct_edge_compare --ranks 1,100
```

Output:

```text
outputs/part2/phase1/ct_review/comparisons/rank_001_vs_rank_100_ct_comparison.png
outputs/part2/phase1/ct_review/comparisons/rank_001_vs_rank_100_ct_comparison.json
```

Open the panel folder:

```bash
open outputs/part2/phase1/ct_review/panels
```

Open the comparison folder:

```bash
open outputs/part2/phase1/ct_review/comparisons
```

What each panel shows:

- Top row: local `XY`, `XZ`, and `YZ` maximum projections.
- Cyan line: registered expected edge path.
- Bottom left: edge-aligned straightened slab.
- Bottom right: intensity profile along the edge.
- Yellow contour/line: visual threshold reference only, not final classification.

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected current result:

```text
Ran 23 tests
OK
```

## Part 2 Phase 2A - CT Sampler Calibration

Use this when you want to rerun the Phase 2A calibration workflow.

Run:

```bash
python3 -m src.part2.phase2a
```

Main outputs:

```text
outputs/part2/phase2a/run_manifest.json
outputs/part2/phase2a/calibration_manifest.csv
outputs/part2/phase2a/edge_features.csv
outputs/part2/phase2a/edge_parameter_features.csv
outputs/part2/phase2a/parameter_sweep_summary.csv
outputs/part2/phase2a/group_separation_report.md
outputs/part2/phase2a/qc/
```

Open the Phase 2A report:

```bash
open outputs/part2/phase2a/group_separation_report.md
```

Open the Phase 2A review panels:

```bash
open outputs/part2/phase2a/qc/review_panels
```

Open the edge-level feature table:

```bash
open outputs/part2/phase2a/edge_features.csv
```

Open the parameter sweep table:

```bash
open outputs/part2/phase2a/parameter_sweep_summary.csv
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected current result:

```text
Ran 29 tests
OK
```

Important:

- Phase 2A is calibration only.
- It does not produce final missing/disconnected percentages.
- Current result says Phase 2B is still blocked because the calibration groups did not separate cleanly.

## Part 2 Phase 2A1 - Design Intent Repair And Gold Review

Use this when you want to rerun the exact STL design-intent repair and regenerate the human-review packet.

Run:

```bash
python3 -m src.part2.phase2a1
```

Main outputs:

```text
outputs/part2/phase2a1/preflight_report.md
outputs/part2/phase2a1/run_manifest.json
outputs/part2/phase2a1/existing_method_audit.md
outputs/part2/phase2a1/design_intent_exact_scores.csv
outputs/part2/phase2a1/exact_distance_method.md
outputs/part2/phase2a1/symmetry_transform_ranking.csv
outputs/part2/phase2a1/symmetry_audit.md
outputs/part2/phase2a1/provisional_design_intent_map.json
outputs/part2/phase2a1/provisional_design_intent_edges.csv
outputs/part2/phase2a1/gold_review/review_index.html
outputs/part2/phase2a1/gold_review/human_labels.csv
outputs/part2/phase2a1/phase2a1_stop_report.md
```

Open the Phase 2A.1 STOP report:

```bash
open outputs/part2/phase2a1/phase2a1_stop_report.md
```

Open the gold review packet:

```bash
open outputs/part2/phase2a1/gold_review/review_index.html
```

Open the blank human-label CSV:

```bash
open outputs/part2/phase2a1/gold_review/human_labels.csv
```

Open the exact-score table:

```bash
open outputs/part2/phase2a1/design_intent_exact_scores.csv
```

Open the transform ranking:

```bash
open outputs/part2/phase2a1/symmetry_transform_ranking.csv
```

Run only the new Phase 2A.1 tests:

```bash
python3 -m unittest tests.part2.test_phase2a1_exact_stl_distance -v
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Expected current result:

```text
Ran 38 tests
OK
```

Important:

- Phase 2A.1 does not produce final CT missing/disconnected percentages.
- It repairs the STL design-intent evidence and creates the review set.
- Current mapping status is `UNRESOLVED`.
- Do not start Phase 2B until the gold-review CSV is labeled.

If you need true Parquet output later:

```bash
python3 -m pip install pyarrow
python3 -m src.part2.phase2a1
```

Do not install `pyarrow` unless you intentionally want the larger optional dependency. The CSV and JSON files are enough for current review work.

## Part 2 Phase 2R - Method Pivot And Benchmark

What this does:

Phase 2R benchmarks a new hybrid method before final CT classification.

It has three branches:

- Design-only STL voxel subtraction.
- CT-only straightened strut atlas.
- Late fusion to rank the 48 graph/STL cube transforms.

Run the full Phase 2R benchmark:

```bash
python3 -m src.part2.phase2r
```

Expected runtime from the completed run:

```text
about 464 seconds
about 3.1 GB peak memory
```

Run only the Phase 2R tests:

```bash
python3 -m unittest tests.part2.test_phase2r_hybrid_benchmark -v
```

Current expected result:

```text
Ran 11 tests
OK
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result after the Phase 2R coverage-gate fix:

```text
Ran 49 tests
OK
```

Open the main Phase 2R reports:

```bash
open outputs/part2/phase2r/design/design_difference_report.md
open outputs/part2/phase2r/ct/ct_atlas_report.md
open outputs/part2/phase2r/fusion/fusion_report.md
open outputs/part2/phase2r/method_comparison_report.md
```

Important current result:

```text
0.1% STL occupancy components = 7
0.5% STL occupancy components = 67
1.0% STL occupancy components = 104
fusion transform status = PROVISIONAL
best transform = perm021_signmmm
```

Why `PROVISIONAL`:

The leading transform had CT features for only `7` of `67` mapped deleted-volume components. That is a useful clue, but not enough to call the cube orientation verified.

Next recommended command for checking Git status without LFS clean-filter errors:

```bash
git -c filter.lfs.clean=cat -c filter.lfs.smudge=cat -c filter.lfs.process= -c filter.lfs.required=false status --short --branch
```

## Part 2 Phase 2R1 - Anchor Review And Transform Resolution

What this does:

Phase 2R.1 expands CT coverage around likely transform candidates and creates a small human-anchor review packet.

Run:

```bash
python3 -m src.part2.phase2r1
```

Current completed run:

```text
expanded CT feature edges = 1300
newly sampled CT edges = 800
best transform = perm021_signmmm
status = ANCHOR_GATE_PASSED after repaired human-anchor labels
```

Open the report:

```bash
open outputs/part2/phase2r1/phase2r1_report.md
```

Open the anchor review packet:

```bash
open outputs/part2/phase2r1/anchor_review.html
```

Open the human label CSV:

```bash
open outputs/part2/phase2r1/human_anchor_labels.csv
```

Important CSV note:

```text
outputs/part2/phase2r1/human_anchor_labels.csv
```

is currently a Numbers/iWork-style ZIP file with a `.csv` name, not a readable CSV. Use this repaired CSV instead:

```bash
open outputs/part2/phase2r1/human_anchor_labels_repaired_2026-07-26.csv
```

Run the anchor-gate check:

```bash
python3 -m src.part2.phase2r1_anchor_gate --label-csv outputs/part2/phase2r1/human_anchor_labels_repaired_2026-07-26.csv
```

Latest anchor-gate report:

```bash
open outputs/part2/phase2r1/anchor_gate_runs/20260726_220926/anchor_gate_report.md
```

Latest anchor-gate result:

```text
anchor_gate_status = ANCHOR_GATE_PASSED
best_transform_id = perm021_signmmm
phase2b_gate_recommendation = READY_TO_PREPARE_PHASE2B_CALIBRATION
```

Only review the first five rows first:

```text
anchor_role = primary_anchor
```

Fill only this column if you want to keep it simple:

```text
transform_anchor_label
```

Allowed values:

```text
same_physical_location
not_same_physical_location
unclear
```

Run focused Phase 2R/2R.1 tests:

```bash
python3 -m unittest tests.part2.test_phase2r_hybrid_benchmark -v
```

Current expected result:

```text
Ran 19 tests
OK (skipped=1 if VTK is not installed)
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 57 tests
OK (skipped=1 if VTK is not installed)
```

Important:

- Use `outputs/part2/phase2r1/anchor_panels/` as the current panel folder.
- Ignore the older `outputs/part2/phase2r1/panels/` folder if present; it contains stale panels from an earlier internal run.
- Phase 2R.1 does not publish final defect percentages.
- The next step is Phase 2B CT calibration preparation, not final classification.

## Part 2 Phase 2B - CT Calibration Preparation

What this does:

Phase 2B calibration preparation checks whether human-anchored design-removed struts look different from sampled design-present/control struts in CT features.

Run:

```bash
python3 -m src.part2.phase2b_calibration
```

Latest valid run:

```text
outputs/part2/phase2b/20260726_222359/
```

Open the report:

```bash
open outputs/part2/phase2b/20260726_222359/calibration_report.md
```

Open the QC plot:

```bash
open outputs/part2/phase2b/20260726_222359/qc/anomaly_score_by_design_state.png
```

Main result:

```text
status = CALIBRATION_PREP_COMPLETE_NOT_FINAL_CLASSIFICATION
transform = perm021_signmmm
CT feature rows used = 1300
design-removed candidate feature rows = 67
design-present/control feature rows = 1233
ct_missing_material_anomaly_score AUC = 0.9626
candidate anomaly threshold = 2.0135
uncertain/review-needed rows = 80
```

Important:

- This is calibration, not final classification.
- It does not report final missing/disconnected percentages.
- The next step is to review/generate panels for the 80 uncertain rows and decide whether to expand CT sampling toward all `18,468` edges.

Run Phase 2B tests:

```bash
python3 -m unittest tests.part2.test_phase2b_calibration -v
```

Current expected result:

```text
Ran 6 tests
OK
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 63 tests
OK (skipped=1 if VTK is not installed)
```

## Part 2 Phase 2B.1 - Design Reconciliation

What this does:

Phase 2B.1 fixes the confusion between deleted STL components and deleted strut edges. One connected deleted STL component can contain multiple struts.

Run:

```bash
python3 -m src.part2.phase2b1_reconcile
```

Latest valid run:

```text
outputs/part2/phase2b1/20260726_231259/
```

Open the report:

```bash
open outputs/part2/phase2b1/20260726_231259/phase2b1_report.md
```

Open the review panels:

```bash
open outputs/part2/phase2b1/20260726_231259/review_panels
```

Main result:

```text
deleted STL components = 67
volume-estimated strut-equivalent count = 94
unique selected canonical edge candidates = 94
new CT edges sampled = 26
combined CT feature rows = 1326
design-removed candidate feature rows = 94
design-present/control feature rows = 1232
ct_missing_material_anomaly_score AUC = 0.9635
review panels generated = 16
```

Important:

- `67` is a connected-blob count.
- `94` is the current strut-edge candidate count after allowing big blobs to contain multiple struts.
- This reconciles well with the expected `0.5% * 18,468 ~= 92`.
- This is still not final classification.

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 65 tests
OK (skipped=1 if VTK is not installed)
```

## Part 2 Phase 2B.2 - All-Edge CT Sampling Prep

What this does:

Phase 2B.2 samples more registered strut edges in the TIFF and builds a non-final candidate classification table. It expands coverage toward all `18,468` graph edges, but it does not publish final missing/disconnected percentages.

Run a bounded batch from Phase 2B.1:

```bash
python3 -m src.part2.phase2b2_all_edge_prep --max-new-edges 1000 --review-panels 20
```

Latest valid run:

```text
outputs/part2/phase2b2/20260727_013304/
```

Open the report:

```bash
open outputs/part2/phase2b2/20260727_013304/phase2b2_report.md
```

Open the review panels:

```bash
open outputs/part2/phase2b2/20260727_013304/review_panels
```

Current full all-edge feature table:

```text
outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv
```

Resume after an interrupted run that already wrote a partial checkpoint:

```bash
python3 -m src.part2.phase2b2_all_edge_prep \
  --base-features-csv outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv \
  --extra-features-csv outputs/part2/phase2b2/YOUR_INTERRUPTED_RUN/newly_sampled_ct_features.partial.csv \
  --max-new-edges 1000 \
  --review-panels 20
```

Run all remaining edges in one longer run:

```bash
python3 -m src.part2.phase2b2_all_edge_prep \
  --base-features-csv outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv \
  --sample-all \
  --review-panels 40
```

Main result:

```text
prior CT feature rows = 2326
new CT edges sampled = 16142
combined CT feature rows = 18468
remaining unsampled edges = 0
design-removed candidate edges = 94
candidate_design_removed_missing_like = 90
uncertain_design_removed_low_ct_anomaly = 4
candidate_unexpected_missing_like = 1137
uncertain_near_threshold_present_like = 718
candidate_present_like = 16519
```

Important:

- These are candidate statuses, not final labels.
- `candidate_unexpected_missing_like` means the design did not say removed, but CT looks missing-like in the sampled features.
- Final percentages are still blocked until all-edge sampling and uncertainty handling are complete.

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 71 tests
OK (skipped=1 if VTK is not installed)
```

## Part 2 Phase 2B3 - Guarded CT Labels

What this does:

It reads the completed all-edge CT feature table from Phase 2B.2 and assigns
guarded, review-aware labels to every expected strut.

Important:

This is still not a final publication command. It creates a label table and a
review queue.

Run:

```bash
python3 -m src.part2.phase2b3_guarded_labels --max-review-panels 60
```

Latest valid run:

```text
outputs/part2/phase2b3/20260727_090709/
```

Open the report:

```bash
open outputs/part2/phase2b3/20260727_090709/label_summary_report.md
```

Open the review panels:

```bash
open outputs/part2/phase2b3/20260727_090709/review_panels
```

Main output table:

```text
outputs/part2/phase2b3/20260727_090709/guarded_edge_labels.csv
```

Top review queue:

```text
outputs/part2/phase2b3/20260727_090709/top_possible_unintended_edges.csv
```

Run the same label logic without rendering PNG panels:

```bash
python3 -m src.part2.phase2b3_guarded_labels --skip-panels
```

Run the targeted Phase 2B.3 tests:

```bash
python3 -m unittest tests.part2.test_phase2b3_guarded_labels -v
```

Current expected result:

```text
Ran 6 tests
OK
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 77 tests
OK (skipped=1 if VTK is not installed)
```

Main result from latest run:

```text
total registered edges = 18468
designed_removed_ct_absent = 88
designed_removed_ct_disconnected_or_residual_material = 1
designed_removed_ct_uncertain = 1
designed_removed_ct_present_like_conflict = 4
possible_unintended_missing = 420
possible_unintended_disconnected = 58
uncertain_review_required = 3076
present_like = 14820
review_required_count = 3573
```

Meaning:

- `present_like` means CT evidence looks connected/present.
- `possible_unintended_missing` means design did not mark the strut removed, but CT looks almost empty.
- `possible_unintended_disconnected` means design did not mark the strut removed, but CT looks broken or gapped.
- `uncertain_review_required` means the evidence is mixed, near-threshold, threshold-sensitive, or registration-sensitive.
- These counts are guarded screening labels, not final published percentages.

## Part 2 Phase 2B4 - Automated Evidence Review

What this does:

It reads the Phase 2B.3 guarded labels and applies stricter automatic review
rules. This separates clean auto-supported candidates from rows that still need
manual review.

Run:

```bash
python3 -m src.part2.phase2b4_automated_review --max-spotcheck-panels 80
```

Latest valid run:

```text
outputs/part2/phase2b4/20260727_092219/
```

Open the report:

```bash
open outputs/part2/phase2b4/20260727_092219/draft_defect_summary_not_for_publication.md
```

Open the spot-check panels:

```bash
open outputs/part2/phase2b4/20260727_092219/spotcheck_panels
```

Main output table:

```text
outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv
```

Auto-supported possible unintended candidates:

```text
outputs/part2/phase2b4/20260727_092219/auto_supported_unintended_candidates.csv
```

Manual-review queue:

```text
outputs/part2/phase2b4/20260727_092219/manual_review_queue.csv
```

Rerun without rendering panels:

```bash
python3 -m src.part2.phase2b4_automated_review --skip-panels
```

Run targeted Phase 2B.4 tests:

```bash
python3 -m unittest tests.part2.test_phase2b4_automated_review -v
```

Current expected result:

```text
Ran 5 tests
OK
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current expected result:

```text
Ran 82 tests
OK (skipped=1 if VTK is not installed)
```

Main result from latest run:

```text
auto_supported_possible_unintended_missing = 202
auto_supported_possible_unintended_disconnected = 12
auto_supported_possible_unintended_combined = 214
auto_supported_designed_removed_absent_or_disconnected = 89
auto_supported_present_like = 14820
blocked_manual_review = 920
low_priority_uncertain_not_defect_like = 2425
```

Important:

`214 / 18,468` is about `1.16%`, but this is a draft automated-review
fraction, not a final published percentage.

## Part 2 Final Report And Agentic System

What this does:

It reads the completed Phase 2B.4 automated-review output and the user's
rank `001-040` human spot-check labels. It creates one final report package
with a beginner-readable report, machine-readable summary, compact tables, a QC
figure, and an agentic workflow guide.

Run:

```bash
python3 -m src.part2.final_report --phase2b4-dir outputs/part2/phase2b4/20260727_092219
```

Latest valid run:

```text
outputs/part2/final_report/20260727_123413/
```

Open the final report:

```bash
open outputs/part2/final_report/20260727_123413/final_ct_defect_report.md
```

Open the agentic workflow guide:

```bash
open outputs/part2/final_report/20260727_123413/agentic_workflow.md
```

Main files:

```text
outputs/part2/final_report/20260727_123413/final_ct_defect_report.md
outputs/part2/final_report/20260727_123413/final_ct_defect_summary.json
outputs/part2/final_report/20260727_123413/tables/headline_numbers.csv
outputs/part2/final_report/20260727_123413/figures/automated_review_label_counts.png
```

Run targeted final-report tests:

```bash
python3 -m unittest tests.part2.test_final_report -v
```

Validate the Part 2 defect-analysis skill:

```bash
python3 /Users/haseebahmad/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/part2-defect-analysis
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current result:

```text
targeted final-report tests: Ran 4 tests, OK
skill validation: Skill is valid
full Part 2 tests after Phase 2C/viewer/pipeline: Ran 93 tests, OK, skipped 1 optional VTK test
```

Main final-report interpretation:

```text
auto-supported possible unintended combined = 214
total expected struts = 18468
draft automated possible-unintended fraction = 1.16%
human top-40 spot-check = 36 defect-like, 4 ambiguous, 0 present-like contradictions
status = SPOTCHECK_SUPPORTED_AUTOMATED_ESTIMATE_NOT_FULL_GROUND_TRUTH
```

Important:

This is a spot-check-supported automated estimate. It is not fully exhaustive
human-labeled ground truth. The `920` blocked manual-review rows remain
unresolved and should not be silently counted as defects.

## Part 2 Phase 2C - Automatic Manual-Queue Triage

What this does:

It reads the Phase 2B.4 all-edge automated-review table and performs a second
automatic triage pass. It does not rescan the full TIFF. It promotes only very
clear blocked cases and keeps mixed cases review-required.

Run with review panels:

```bash
python3 -m src.part2.phase2c_manual_queue_triage --phase2b4-dir outputs/part2/phase2b4/20260727_092219 --max-review-panels 120
```

Latest dedicated run:

```text
outputs/part2/phase2c/20260727_132248/
```

Open the report:

```bash
open outputs/part2/phase2c/20260727_132248/manual_queue_triage_report.md
```

Open the review panels:

```bash
open outputs/part2/phase2c/20260727_132248/review_packet/panels
```

Run without rendering review panels:

```bash
python3 -m src.part2.phase2c_manual_queue_triage --phase2b4-dir outputs/part2/phase2b4/20260727_092219 --skip-panels
```

Main output files:

```text
outputs/part2/phase2c/20260727_132248/phase2c_labels.csv
outputs/part2/phase2c/20260727_132248/phase2c_summary.json
outputs/part2/phase2c/20260727_132248/phase2c_auto_supported_unintended_candidates.csv
outputs/part2/phase2c/20260727_132248/phase2c_remaining_review_queue.csv
outputs/part2/phase2c/20260727_132248/review_packet/
```

Run targeted Phase 2C tests:

```bash
python3 -m unittest tests.part2.test_phase2c_manual_queue_triage -v
```

Current Phase 2C result:

```text
total registered struts checked = 18468
auto-supported possible unintended missing = 215
auto-supported possible unintended disconnected = 13
auto-supported possible unintended combined = 228
newly promoted from blocked rows = 14
still review-required = 677
low-priority uncertain, not counted as defects = 2654
```

Important:

`228 / 18,468` is about `1.23%`, but this is the newest automated triage result,
not full human-labeled ground truth. The earlier `214 / 18,468` final package is
still the current spot-check-supported report baseline.

## Part 2 Local Defect Viewer

What this does:

It exports a dependency-free local HTML viewer that draws all registered struts
as colored lines. This is a quick global map, not a full CT surface renderer.

Generate the viewer from the latest dedicated Phase 2C labels:

```bash
python3 -m src.part2.visualization.export_defect_viewer --labels-csv outputs/part2/phase2c/20260727_132248/phase2c_labels.csv
```

Latest viewer:

```text
outputs/part2/visualization/20260727_132343/index.html
```

Open it on macOS:

```bash
open outputs/part2/visualization/20260727_132343/index.html
```

Viewer colors:

```text
gray = present-like
red = possible unintended missing
orange = possible unintended disconnected
blue = intentionally designed removed
purple = still review-required
yellow = low-priority uncertain
```

Generated viewer files:

```text
outputs/part2/visualization/20260727_132343/index.html
outputs/part2/visualization/20260727_132343/viewer_data.json
outputs/part2/visualization/20260727_132343/legend.json
outputs/part2/visualization/20260727_132343/run_manifest.json
```

## Part 2 Automatic Pipeline Runner

What this does:

It reads `configs/part2.yaml`, checks raw data files, runs the current automatic
layers, exports a viewer, and writes one pipeline manifest. This is the first
single-command entry point for the agentic system.

Dry run first:

```bash
python3 -m src.part2.run_defect_pipeline --config configs/part2.yaml --dry-run
```

Latest dry-run output:

```text
outputs/part2/pipeline_runs/20260727_132540/
```

Run the current pipeline:

```bash
python3 -m src.part2.run_defect_pipeline --config configs/part2.yaml
```

Latest full pipeline output:

```text
outputs/part2/pipeline_runs/20260727_132552/
```

What this latest pipeline run did:

```text
Phase 2C triage, without regenerating panels
local viewer export
conservative final report package from Phase 2B.4
```

Latest pipeline result:

```text
phase2c auto-supported possible unintended combined = 228
phase2c still review-required = 677
viewer edge count = 18468
final report baseline remains 214 spot-check-supported candidates
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Current result:

```text
Ran 93 tests
OK
skipped 1 optional VTK test
```
