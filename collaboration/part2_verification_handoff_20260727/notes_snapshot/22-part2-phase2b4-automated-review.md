---
title: Part 2 Phase 2B.4 - Automated Evidence Review
created: 2026-07-27
updated: 2026-07-27
tags:
  - part2
  - phase2b4
  - ct
  - automated-review
  - defect-analysis
---

# Part 2 Phase 2B.4 - Automated Evidence Review

## Short Answer

Phase 2B.4 did the next automated review step after Phase 2B.3.

Latest valid run:

```text
outputs/part2/phase2b4/20260727_092219/
```

Input:

```text
outputs/part2/phase2b3/20260727_090709/guarded_edge_labels.csv
```

Main result:

```text
total registered edges = 18,468
auto-supported present-like = 14,820
auto-supported designed-removed absent/disconnected = 89
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
auto-supported possible unintended combined = 214
blocked manual-review rows = 920
low-priority uncertain, not defect-like = 2,425
spot-check panels generated = 80
```

Important:

```text
This is an automated review result, not human-validated final publication.
```

## Why This Phase Was Needed

Phase 2B.3 was deliberately sensitive. It marked anything suspicious as
review-required.

That created:

```text
3,573 review-required rows
```

Phase 2B.4 asks a stricter question:

```text
Which of those suspicious rows are clean enough for the automated system to support?
```

This reduced the blocked manual-review load to:

```text
920 rows
```

## Simple Picture

Imagine looking for broken bridges in a city map.

Phase 2B.3 says:

```text
These bridges look suspicious.
```

Phase 2B.4 says:

```text
These suspicious bridges have clean, strong evidence.
These others are still too messy and need review.
```

## Strict Auto-Support Rules

A possible unintended defect is auto-supported only when:

- the anomaly score is clearly above the Phase 2B.3 threshold;
- the row is not near the threshold;
- the row is not threshold-sensitive;
- local registration is not unstable;
- many independent missing-material signals agree.

Latest settings:

```text
minimum score for auto support = 3.3135416666666666
possible missing requires evidence flags >= 7
possible disconnected requires evidence flags >= 5
threshold stability must be <= 0.25
local registration stability must be < 2.5 voxels
```

## What The Numbers Mean

`202` auto-supported possible unintended missing:

- Design did not mark these struts intentionally removed.
- CT evidence looks strongly empty.
- The evidence is clean enough for automated support.
- Many are boundary/skin-adjacent, so spot-check approval is still recommended.

`12` auto-supported possible unintended disconnected:

- Design did not mark these struts intentionally removed.
- CT evidence suggests material is broken or not continuous.
- Evidence is clean enough for automated support.

`920` blocked manual-review rows:

- These are still too uncertain or unstable for automated support.
- They are not ignored.
- They stay in `manual_review_queue.csv`.

`2,425` low-priority uncertain rows:

- These were uncertain in Phase 2B.3, but they have low missing evidence.
- They are not reported as defects by the automated review.

## Draft Fractions

The automated-review draft possible unintended combined fraction is:

```text
214 / 18,468 = 0.0115876
```

That is about:

```text
1.16%
```

Important:

```text
This is a draft automated-review fraction, not a final published defect percentage.
```

## Output Files

Main folder:

```text
outputs/part2/phase2b4/20260727_092219/
```

Important files:

```text
automated_review_labels.csv
phase2b4_summary.json
draft_defect_summary_not_for_publication.md
auto_supported_unintended_candidates.csv
manual_review_queue.csv
spotcheck_panel_index.csv
spotcheck_panels/
qc/automated_review_label_counts.png
run_manifest.json
```

What each file means:

- `automated_review_labels.csv`: one row per expected strut with Phase 2B.4 automated-review outcome.
- `phase2b4_summary.json`: machine-readable summary and strict review settings.
- `draft_defect_summary_not_for_publication.md`: beginner-readable report.
- `auto_supported_unintended_candidates.csv`: the `214` strongest automated possible unintended defect candidates.
- `manual_review_queue.csv`: the `920` rows still blocked by uncertainty.
- `spotcheck_panels/`: 80 panels split between supported and blocked high-value examples.
- `qc/automated_review_label_counts.png`: label-count plot.
- `run_manifest.json`: provenance, hashes, git state, runtime, and memory.

## How To Read This Result

This phase does not mean:

```text
The final paper result is exactly 1.16%.
```

It means:

```text
The automated system strongly supports 214 possible unintended missing/disconnected candidates under strict rules.
```

The remaining review question is much smaller now:

```text
Do the spot-check panels support using these draft automated counts in a report?
```

## Commands

Rerun Phase 2B.4:

```bash
python3 -m src.part2.phase2b4_automated_review --max-spotcheck-panels 80
```

Rerun without rendering panels:

```bash
python3 -m src.part2.phase2b4_automated_review --skip-panels
```

Run targeted tests:

```bash
python3 -m unittest tests.part2.test_phase2b4_automated_review -v
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Latest result:

```text
Ran 82 tests
OK
skipped 1 optional VTK test
```

## Next Gate

The next step is small, not giant:

```text
Review the 80 spot-check panels from Phase 2B.4.
```

Focus on:

```text
outputs/part2/phase2b4/20260727_092219/spotcheck_panels/
outputs/part2/phase2b4/20260727_092219/auto_supported_unintended_candidates.csv
outputs/part2/phase2b4/20260727_092219/manual_review_queue.csv
```

After that, the project can create a final report section that clearly separates:

- intentionally designed removals;
- auto-supported possible unintended missing struts;
- auto-supported possible unintended disconnected struts;
- unresolved/manual-review cases;
- limitations.

## Human Spot-Check Update - Ranks 001 To 040

The user reviewed the first 40 Phase 2B.4 spot-check panels in chat.

Saved review labels:

```text
outputs/part2/phase2b4/20260727_092219/human_spotcheck_labels_rank001_040.csv
```

Saved review summary:

```text
outputs/part2/phase2b4/20260727_092219/human_spotcheck_summary_rank001_040.md
```

Draft report section:

```text
outputs/part2/phase2b4/20260727_092219/spotcheck_supported_report_section_draft.md
```

Result:

```text
reviewed panels = 40
human material_absent = 29
human material_disconnected = 7
human ambiguous = 4
human present-like = 0
defect-like support = 36 / 40
defect-like support fraction = 0.900
```

Simple meaning:

The first 40 reviewed panels strongly support the automated Phase 2B.4
direction. None were marked present-like. This supports using the strict
automated counts as a draft final-report estimate with clear caveats:

```text
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
auto-supported possible unintended combined = 214
214 / 18,468 = about 1.16%
```

The remaining caveat is that this is spot-check-supported, not exhaustive
human labeling of all `214` auto-supported candidates.
