---
name: nde-report
description: Generate a non-destructive evaluation (NDE) markdown report from volumetric, mask, and skeleton .npy files, including two fixed-perspective 3D renders. Use when asked for an NDE report, defect report, or lattice inspection writeup.
---

# NDE Report Generation Protocol

You are the **Non-Destructive Evaluation Report Expert**. Run every step in the
`DSC` conda environment (`conda run -n DSC python ...`).

## Step 1 — Feature extraction

- **Original volume**: load the raw intensity `.npy`. Remember raw CT values are
  ~`[-0.003, 0.015]`, not `[0, 1]` — threshold with Otsu, not 0.5.
- **Segmented mask**: load the mask `.npy`. If it does not exist, generate it with
  the MCP tool `segment_ct_dataset()` (see `src/mcp_server.py`).
- **Skeleton**: load the skeleton `.npy`. If it does not exist, generate it with
  the MCP tool `skeletonize()`.
- Compute mean intensity, volume (voxel count and material fraction), connected
  components, and skeletal complexity (endpoints, branch voxels).

Prefer `Scripts/Components/segmentation.py` and `asset_io.py` over ad-hoc code.

## Step 2 — 3D visualization

Use `.agents/skills/nde_report_expert/scripts/3d_visualize.py`. It exposes
`visualize_3d(file_path, output_path, threshold, downsample_factor, elev, azim)`
and `visualize_3d_with_skeleton(...)` as importable functions (no CLI) — import
and call them. Render twice:

| View | `elev` | `azim` |
| :--- | ---: | ---: |
| View A | 30.0 | 45.0 |
| View B | 60.0 | 45.0 |

## Step 3 — Report compilation

Write a markdown report containing:

1. **Summary table** — metrics for the volume, mask, and skeleton, with units.
2. **Visual gallery** — both 3D renders embedded by relative path.
3. **Analysis** — brief interpretation of mask-to-volume alignment, plus any
   caveats (artifacts, unvalidated steps, thresholds chosen).

## Constraints

- Check `.npy` shapes for compatibility before processing; volumes are `[z, y, x]`.
- Write outputs under `Scripts/outputs/`.
- Save `.tif` images through Pillow, never `matplotlib.imsave`.
- Delete any helper Python scripts you created once the report is done.
