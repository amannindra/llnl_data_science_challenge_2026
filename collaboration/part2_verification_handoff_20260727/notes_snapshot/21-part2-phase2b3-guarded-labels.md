---
title: Part 2 Phase 2B.3 - Guarded CT Labels
created: 2026-07-27
updated: 2026-07-27
tags:
  - part2
  - phase2b3
  - ct
  - defect-analysis
  - review
---

# Part 2 Phase 2B.3 - Guarded CT Labels

## Short Answer

Phase 2B.3 converted the all-edge Phase 2B.2 CT feature table into guarded,
review-aware labels.

Latest valid run:

```text
outputs/part2/phase2b3/20260727_090709/
```

Input table:

```text
outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv
```

Main result:

```text
total registered edges = 18,468
present_like = 14,820
designed_removed_ct_absent = 88
designed_removed_ct_disconnected_or_residual_material = 1
designed_removed_ct_uncertain = 1
designed_removed_ct_present_like_conflict = 4
possible_unintended_missing = 420
possible_unintended_disconnected = 58
uncertain_review_required = 3,076
review_required_count = 3,573
```

Important:

```text
These are guarded screening labels, not final published defect percentages.
```

## Simple Picture

Think of the lattice as many tiny bridges.

Phase 2B.2 already measured every bridge in the CT scan.

Phase 2B.3 asks:

```text
Do several measurements agree that this bridge is present, absent, broken, or unclear?
```

If the measurements do not agree, the label stays `review_required`.

## Files Used

All-edge CT measurements:

```text
outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv
```

Phase 2B.2 threshold summary:

```text
outputs/part2/phase2b2/20260727_013304/phase2b2_summary.json
```

Registered expected strut graph:

```text
outputs/part2/phase0/canonical_graphs/registered_9x9.canonical_graph.json
```

Raw TIFF was used only to render review panels:

```text
data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif
```

## What The New Code Does

New script:

```text
src/part2/phase2b3_guarded_labels.py
```

New tests:

```text
tests/part2/test_phase2b3_guarded_labels.py
```

The script does these jobs:

1. Loads the full `18,468`-edge CT feature table.
2. Loads calibrated thresholds from Phase 2B.2.
3. Checks several CT evidence signals for every edge.
4. Separates design intent from CT observation.
5. Writes one guarded label per edge.
6. Writes review-priority tables.
7. Creates 60 CT review panels for the highest-priority review cases.
8. Stops before final published percentages.

## The CT Evidence Signals

The main CT signals are:

- `ct_missing_material_anomaly_score`: overall missing-material score. Higher means more missing-like.
- `longest_low_area_gap_fraction`: how much of the strut has a long low-material gap.
- `occupied_axial_fraction`: fraction of the strut length that looks occupied by material.
- `area_mean_voxels2`: average detected material cross-section area.
- `core_minus_background_contrast`: whether the expected strut core is brighter than nearby background.
- `negative_template_residual`: how much material is missing compared with similar struts.
- `bridge_connected_26`: whether material appears connected through the strut using 26-neighbor voxel connectivity.

Simple meaning:

```text
A missing strut should be dark, low-area, low-occupancy, gapped, and not connected.
```

One signal alone is not enough for a guarded label.

## Thresholds Used

These came from the Phase 2B.2 all-edge calibration summary:

```text
ct_missing_material_anomaly_score high >= 2.8135416666666666
older warning threshold >= 2.020833333333333
longest_low_area_gap_fraction high >= 0.5208333333333333
negative_template_residual high >= 1.123397435897436
occupied_axial_fraction low <= 0.10416666666666666
area_mean_voxels2 low <= 0.3125
core_minus_background_contrast low <= 0.028496128080248578
near-threshold margin = 0.5
threshold stability warning > 0.25
local registration stability warning >= 2.5 voxels
```

These are dataset-calibrated decision aids. They are not universal physics
laws.

## Label Meanings

`designed_removed_ct_absent`:

- The STL/design map says this strut was intentionally removed.
- CT also looks almost empty along that expected strut.

`designed_removed_ct_disconnected_or_residual_material`:

- Design says removed.
- CT still shows some broken or residual material.

`designed_removed_ct_present_like_conflict`:

- Design says removed.
- CT looks present-like.
- This is a conflict and must be reviewed.

`possible_unintended_missing`:

- Design did not mark this strut removed.
- CT looks almost empty.
- This could be an unintended missing strut, but it must be reviewed.

`possible_unintended_disconnected`:

- Design did not mark this strut removed.
- CT has material but the material looks broken or not connected.
- This could be an unintended disconnected strut, but it must be reviewed.

`present_like`:

- CT looks connected and far from the missing threshold.

`uncertain_review_required`:

- The evidence is mixed, near a threshold, threshold-sensitive, or registration-sensitive.

## Why Final Percentages Are Still Blocked

Phase 2B.3 is much closer to final classification, but it still blocks final
publication because:

- `possible_unintended_missing` and `possible_unintended_disconnected` can include false positives.
- Local CT registration and threshold choices can create confusing edge cases.
- Boundary or skin-adjacent regions can look different from interior struts.
- The user has not approved a final review rule for publishing percentages.

So the correct current language is:

```text
guarded screening labels
```

not:

```text
final defect percentages
```

## Output Files

Main folder:

```text
outputs/part2/phase2b3/20260727_090709/
```

Important files:

```text
guarded_edge_labels.csv
guarded_label_summary.json
label_summary_report.md
review_required_edges.csv
top_possible_unintended_edges.csv
design_removed_disagreements.csv
review_panel_index.csv
review_panels/
qc/guarded_label_counts.png
qc/anomaly_score_by_guarded_label.png
run_manifest.json
```

What each file means:

- `guarded_edge_labels.csv`: one row for every expected strut with CT features, evidence flags, and guarded labels.
- `guarded_label_summary.json`: machine-readable counts and thresholds.
- `label_summary_report.md`: beginner-readable summary report.
- `review_required_edges.csv`: all rows that need review before final publication.
- `top_possible_unintended_edges.csv`: highest-priority possible unintended missing/disconnected candidates.
- `design_removed_disagreements.csv`: design-removed candidates where CT does not clearly agree.
- `review_panels/`: 60 focused CT panels for top review cases.
- `qc/`: summary plots.
- `run_manifest.json`: provenance, input hashes, git state, outputs, runtime, and memory.

## How To Read The Review Panels

The review panels are aids, not final labels.

Important visual rules:

- The cyan line is the expected registered strut path.
- The cyan line is not material. It is just the map line drawn over the CT data.
- Bright CT near the line usually means metal is present near the expected strut.
- Dark CT along the line suggests missing or weak material.
- The yellow contour/line is a visual threshold reference.
- Maximum projections can include neighboring struts, so use the straightened slab and the numeric label table together.

## What Worked

- All `18,468` CT feature rows were classified by one deterministic script.
- The method now separates design intent from CT observation.
- The method does not automatically accept possible unintended defects as final truth.
- Review panels and review CSVs were generated.
- Full Part 2 tests pass.

## What Remains

The next gate is not more automatic classification. The next gate is review and
calibration of the highest-value cases.

Recommended next task:

```text
Phase 2B.4: review a small prioritized subset from top_possible_unintended_edges.csv and review_panels/, then decide final publication rules.
```

The review should focus first on:

```text
outputs/part2/phase2b3/20260727_090709/top_possible_unintended_edges.csv
outputs/part2/phase2b3/20260727_090709/review_panels/
```

## Commands

Rerun Phase 2B.3:

```bash
python3 -m src.part2.phase2b3_guarded_labels --max-review-panels 60
```

Rerun Phase 2B.3 without making panels:

```bash
python3 -m src.part2.phase2b3_guarded_labels --skip-panels
```

Run the targeted tests:

```bash
python3 -m unittest tests.part2.test_phase2b3_guarded_labels -v
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```
