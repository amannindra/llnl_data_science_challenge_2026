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

Everything imports side-effect free; only `validate.py` writes files.

## Run

```bash
conda run -n DSC python Aman_Scripts/tif2stl/validate.py            # defaults: 0.5-1 specimen
conda run -n DSC python Aman_Scripts/tif2stl/validate.py --downsample 2 --tolerance-cells 1
conda run -n DSC python Aman_Scripts/tif2stl/visualize.py           # comparison panels -> outputs/tif2stl/visuals
```

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

`Aman_Scripts/ComponentTests/test_tif2stl.py` (84 adversarial checks, registered
in `run_all.py`): streaming/LFS/NaN/truncation failure modes, subdivision area
preservation, metric edge conventions, Umeyama recovery and degeneracy, the
24-rotation orientation search (including recovery of a planted y↔z rotation),
point-in-mask and window-slice conventions, voxel fill/determinism/budget, and
real-asset registration invariants.
