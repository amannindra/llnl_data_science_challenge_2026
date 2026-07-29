# tif2stl — validate the CT TIFF against the STL design mesh

Answers: *does the printed part captured in the X-ray CT scan match the STL it
was printed from?* The pipeline registers the STL into the CT voxel frame,
voxelizes it, and scores voxel-level agreement against the Otsu-segmented scan.

## Pipeline

```
raw CT TIFF (ZYX, uint16)         STL design mesh (XYZ, mm, origin-centred)
        |                                     |
 streamed Otsu histogram             bbox X-extent / 18
        |                                     |  mm per design unit
 downsampled boolean mask            STL -> design-unit affine
        |                                     |
        |          design JSON (0..18) ---- registered JSON (CT voxels)
        |                     \\   id-matched junction pairs   /
        |                      Umeyama similarity (39.4888 vox/unit, 0.335 deg)
        |                                     |
        |<--- score 24 proper cube rotations of the STL against the CT mask
        |                                     |
        |          composite STL -> CT-voxel transform (best orientation)
        |                                     |
        |                    subdivide triangles, mark + fill voxels
        \\                                    /
   Dice / IoU / containment (lattice window + full grid), slabs, overlays, gates
```

## Modules

| File | Purpose |
| --- | --- |
| `stl_geometry.py` | Streamed binary/ASCII STL triangle chunks, enclosed volume, deterministic subdivision, surface points |
| `registration.py` | Umeyama similarity fit, id-based junction pairing, STL→design affine, the 24 proper cube rotations |
| `voxelize.py` | Transform + rasterize an STL into a ZYX boolean grid (optional morphological fill; SciPy imported lazily) |
| `metrics.py` | Dice/IoU/containment, foreground bounds, per-slab rows, point-in-mask scoring, lattice-window slices |
| `validate.py` | CLI orchestrating the whole run (incl. the orientation search) and writing artifacts via `Components/reporting.py` |
| `visualize.py` | CLI writing three-up comparison panels per slice: STL design (expected) / CT scan (actual) / overlay |
| `meshlab_export.py` | Reusable, memory-bounded exporter for colored CT/STL voxel evidence layers and MeshLab project files |
| `meshlab_metrics.py` | CLI producing one MeshLab project per lattice-window metric, with exact counts and responsive display samples |

Everything imports side-effect free; the CLI entry points (`validate.py`,
`visualize.py`, and `meshlab_metrics.py`) write their requested artifacts.

## Run

```bash
conda run -n DSC python Aman_Scripts/tif2stl/validate.py            # defaults: 0.5-1 specimen
conda run -n DSC python Aman_Scripts/tif2stl/validate.py --downsample 2 --tolerance-cells 1
conda run -n DSC python Aman_Scripts/tif2stl/visualize.py           # comparison panels -> outputs/tif2stl/visuals
```

To inspect exactly ten evenly distributed axial CT/STL layers with the
plate-consistent orientation, run:

```bash
conda run -n DSC python Aman_Scripts/tif2stl/visualize.py \
  --stl-rotation +z+x+y \
  --z-fractions 0.08 0.17 0.26 0.35 0.44 0.53 0.62 0.71 0.80 0.89 \
  --no-cross-sections \
  --output-dir Aman_Scripts/outputs/tif2stl_plate/ten_layers
```

This writes exactly ten `compare_z*.png` panels. Each panel is `[STL design |
CT material | overlay]`; red means CT-only material, green means STL-only
material, and yellow means agreement. The 120-degree modelling-frame rotation
is explicit so this visual review matches the `tif2stl_plate` baseline rather
than the known plate-inconsistent auto-orientation choice.

To inspect the full 3-D evidence for each headline number directly in MeshLab,
run:

```bash
conda run -n DSC python Aman_Scripts/tif2stl/meshlab_metrics.py \
  --stl-rotation +z+x+y \
  --output-dir Aman_Scripts/outputs/tif2stl_plate/meshlab_metrics
```

This writes three MeshLab projects: `01_exact_dice.mlp` (yellow = exact CT/STL
overlap, red = CT-only, green = STL-only; Dice 44.83%),
`02_ct_within_design.mlp` (blue = CT within one downsampled cell of STL,
red = farther material; 73.47%), and `03_design_realized.mlp`
(yellow = STL supported by nearby CT, green = unsupported STL; 60.36%).
The percentages use every voxel in the lattice window. Each PLY contains a
deterministic, capped point sample only for display responsiveness, and its
layer name, PLY comments, and `metrics.json` retain the exact count.
For the exact project, the visual yellow share of red+yellow+green is the
**IoU** (28.89%), not the **Dice** (44.83%), because Dice counts the same
intersection against both input masks. The layer label reports Dice explicitly.

Artifacts land in `Aman_Scripts/outputs/tif2stl/`: `report.json`, `report.md`,
`slab_overlap.csv`, `overlay_*.png` (red = CT only, green = STL only, yellow =
agreement), and a SHA-256 `manifest.json`.

Gates (exit code 1 on failure): registration RMS ≤ `--max-rms` (1.0 vox),
lattice-window Dice ≥ `--min-dice` (0.0 = report-only), out-of-grid
surface-point fraction ≤ `--max-outside-fraction` (0.15).

## Coordinate model

- Registered JSON junction positions are **already CT voxel coordinates**;
  design JSON is lattice units 0..18; ids match record-for-record. Their
  Umeyama fit *is* the design→CT transform (RMS ~1e-12 voxels).
- STL millimetres → design units via bbox X-extent/18 (≈2.3052 mm/unit; X/Z
  axes carry no build plates). The implied pitch (~58.4 µm) differs from the
  nominal 58.1 µm by ~0.5% — reported, not hidden.
- The STL models its build plates on its **±Y** axis while the scanned part's
  plates lie at the CT **±Z** extremes, so STL→design needs a proper y↔z
  rotation. Near-cubic lattice symmetry makes bounding boxes useless for
  finding it; `--stl-rotation auto` (default) scores all 24 proper cube
  rotations by the fraction of sampled STL surface points landing in CT
  foreground and picks the winner (reported with runners-up).
- **Known auto-scorer bias**: sampling is per-triangle, so the few huge plate
  triangles contribute ~100 of 1.6M points and the score is dominated by the
  lattice interior, where a segmentation-quality falloff across CT X confounds
  it. On the 0.5-1 specimen `auto` picks the plate-inconsistent `-y-z+x` (hit
  0.4399); the plate-consistent `+z+x+y` (hit 0.3261) is better on every
  volumetric metric (window Dice 0.4483 vs 0.4448, CT-in-design 0.7347 vs
  0.7000, design-in-CT 0.6036 vs 0.5941) and puts the STL plates on the CT
  plate bands in the overlays. For this specimen pass
  `--stl-rotation "+z+x+y"` explicitly and confirm with `visualize.py`.
- The CT field of view crops the build plates; crop-opened solids cannot be
  hole-filled, so full-grid Dice and the voxelized volume undercount plate
  material. The **lattice-window** metrics (junction bounding box + 2 cells)
  are the headline numbers; full-grid values are reported alongside.

## Tests

`Aman_Scripts/ComponentTests/test_tif2stl.py` (99 adversarial checks, registered
in `run_all.py`): streaming/LFS/NaN/truncation failure modes, subdivision area
preservation, metric edge conventions, Umeyama recovery and degeneracy, the
24-rotation orientation search (including recovery of a planted y↔z rotation),
point-in-mask and window-slice conventions, voxel fill/determinism/budget, and
real-asset registration invariants. It additionally checks MeshLab PLY sampling,
native XYZ coordinate mapping, project-layer metadata, and invalid point-budget
handling.
