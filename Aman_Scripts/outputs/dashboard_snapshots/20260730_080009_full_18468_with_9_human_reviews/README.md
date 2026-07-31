# Full-lattice CT defect classification — snapshot

LLNL Data Science Challenge 2026, additively-manufactured strut lattice CT scan.
Generated (source artifacts written): 2026-07-30 00:08 local. Snapshot packaged:
2026-07-30 08:00 UTC.

All **18,468** registered expected struts, deterministic automated classification
plus **9** human-reviewed overrides applied on top (see `human_review_labels`
list below). This is not validated manufacturing ground truth — see
`full_defect_report.md` in this bundle for methodology and limitations.

## Breakdown (prediction_counts, from full_pipeline_metrics.json)

| label | count |
| --- | --- |
| healthy | 3,160 |
| missing | 118 |
| broken | 256 |
| thin | 1 |
| thick | 0 |
| bent_or_misaligned | 12,722 |
| uncertain | 1,472 |
| not_applicable | 739 |

## Human-reviewed strut IDs (9)

| strut_id | label |
| --- | --- |
| 6754 | healthy |
| 14755 | healthy |
| 1523 | uncertain |
| 1775 | healthy |
| 1870 | bent_or_misaligned |
| 10005 | missing |
| 10536 | healthy |
| 14098 | missing |
| 17654 | healthy |

## Files in this bundle

- `full_strut_classification.csv` — main table, 18,468 rows x 53 columns
- `full_lattice_scene.npz` — compact 3D scene for the Three.js viewer
- `full_pipeline_metrics.json` — summary metrics, incl. prediction_counts
- `full_alignment.json` — CT-to-registered-geometry alignment transform
- `full_thickness_reference.json` — thickness reference stats
- `full_defect_report.md` — methodology and limitations writeup

## How to view this in the dashboard

You need a clone of the same repository (the frontend also needs `data/`
git-LFS CT volumes/JSON and the rest of the pipeline code, not just these
artifacts). Steps:

1. Back up your own `part2/artifacts/sample/` directory.
2. Copy the 6 files above into `part2/artifacts/sample/`, overwriting the
   existing ones.
3. From the repo root: `PYTHONPATH=part2 conda run -n DSC streamlit run
   part2/app.py` (or `conda activate defect-cartographer` first if not using
   `conda run`).
4. Open the Overview or Visual Analysis page.
