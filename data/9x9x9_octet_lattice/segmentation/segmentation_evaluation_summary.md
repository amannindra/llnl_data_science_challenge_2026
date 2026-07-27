# Segmentation and Evaluation Summary

## Dataset

- Raw CT volume: `data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`
- Shape: `761 × 815 × 837` voxels
- Input dtype: `uint16`
- Intensity range: `0–65,535`
- Evaluation slice: index `380` along axis `0`
- Ground-truth image: `data/9x9x9_octet_lattice/ground_truth_segmentation_slice_380.png`

## Final Segmentation

- Method: global intensity thresholding
- Threshold: `39,000`
- Gaussian sigma: `0.5`
- Minimum component size: `8` pixels
- Final mask: `data/9x9x9_octet_lattice/segmentation/segmented_mask.tif`
- Final slice: `data/9x9x9_octet_lattice/segmentation/slice_380.png`
- Reproducible script: `data/9x9x9_octet_lattice/segmentation/segment_lattice.py`
- Detailed report: `data/9x9x9_octet_lattice/segmentation/REPORT.md`

### Full-volume statistics

| Metric | Result |
|---|---:|
| Total voxels | 519,119,955 |
| Foreground voxels | 63,783,110 |
| Foreground fraction | 12.286777% |
| Background voxels | 455,336,845 |
| Background fraction | 87.713223% |
| Output shape | 761 × 815 × 837 |
| Output dtype | uint8 |

### Slice-380 preview statistics

| Metric | Result |
|---|---:|
| Foreground pixels | 38,442 |
| Foreground fraction | 5.635376% |
| Background pixels | 643,713 |
| Connected components | 192 |

## Optimization Summary

Early locally adaptive and hysteresis-based methods recovered dim intensity paths but substantially over-segmented the slice, joining isolated nodes with false diagonal struts. The evaluation score for those results fell as low as `1/5`.

A conservative global-threshold baseline using threshold `39,000` and sigma `1.0` reduced false connections and scored `3/5`. A focused sweep then compared thresholds `39,000–41,000` with sigma values `0.0–0.5`. Keeping the threshold at `39,000` while reducing sigma to `0.5` produced thinner, sharper structures without the severe connection loss of higher thresholds.

## Final LLM Evaluation

- Rubric: `evals/rubric_segmentation_1.md`
- Final score: **4 / 5**
- Interpretation: excellent segmentation with minor differences.

```json
{
  "reasoning": "The result closely preserves the ground-truth lattice geometry, nodes, and overall connectivity. Foreground regions are consistently thicker and slightly enlarged, producing modest over-segmentation, while a few thin diagonal sections are fragmented or missing. Boundaries are somewhat rough, with minor speckle-like fragments, but no major false structures or topology-changing errors are evident.",
  "score": 4
}
```

## Conclusion

The final result preserves the primary lattice geometry and topology and avoids the major false connections produced by adaptive methods. Remaining errors are limited to modest foreground thickening, several fragmented thin diagonals, and minor boundary roughness. The score-4 result is the selected final deliverable.
