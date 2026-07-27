---
name: part2-defect-analysis
description: Run or audit the LLNL DSC Part 2 lattice CT defect-analysis workflow. Use when Codex needs to resume Part 2 from repo notes, verify canonical graph/design-intent/CT-sampling gates, run guarded labels or strict automated review, package the final spot-check-supported report, explain results to a beginner, or update Part 2 notes without modifying raw data or Git state.
---

# Part 2 Defect Analysis

## Core Rule

Use deterministic Python scripts for calculations. Use Codex reasoning for
planning, checking gates, reading artifacts, explaining results, and updating
notes.

Do not modify raw data under `data/`. Do not stage, commit, push, reset, clean,
delete, checkout, merge, or rebase. Do not overwrite old output folders.

## Read First

Read these files before making changes:

```text
AGENTS.md
notes/00-big-picture.md
notes/project-notebook.md
notes/sections/01-how-to-run-code.md
notes/sections/05-task-log-and-experiments.md
configs/scientific_assumptions.yaml
docs/part2/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md
```

For final reporting, also read:

```text
notes/sections/22-part2-phase2b4-automated-review.md
outputs/part2/phase2b4/20260727_092219/phase2b4_summary.json
outputs/part2/phase2b4/20260727_092219/human_spotcheck_summary_rank001_040.md
```

For the newest automatic triage and viewer layer, also read:

```text
notes/sections/24-part2-phase2c-automatic-triage-and-viewer.md
outputs/part2/phase2c/20260727_132248/phase2c_summary.json
outputs/part2/phase2c/20260727_132248/manual_queue_triage_report.md
```

## Current Valid Final-Report Source

Use this Phase 2B.4 run unless newer notes clearly supersede it:

```text
outputs/part2/phase2b4/20260727_092219/
```

Current interpretation:

```text
total expected struts = 18,468
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
auto-supported possible unintended combined = 214
auto-supported designed-removed absent/disconnected = 89
auto-supported present-like = 14,820
blocked manual-review rows = 920
low-priority uncertain not reported as defects = 2,425
human top-40 spot-check = 36 defect-like, 4 ambiguous, 0 present-like contradictions
```

Report `214 / 18,468 = 1.16%` only as a spot-check-supported automated
estimate, not as fully human-labeled ground truth.

## Current Newest Automatic Triage Source

Use this Phase 2C run for continued automation, viewer export, and unresolved
queue reduction unless newer notes clearly supersede it:

```text
outputs/part2/phase2c/20260727_132248/
```

Current interpretation:

```text
total expected struts = 18,468
auto-supported possible unintended missing = 215
auto-supported possible unintended disconnected = 13
auto-supported possible unintended combined = 228
auto-supported designed-removed absent/disconnected = 89
auto-supported present-like = 14,820
still review-required rows = 677
low-priority uncertain not reported as defects = 2,654
newly promoted from Phase 2B.4 blocked rows = 14
```

Report `228 / 18,468 = 1.23%` only as the newest automatic triage result. Do not
call it the current spot-check-supported final baseline until the `14` newly
promoted rows and a sample of the remaining review queue are spot-checked.

## Automatic Workflow

1. Preflight the repo.
   - Confirm the current directory is the repo root.
   - Record Git status with LFS filters disabled.
   - Stop if required TIFF/STL/JSON files are Git LFS pointer text.

2. Verify Phase 0 canonical graph.
   - Use `python3 -m src.part2.phase0` only if outputs are missing or stale.
   - Keep raw JSON aliases separate from canonical physical nodes.

3. Verify design intent and transform gates.
   - Use the human-anchored Phase 2R.1 transform only when the anchor gate passed.
   - Stop if graph/STL/CT orientation is unresolved.

4. Verify CT feature coverage.
   - Use the registered JSON as the expected CT strut atlas.
   - Remember registered coordinates are `[x,y,z]`; TIFF arrays are `[z,y,x]`.
   - Exclude node zones when judging strut bodies.

5. Run guarded labels if needed.
   - Command: `python3 -m src.part2.phase2b3_guarded_labels`
   - Treat Phase 2B.3 as screening, not publication.

6. Run strict automated review if needed.
   - Command: `python3 -m src.part2.phase2b4_automated_review`
   - Keep blocked manual-review rows unresolved.

7. Run Phase 2C second-pass triage if needed.
   - Command: `python3 -m src.part2.phase2c_manual_queue_triage --phase2b4-dir outputs/part2/phase2b4/20260727_092219`
   - Use `--skip-panels` for fast repeat runs.
   - Keep still-review-required rows unresolved.

8. Export the local defect viewer if needed.
   - Command: `python3 -m src.part2.visualization.export_defect_viewer --labels-csv outputs/part2/phase2c/20260727_132248/phase2c_labels.csv`
   - Viewer output opens from `outputs/part2/visualization/<run_id>/index.html`.

9. Run the config-driven pipeline when a single orchestration command is useful.
   - Dry run: `python3 -m src.part2.run_defect_pipeline --config configs/part2.yaml --dry-run`
   - Full current run: `python3 -m src.part2.run_defect_pipeline --config configs/part2.yaml`
   - Stop if the dataset preflight reports missing registered JSON or Git LFS pointers.

10. Package the conservative final report.
   - Command: `python3 -m src.part2.final_report`
   - Output goes under `outputs/part2/final_report/<run_id>/`.
   - Current final-report script packages the Phase 2B.4 spot-check-supported baseline, not the unreviewed Phase 2C promoted rows.

11. Run tests.
   - Targeted: `python3 -m unittest tests.part2.test_final_report -v`
   - Phase 2C/viewer: `python3 -m unittest tests.part2.test_phase2c_manual_queue_triage tests.part2.test_pipeline_and_viewer -v`
   - Full Part 2: `python3 -m unittest discover -s tests/part2 -v`

12. Update notes.
   - Update `notes/00-big-picture.md` briefly.
   - Update `notes/project-notebook.md` links and next step.
   - Update `notes/sections/01-how-to-run-code.md` with commands.
   - Update `notes/sections/05-task-log-and-experiments.md` with what changed, why, tests, results, failures, and next gate.
   - Update `notes/sections/24-part2-phase2c-automatic-triage-and-viewer.md` when Phase 2C or viewer behavior changes.

## Beginner Explanation To Preserve

The STL tells what the design intended. The registered JSON tells where each
expected strut should be inside the CT scan. The TIFF tells what material was
actually scanned. Bright voxels usually mean titanium alloy; dark voxels usually
mean air or missing material.

A possible unintended defect means:

```text
the design says the strut should be present,
but the CT evidence looks missing or broken.
```

An intentionally designed removal means:

```text
the design already removed that strut,
so it should not be counted as an unintended defect.
```

## Stop Gates

Stop and report the blocker when:

- required raw data are missing or still Git LFS pointers;
- transform status is unresolved;
- all-edge CT coverage is missing;
- human spot-check labels are missing for a final report;
- blocked manual-review rows are being counted as defects;
- Phase 2C newly promoted rows are being presented as spot-check-supported without review;
- a report claims fully human-labeled ground truth from automated labels.
