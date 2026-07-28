# Segmentation report

## Baseline and tuning disclosure

- Baseline threshold: 34213.000; baseline evaluator score: 2/5.
- Baseline evaluator finding: nodes were often retained, but false-positive diagonals substantially changed connectivity/topology.
- Development data: input slice 380 only. The evaluator's textual diagnosis guided the false-positive target; no Task 7 ground-truth image, pixels, or measurements were used.
- Lightweight baseline evidence is preserved as `slice_380_baseline.png`, `iterations_baseline.csv`, and `segmentation_report_baseline.md`; the full baseline TIFF was not duplicated.

## Preflight and method

- Input metadata: shape (761, 815, 837), 761 pages, dtype uint16; slice index 380 exists.
- Free disk before processing: 26852519936 bytes (25.01 GiB); input size 1038433319 bytes.
- Estimated peak page memory: 2046465 bytes; estimated uncompressed mask size: 519119955 bytes.
- Threshold method: global fixed threshold selected by a slice-380 candidate sweep around Li, Otsu, and 35,000-40,000.
- Selected threshold: 40000.000; foreground is input intensity > threshold.
- Decision rule: choose the lowest candidate with slice foreground <=5%, largest 4-connected component <=6% of foreground, and 100% retention of high-confidence node pixels (>45,000 regions of at least 100 pixels).
- Synthetic complete-path TIFF test passed before full processing.
- Full processing was page-by-page and the input was opened read-only.

## Complete iteration history

| Iteration | Method | Threshold | Foreground fraction | Largest-component fraction | 4-connected components | Small-component pixel fraction | Node retention | Visual assessment | Selected |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | fixed_35000 | 35000.000 | 0.110314 | 0.599248 | 241 | 0.008943 | 1.000 | Rejected: extensive diagonal lattice; 59.9% of foreground is one 4-connected component. | False |
| 2 | slice_li | 36632.933 | 0.081083 | 0.435248 | 304 | 0.012583 | 1.000 | Rejected: many false-positive diagonals remain and largest component is 43.5%. | False |
| 3 | fixed_37500 | 37500.000 | 0.070513 | 0.328372 | 292 | 0.013846 | 1.000 | Rejected: fewer diagonals, but central diagonal connectivity remains (largest component 32.8%). | False |
| 4 | fixed_40000 | 40000.000 | 0.049756 | 0.058484 | 283 | 0.015026 | 1.000 | Selected: isolated nodes preserved; central false diagonals largely removed; supported left struts retained. | True |
| 5 | slice_otsu | 40499.000 | 0.046853 | 0.046338 | 275 | 0.015175 | 1.000 | Rejected: marginal topology gain versus 40000 but visibly removes additional supported left-edge struts. | False |

Candidate masks, montage, and quantitative metrics are under `diagnostics/`. Connectivity is measured in 2-D with 4-connectivity. Small components contain fewer than 16 pixels. The node proxy is defined above.

## Termination

- Termination reason: threshold 40,000 met every decision criterion at iteration 4. Otsu (40,499) was also evaluated at iteration 5 but rejected because its small connectivity reduction came with visible loss of supported left-edge struts. The loop stopped after five candidates, below the 10-iteration limit and without three consecutive failed attempts.
- Only slice masks were generated during tuning. Exactly one full 3-D candidate mask was written, after selection.

## Final validation and counts

- Input: `/Users/ulicesramirez/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`
- Output shape: (761, 815, 837)
- Output TIFF page count: 761
- Output dtype: uint8
- Unique values: [0, 1]
- Foreground voxel count: 58888345
- Background voxel count: 460231610
- Foreground percentage: 11.34388005%
- Count check: 58888345 + 460231610 = 519119955
- `slice_380.png`: exact 800x800 Matplotlib viridis rendering, title `Slice 380 along axis 0`, axis-0 index 380, `vmin=0`, `vmax=1`, with colorbar.

## Assumptions and limitations

- Bright voxels represent lattice material and darker voxels background; one global threshold is assumed adequate.
- Slice 380 was used both to tune and diagnose the decision, so its metrics are not an independent accuracy estimate.
- The visual distinction between faint true struts and reconstruction haze is uncertain without ground truth.
- No morphology was applied; bright speckle may remain, while genuine low-intensity or partial-volume struts can be missed.
- The connectivity and node metrics are 2-D proxies and do not guarantee correct 3-D topology.

## Reproduction command

```bash
/opt/miniconda3/envs/dssi_env/bin/python data/9x9x9_octet_lattice/segmentation/segment_volume.py data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif
```
