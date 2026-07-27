# Focused Global Rerun Report

## Paths

- Input TIFF: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`
- Rerun output directory: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/segmentation`
- Reproducible script: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/segmentation/segment_lattice.py`
- Final mask TIFF: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/segmentation/segmented_mask.tif`
- Final slice image: [slice_380.png](slice_380.png)

## Input And Mask Metadata

- Input shape: `(761, 815, 837)`
- Input dtype: `>u2` (`uint16`)
- Input intensity range: `0` to `65535`
- Mask shape: `(761, 815, 837)`
- Mask dtype: `uint8`
- Mask values: binary `{0, 1}`

## Inspection And Optimization Approach

The input TIFF was validated as an existing 3D volume, and slice `380` was confirmed to exist on axis `0`. Inspection artifacts were saved in the rerun directory:

- `raw_slice_380.png`
- `inspection_histogram.png`
- `inspection_slices.png`

The sampled histogram remains consistent with the earlier focused run: a dominant background peak around the low-`30k` range plus a brighter material tail extending toward saturation. Representative slices `0`, `190`, `380`, `570`, and `760` show that slice `380` lies in the lattice interior, while the outer slices contain stronger surrounding boundary signal.

This rerun used the original global baseline only as a visual comparison target:

- Baseline reference from the original segmentation workspace: `method=global`, `threshold=39000`, `sigma=1.0`

The rerun itself was constrained exactly as requested. No CLAHE, local thresholding, background correction, hysteresis, or binary closing was used. No ground-truth image was inspected or used.

Requested preview candidates:

1. `threshold=39000`, `sigma=0.0`
2. `threshold=39000`, `sigma=0.5`
3. `threshold=40000`, `sigma=0.5`
4. `threshold=41000`, `sigma=0.5`
5. `threshold=40000`, `sigma=0.0`

Selection emphasized reducing excessive strut thickness and merged junctions relative to the `sigma=1.0` baseline while avoiding unnecessary loss of visibly present thin diagonal links.

## Iteration Table

Preview metrics below are for slice `380` only.

| Iter | Method | Parameters | FG frac | FG count | BG count | Connectivity evidence | Visible missing structure | Visible extra structure | Improved |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| 01 | `global` | `threshold=39000, sigma=0.0, min_size=8` | 0.056380 | 38,460 | 643,695 | 195 comps, largest 11.13% of FG | Right-half faint diagonals still mostly absent; a few left-side thin links look slightly brittle | Low; junctions are visibly thinner than the `sigma=1.0` baseline | No |
| 02 | `global` | `threshold=39000, sigma=0.5, min_size=8` | 0.056354 | 38,442 | 643,713 | 192 comps, largest 8.44% of FG | Right side still loses the faintest diagonals, but the left and middle lattice keep the best thin-link continuity in this rerun set | Low to mild; less blur-driven thickening than the `sigma=1.0` baseline | Yes |
| 03 | `global` | `threshold=40000, sigma=0.5, min_size=8` | 0.049323 | 33,646 | 648,509 | 197 comps, largest 5.69% of FG | More diagonal branches disappear in the left and middle field; right-side dots shrink further | Very low | No |
| 04 | `global` | `threshold=41000, sigma=0.5, min_size=8` | 0.043911 | 29,954 | 652,201 | 192 comps, largest 4.45% of FG | Severe link loss, including breaks in struts still visible in the raw slice | Minimal | No |
| 05 | `global` | `threshold=40000, sigma=0.0, min_size=8` | 0.049458 | 33,738 | 648,417 | 205 comps, largest 5.88% of FG | Similar link loss to iteration 03, with slightly rougher and more fragmented diagonals | Very low | No |

## Selected Method

Selected iteration: `02`

Final method:

- `global`
- `threshold=39000`
- `sigma=0.5`
- `min_size=8`

Why it was chosen:

- Compared with the original `sigma=1.0` baseline, it visibly reduces strut thickness and merged junctions along the bright left edge.
- Compared with iteration `01`, it preserves slightly smoother and more continuous thin links through the left and middle lattice while staying materially thinner than the `sigma=1.0` baseline.
- Iterations `03` through `05` suppress foreground more aggressively, but the raw slice shows that they remove thin diagonal material that is still visibly present, especially away from the bright left boundary.

## Final Mask Statistics

- Total voxels: `519,119,955`
- Foreground voxels: `63,783,110` (`12.286777%`)
- Background voxels: `455,336,845` (`87.713223%`)

## Iteration Termination

- Total iteration count: `5`
- Consecutive non-improving attempts at termination: `3`
- Termination reason: all five requested previews were generated before any full-volume run, iteration `02` was explicitly selected as the best preview, and iterations `03`, `04`, and `05` each failed to improve on it, leaving `3 consecutive attempts without improvement` at the end of the fixed five-candidate rerun.

## Verification

- `segment_lattice.py` exists and accepts the input TIFF path plus output directory.
- `segmented_mask.tif` is readable.
- The saved mask shape matches the input shape: `(761, 815, 837)`.
- The saved mask dtype is `uint8`.
- The saved mask values are binary `{0, 1}`.
- `slice_380.png` matches mask slice `380`.

## Limitations

This selection was made without ground-truth evaluation, so it is limited to the visible tradeoff between thinning over-merged structures and preserving lattice connectivity in slice `380` plus the representative raw-slice inspection. The chosen global threshold can still over-segment bright junction cores, under-segment faint right-side branches, or behave differently in other depths where attenuation changes. Stronger validation would require trusted annotations or downstream geometric checks.
