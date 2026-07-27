# Agentic Part 2 CT Defect-Analysis Workflow

## Purpose

This is the practical automatic system for this project. Deterministic Python
scripts do the numerical work. Codex agents orchestrate the steps, check stop
gates, inspect outputs, and write notes.

## Current Final Package

```text
outputs/part2/final_report/20260727_123413
```

Source Phase 2B.4 run:

```text
outputs/part2/phase2b4/20260727_092219
```

## Tools To Use

Project skill:

```text
.agents/skills/part2-defect-analysis/SKILL.md
```

Main orchestration agent:

```text
.codex/agents/part2_defect_analysis_agent.toml
```

Helpful specialized agents:

```text
.codex/agents/ct_visual_review_agent.toml
.codex/agents/phase2b_ct_calibration_agent.toml
.codex/agents/segmentation_agent.toml
```

Main deterministic scripts:

```text
python3 -m src.part2.phase0
python3 -m src.part2.phase2r1_anchor_gate
python3 -m src.part2.phase2b2_all_edge_prep
python3 -m src.part2.phase2b3_guarded_labels
python3 -m src.part2.phase2b4_automated_review
python3 -m src.part2.final_report
```

## Automatic Workflow

1. Preflight the repository and data.
   - Confirm the current folder is the repo root.
   - Record Git status with LFS filters disabled.
   - Stop if required TIFF/STL/JSON data are Git LFS pointer files.

2. Build or verify the canonical graph.
   - Raw JSON has repeated junction aliases.
   - Phase 0 merges aliases into real physical nodes and creates stable edge IDs.

3. Recover design intent.
   - STL comparison tells which struts were intentionally removed by design.
   - Human anchors resolved the cube orientation enough for Phase 2B.

4. Sample CT around every registered strut.
   - Use the registered JSON as the expected path in the TIFF.
   - Remember JSON coordinates are `[x,y,z]`; TIFF arrays are `[z,y,x]`.
   - Exclude node zones so a bright joint does not fake a present strut body.

5. Create guarded CT labels.
   - Keep present-like, designed-removed, possible unintended, and uncertain rows separate.
   - Do not publish final percentages from Phase 2B.3 alone.

6. Apply strict automated evidence review.
   - Phase 2B.4 only auto-supports clean, stable candidates.
   - Unstable or ambiguous rows stay in `manual_review_queue.csv`.

7. Package the final spot-check-supported estimate.
   - Use this script to write `final_ct_defect_report.md`.
   - Keep caveats in the report.

## Most Important Stop Gates

- Stop if raw data are missing or only LFS pointers.
- Stop if the graph/STL/CT transform is not human-anchored or otherwise verified.
- Stop if CT sampling did not cover all `18,468` expected struts.
- Stop if manual-review rows are being silently counted as defects.
- Stop if a report calls the estimate fully final without human spot-check evidence.

## How To Rerun The Current Final Package

```bash
python3 -m src.part2.final_report --phase2b4-dir outputs/part2/phase2b4/20260727_092219
```

Run all Part 2 tests:

```bash
python3 -m unittest discover -s tests/part2 -v
```

## What Still Needs Human Judgment

The automatic system can reduce review work a lot, but it cannot remove all
judgment yet. The current report is supported by the top-40 spot-check. For a
stronger paper/poster claim, review more of:

```text
outputs/part2/phase2b4/20260727_092219/spotcheck_panels
outputs/part2/phase2b4/20260727_092219/manual_review_queue.csv
```
