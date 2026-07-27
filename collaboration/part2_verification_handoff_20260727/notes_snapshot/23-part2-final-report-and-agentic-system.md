---
title: Part 2 Final Report And Agentic System
created: 2026-07-27
updated: 2026-07-27
tags:
  - part2
  - final-report
  - agentic-system
  - ct
  - defect-analysis
---

# Part 2 Final Report And Agentic System

## Short Answer

The project now has a final report package and a reusable agentic workflow.

Latest final package:

```text
outputs/part2/final_report/20260727_123413/
```

Newest automation layer after this package:

```text
outputs/part2/phase2c/20260727_132248/
```

Newest local all-strut viewer:

```text
outputs/part2/visualization/20260727_132343/index.html
```

See the newer Phase 2C note:

```text
notes/sections/24-part2-phase2c-automatic-triage-and-viewer.md
```

Most important files:

```text
outputs/part2/final_report/20260727_123413/final_ct_defect_report.md
outputs/part2/final_report/20260727_123413/final_ct_defect_summary.json
outputs/part2/final_report/20260727_123413/agentic_workflow.md
outputs/part2/final_report/20260727_123413/tables/headline_numbers.csv
outputs/part2/final_report/20260727_123413/figures/automated_review_label_counts.png
```

## Main Result

```text
total expected struts = 18,468
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
auto-supported possible unintended combined = 214
draft possible-unintended fraction = 214 / 18,468 = 1.16%
```

Human spot-check:

```text
reviewed panels = 40
defect-like = 36
ambiguous = 4
present-like contradictions = 0
```

Important wording:

```text
This is a spot-check-supported automated estimate, not a fully human-labeled ground truth.
```

## Simple Physical Meaning

Think of the lattice like a tiny bridge network.

- The STL tells what the design intentionally removed.
- The registered JSON tells where every strut should be in the CT scan.
- The TIFF tells what material actually appears in X-ray CT.
- Bright CT voxels usually mean titanium alloy material.
- Dark CT voxels usually mean air, empty space, or missing material.

The system checks each expected strut path. If the design says the strut should
exist, but CT evidence along that strut is mostly dark, broken, or has a long
gap, then it becomes a possible unintended missing or disconnected strut.

## What The Automatic System Is

The automatic system is not one magic AI call. It is a staged workflow:

1. Build a clean canonical graph from the raw JSON.
2. Recover design intent from STL files.
3. Use human anchors to fix the graph/STL/CT orientation.
4. Sample CT evidence around all `18,468` registered struts.
5. Assign guarded labels.
6. Apply strict automated-review rules.
7. Package the result into a report with caveats.

Python scripts do the numerical work. Codex agents check gates, run the scripts,
inspect outputs, explain results, and update notes.

## New Tools Created

Final report script:

```text
src/part2/final_report.py
```

Tests:

```text
tests/part2/test_final_report.py
```

Project skill:

```text
.agents/skills/part2-defect-analysis/SKILL.md
```

Main agent config:

```text
.codex/agents/part2_defect_analysis_agent.toml
```

## How To Rerun

Generate a new final report package from the current Phase 2B.4 result:

```bash
python3 -m src.part2.final_report --phase2b4-dir outputs/part2/phase2b4/20260727_092219
```

Run the final-report tests:

```bash
python3 -m unittest tests.part2.test_final_report -v
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

Validate the project skill:

```bash
python3 /Users/haseebahmad/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/part2-defect-analysis
```

## What Worked

- The final package was generated quickly without rereading the large TIFF/STL files.
- The package copied the key tables and QC figure into one folder.
- The report language keeps designed removals, possible unintended defects, and unresolved rows separate.
- The new test verifies the `214 / 18,468 = 1.16%` calculation and caveat wording.
- The project skill validates successfully.

## What Still Needs Care

- The `920` blocked manual-review rows remain unresolved.
- The top `40` spot-check panels support the automated estimate, but all `214` auto-supported candidates were not manually labeled.
- Boundary and skin-adjacent regions can be harder to judge.
- This should be described as a spot-check-supported automated estimate, not final exhaustive ground truth.
- Phase 2C later reduced the unresolved queue to `677` and raised the automatic triage count to `228`, but that newer count has not yet received the same human spot-check as the `214` final-package baseline.

## Recommended Next Action

Use the final package for a draft report/poster section. If the claim needs to
be stronger, review more of the Phase 2B.4 panels, especially ranks `041-080`
and selected rows from:

```text
outputs/part2/phase2b4/20260727_092219/manual_review_queue.csv
```

For continued automation and visualization, use the Phase 2C note and viewer:

```text
notes/sections/24-part2-phase2c-automatic-triage-and-viewer.md
outputs/part2/visualization/20260727_132343/index.html
```
