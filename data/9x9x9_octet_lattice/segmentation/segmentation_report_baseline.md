# Segmentation report

## Preflight and resource estimates

- Repository branch confirmed before processing: `ulices-test` (no branch switch performed).
- Input existence and readability: passed.
- Input metadata: shape (761, 815, 837), 761 pages, dtype uint16; slice index 380 exists.
- Required interpreter and imports (`numpy`, `tifffile`, `scipy`, `skimage`, `PIL`) passed.
- Free disk before processing: 27986010112 bytes (26.06 GiB), exceeding the 4 GiB requirement.
- Input file size: 1038433319 bytes.
- Estimated peak source-plus-mask page memory: 2046465 bytes (excluding library overhead).
- Estimated uncompressed uint8 output storage: 519119955 bytes; DEFLATE compression was used for the final TIFF.

## Method and termination

- Threshold method: global histogram triangle threshold plus a fixed 500-intensity-unit offset.
- Selected threshold: 34213.000 (foreground is input intensity > threshold).
- Optimization used representative input slices only; the Task 7 ground-truth image was not used.
- Termination reason: iteration 4 was selected after visual and metric review because it retained lattice struts while reducing low-intensity haze. This was within the 10-iteration safety limit and before three consecutive non-improving attempts.
- Synthetic complete-path TIFF test passed before the full run: True.
- Processing was page-by-page; the input TIFF was opened read-only and the full input/output were never simultaneously held in RAM.

## Iteration history

| Iteration | Method | Threshold | Mean foreground fraction | Mean largest-component fraction | Mean small-component pixel fraction | Mean component count | Assessment |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | global_otsu | 38341.000 | 0.052471 | 0.025645 | 0.001627 | 621.56 | Thin/disconnected struts in visual review |
| 2 | global_li | 36219.536 | 0.072734 | 0.055201 | 0.001379 | 605.67 | Improved retention but incomplete faint struts |
| 3 | global_triangle | 33713.000 | 0.157367 | 0.182962 | 0.003328 | 759.33 | Good strut retention; some low-intensity haze |
| 4 | global_triangle_plus_offset | 34213.000 | 0.125464 | 0.147175 | 0.003280 | 739.89 | Selected: retained struts with less haze |

Full parameters and per-iteration quality metrics are in `iterations.csv`. Connectivity metrics are 2-D, 4-connected measurements on slices; the small-component metric is the fraction of foreground pixels in components smaller than 16 pixels.

## Final validation and counts

- Input: `/Users/ulicesramirez/llnl_data_science_challenge_2026/data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`
- Input dtype: uint16
- Output shape: (761, 815, 837)
- Output TIFF page count: 761
- Output dtype: uint8
- Unique values: [0, 1]
- Foreground voxel count: 114798367
- Background voxel count: 404321588
- Foreground percentage: 22.11403470%
- Count check: 114798367 + 404321588 = 519119955
- Slice preview: final mask slice index 380, displayed as black=0 and white=1.

## Assumptions and limitations

- Bright voxels are assumed to represent lattice material and darker voxels background.
- A single global threshold is assumed adequate despite spatial intensity variation.
- No morphological cleanup was applied, avoiding deletion of real thin struts; isolated bright noise may remain.
- Partial-volume effects and weak material below the threshold can create locally thin or interrupted struts.
- Representative-slice metrics are diagnostic proxies, not ground-truth accuracy measurements.

## Reproduction command

```bash
/opt/miniconda3/envs/dssi_env/bin/python data/9x9x9_octet_lattice/segmentation/segment_volume.py data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif
```
