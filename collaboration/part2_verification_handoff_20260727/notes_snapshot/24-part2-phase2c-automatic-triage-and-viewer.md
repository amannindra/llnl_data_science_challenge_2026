---
title: Part 2 Phase 2C - Automatic Triage, Pipeline, And Viewer
created: 2026-07-27
updated: 2026-07-27
tags:
  - part2
  - phase2c
  - agentic-system
  - visualization
  - ct
  - defect-analysis
---

# Part 2 Phase 2C - Automatic Triage, Pipeline, And Viewer

## Short Answer

Phase 2C is the next automatic improvement after the Phase 2B.4 report.

Latest dedicated Phase 2C run:

```text
outputs/part2/phase2c/20260727_132248/
```

Latest all-strut local viewer:

```text
outputs/part2/visualization/20260727_132343/index.html
```

Latest config-driven pipeline test run:

```text
outputs/part2/pipeline_runs/20260727_132552/
```

Main Phase 2C result:

```text
total registered struts checked = 18,468
auto-supported possible unintended missing = 215
auto-supported possible unintended disconnected = 13
auto-supported possible unintended combined = 228
still review-required = 677
low-priority uncertain, not counted as defects = 2,654
newly promoted from Phase 2B.4 blocked rows = 14
```

Important:

```text
Phase 2C is still automated triage. It is not full human-labeled ground truth.
```

## What Problem Phase 2C Solves

Phase 2B.4 left this situation:

```text
214 auto-supported possible unintended defects
920 blocked manual-review rows
2,425 low-priority uncertain rows
```

The user asked why those unresolved rows were still there and whether we had
really checked the full TIFF.

The answer is:

```text
Yes, all 18,468 registered struts had CT features from the full TIFF.
No, the software should not automatically call every unclear row a defect.
```

Phase 2C uses the existing all-edge CT feature table and asks a safer second
question:

```text
Among the blocked rows, are any cases so empty or so clearly broken that they
can be promoted even though Phase 2B.4 was cautious?
```

Only `14` rows passed that second-pass rule. Everything else stayed review
required or was demoted to low-priority uncertain.

## Simple Example

Imagine checking 18,468 tiny bridge beams.

Phase 2B.4 said:

```text
214 beams look clearly missing or broken.
920 beams are suspicious but messy.
2,425 beams are uncertain but weak evidence.
```

Phase 2C looked again at the messy rows and said:

```text
14 of the messy rows are actually very clear.
677 are still too messy.
2,654 are weak enough that we should not count them as defects.
```

That does not mean the `677` were ignored. It means they were checked but the
automatic evidence was not clean enough.

## What Data Was Used

Phase 2C does not reread the whole TIFF from scratch.

Input:

```text
outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv
outputs/part2/phase2b4/20260727_092219/phase2b4_summary.json
```

Those files already contain all-edge CT evidence that ultimately came from:

```text
data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif
data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json
outputs/part2/phase0/canonical_graphs/registered_9x9.canonical_graph.json
```

Meaning:

- The TIFF is the real CT scan, or what was physically printed and scanned.
- The registered JSON tells the expected path of each strut inside that TIFF.
- The Phase 2B.4 CSV stores the measured CT evidence for each expected strut.

## What The Rules Mean

Phase 2C promotes a blocked possible-missing row only when all of these are true:

```text
CT anomaly score is very high
missing-evidence flags are high enough
occupied axial fraction is almost zero
mean material area is almost zero
longest low-area gap covers almost the whole strut body
26-neighbor bridge connectivity is broken
threshold and registration instability are present only within bounded limits
```

In plain words:

```text
The expected strut path is mostly dark, mostly empty, and not continuously
connected, even when we allow small threshold or registration wiggle room.
```

Phase 2C promotes a blocked possible-disconnected row only when:

```text
there is a long low-material gap,
the bridge is broken,
the score is high,
and the instability is bounded.
```

If evidence is mixed, near-threshold, strongly registration-unstable, or a
design-intent conflict, the row stays review-required.

## Why The Count Changed From 214 To 228

Phase 2B.4 was stricter. It said:

```text
I will only support the cleanest cases.
```

Phase 2C added a second-pass rule for rows that Phase 2B.4 had blocked because
they had mild boundary or stability cautions. If the CT body was essentially
empty anyway, Phase 2C allowed promotion.

That promoted:

```text
14 rows
```

So:

```text
214 + 14 = 228
```

The new fraction is:

```text
228 / 18,468 = 1.23%
```

But the existing final report still uses `214 / 18,468 = 1.16%` because that
was the set supported by the user's top-40 spot-check. The new `228` result is
the latest automatic triage result and should get its own spot-check before a
stronger publication claim.

## Output Files

Dedicated Phase 2C output:

```text
outputs/part2/phase2c/20260727_132248/manual_queue_triage_report.md
outputs/part2/phase2c/20260727_132248/phase2c_summary.json
outputs/part2/phase2c/20260727_132248/phase2c_labels.csv
outputs/part2/phase2c/20260727_132248/phase2c_auto_supported_unintended_candidates.csv
outputs/part2/phase2c/20260727_132248/phase2c_remaining_review_queue.csv
outputs/part2/phase2c/20260727_132248/review_packet/
outputs/part2/phase2c/20260727_132248/run_manifest.json
```

Viewer output:

```text
outputs/part2/visualization/20260727_132343/index.html
outputs/part2/visualization/20260727_132343/viewer_data.json
outputs/part2/visualization/20260727_132343/legend.json
outputs/part2/visualization/20260727_132343/run_manifest.json
```

Pipeline output:

```text
outputs/part2/pipeline_runs/20260727_132552/pipeline_run_manifest.json
outputs/part2/pipeline_runs/20260727_132552/phase2c/
outputs/part2/pipeline_runs/20260727_132552/visualizer/
outputs/part2/pipeline_runs/20260727_132552/final_report/
```

## How To Read The Viewer

Open:

```text
outputs/part2/visualization/20260727_132343/index.html
```

Color meaning:

```text
gray = present-like
red = possible unintended missing
orange = possible unintended disconnected
blue = intentionally designed removed
purple = still review-required
yellow = low-priority uncertain
```

Beginner interpretation:

- Gray struts look okay by the current evidence.
- Blue struts were intentionally removed by design, so do not count them as unintended defects.
- Red and orange are the main possible unintended defect candidates.
- Purple struts are not solved yet; they need review or better evidence.
- Yellow struts were uncertain but weak evidence, so the automated workflow does not count them as defects.

The viewer is not a final CT renderer. It is a fast map of expected graph struts
colored by their latest label. It helps us see where candidate defects cluster
in the 3D lattice.

## What The Agentic System Is Now

The current system has deterministic scripts plus Codex guidance.

Production scripts:

```text
src/part2/phase0.py
src/part2/phase2b2_all_edge_prep.py
src/part2/phase2b3_guarded_labels.py
src/part2/phase2b4_automated_review.py
src/part2/phase2c_manual_queue_triage.py
src/part2/final_report.py
src/part2/run_defect_pipeline.py
src/part2/visualization/export_defect_viewer.py
```

Agent and skill files:

```text
.agents/skills/part2-defect-analysis/SKILL.md
.codex/agents/part2_defect_analysis_agent.toml
```

The automatic workflow is:

1. Check raw files are real data, not Git LFS pointers.
2. Use the registered JSON to know where struts should be in the TIFF.
3. Reuse or build the canonical graph.
4. Reuse or build all-edge CT features.
5. Assign guarded labels.
6. Apply strict automated review.
7. Apply Phase 2C second-pass triage.
8. Export a local 3D graph viewer.
9. Package a conservative report.
10. Stop when review-required rows remain, instead of pretending they are solved.

## For A New TIFF In The Future

A new TIFF alone is not enough for this exact strut-level workflow.

Needed input package:

```text
new TIFF scan
registered JSON aligned to that TIFF
nominal JSON or canonical graph
design STL files if intentional removals must be separated from defects
config file listing those paths
```

If the new TIFF has no registered JSON, the system can still do rough image
segmentation, but it cannot confidently say which exact strut ID is missing.

## What Still Needs Care

- `677` rows still need review or a better future model.
- The `228` Phase 2C auto-supported count has not yet received the same human spot-check as the older `214` final-package count.
- The viewer shows graph struts, not a full segmented CT surface.
- Boundary/skin-adjacent struts are still harder because skin material and node blobs can confuse local evidence.
- Future presentation figures should use the viewer for global context and selected CT panels for local proof.

## Current Recommendation

Use Phase 2C as the newest internal automation state.

Use the Phase 2B.4 final report package when you need the current
spot-check-supported report wording.

Before claiming a stronger final number, spot-check the `14` newly promoted
Phase 2C rows and a sample of the highest-priority `677` remaining review rows.
