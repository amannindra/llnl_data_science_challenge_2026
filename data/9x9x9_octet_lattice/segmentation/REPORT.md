# Segmentation Report: 9x9x9 Octet Lattice

## Paths

- Input path: `data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`
- Output directory: `data/9x9x9_octet_lattice/segmentation/`
- Final script: `data/9x9x9_octet_lattice/segmentation/segment_lattice.py`
- Final mask: `data/9x9x9_octet_lattice/segmentation/segmented_mask.tif`
- Final slice image: [slice_380.png](slice_380.png)

## Input Summary

- Input shape: `(761, 815, 837)`
- Input dtype: `uint16`
- Output mask shape: `(761, 815, 837)`
- Output mask dtype: `uint8`

## Inspection Summary

- Representative raw slices inspected: `z = 0, 95, 190, 285, 380, 475, 570, 665, 760`
- Slice `380` showed bright lattice nodes and struts on a darker background, but the lattice intensity decayed from left to right across the field of view.
- A stratified histogram sample of `96,390` voxels had percentiles:
  - `p50 = 32523`
  - `p75 = 35378.75`
  - `p90 = 50662`
  - `p95 = 54370.55`
- The histogram suggested a bright-material segmentation, but slice `380` showed that a single global raw-intensity threshold would under-segment the dimmer right-hand struts.

## Final Method

Selected method: slice-wise Gaussian smoothing, slice-wise background subtraction, thresholding on the background-corrected image, minimum smoothed-intensity gating, and one iteration of 2D binary closing.

Final parameters:

- `sigma = 0.8`
- `background_sigma = 12.0`
- `threshold = 900.0` on `gaussian(slice, 0.8) - gaussian(slice, 12.0)`
- `min_intensity = 32000.0` on the smoothed slice
- `closing_iters = 1`
- `opening_iters = 0`

## Iteration History

Metric region for proxy scoring: slices `z = 372, 374, 376, 378, 380, 382, 384, 386, 388`

| Iteration | Parameters | Foreground Fraction (metric region) | 3D Proxy Evidence | Outcome |
| --- | --- | ---: | --- | --- |
| 1 | Global threshold `43000`, `sigma 0.8`, close `1` | `0.0411` | `120` components, largest `97.33%`, `116` small comps | Baseline only. Preserved bright nodes but dropped most struts. |
| 2 | Global threshold `45000`, `sigma 0.8`, close `1` | `0.0303` | `612` components, largest `20.59%`, `532` small comps | Failed. Much more fragmented than iteration 1. |
| 3 | Global threshold `47000`, `sigma 0.8`, close `1` | `0.0216` | `713` components, largest `2.91%`, `549` small comps | Failed. Severe under-segmentation. |
| 4 | Global threshold `39000`, `sigma 0.8`, close `1` | `0.0690` | `26` components, largest `99.27%`, `15` small comps | Improved. Recovered many left-side struts and sharply reduced noise. |
| 5 | Global threshold `40000`, `sigma 1.0`, close `1` | `0.0607` | `24` components, largest `99.29%`, `16` small comps | Failed. Slightly cleaner than iteration 4 but lost visible strut continuity. |
| 6 | Global threshold `41000`, `sigma 1.0`, close `2` | `0.0537` | `21` components, largest `99.33%`, `18` small comps | Failed. Further under-segmented the lattice. |
| 7 | Global threshold `36000`, `sigma 0.8`, close `1` | `0.1002` | `21` components, largest `99.76%`, `10` small comps | Improved. Best pure global-threshold result; recovered much more of the lattice but still missed dim right-side struts. |
| 8 | Global threshold `37000`, `sigma 0.8`, close `1` | `0.0881` | `23` components, largest `99.26%`, `11` small comps | Failed. Less strut continuity than iteration 7. |
| 9 | Global threshold `38000`, `sigma 0.8`, close `1` | `0.0779` | `23` components, largest `99.28%`, `11` small comps | Failed. Continued to lose lattice members. |
| 10 | Background-corrected threshold `900`, `sigma 0.8`, background `12`, min intensity `32000`, close `1` | `0.1082` | `14` components, largest `99.72%`, `4` small comps | Improved and selected. Best balance of preserved lattice connectivity and limited isolated noise; recovered more dim right-side struts than any global threshold. |

## Selection Evidence

The final selection used proxy measurements and slice `380` visual inspection rather than ground truth.

- Iteration `10` had the lowest small-component count in the metric slab: `4`
- Iteration `10` had the lowest 3D component count among viable candidates: `14`
- Iteration `10` retained a dominant connected structure in the metric slab: largest component `99.7223%` of foreground voxels
- Iteration `10` produced the largest slice-380 connected foreground share among all attempts: `56.6558%`
- Visual inspection showed that iteration `10` recovered more of the attenuated right-hand lattice struts without flooding the dark background

## Final Volume Statistics

- Total voxels: `519119955`
- Foreground voxels: `52879955` (`10.1865%`)
- Background voxels: `466240000` (`89.8135%`)
- Final mask shape: `(761, 815, 837)`
- Final mask dtype: `uint8`

## Termination

- Total iterations attempted: `10`
- Failed attempts without improvement: `6`
- Termination reason: reached the hard cap of `10` total iterations. The early-stop rule for `3` consecutive failed attempts was not triggered because improvements occurred before any three-failure streak formed.

## Limitations

- These proxy metrics are not a substitute for ground-truth evaluation.
- The chosen method is only the best among the `10` attempted candidates, not a claim of global optimality.
- The final mask still shows residual attenuation sensitivity on the far right side of slice `380`, so some dim struts may remain under-segmented.
