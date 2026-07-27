---
title: Big Picture
created: 2026-07-20
updated: 2026-07-27
tags:
  - llnl
  - project-status
  - big-picture
---

# Big Picture

## Current Status

- Branch: `haseeb`
- Task 1 is complete: `segment_ct_dataset()` is implemented in `src/mcp_server.py`.
- Task 2 is complete: `visualize_slice()` is implemented in `src/mcp_server.py`.
- Task 3 is complete: `skeletonize()` is implemented in `src/mcp_server.py`.
- Task 4 is complete: generated an NDE report from the raw CT volume, mask, skeleton, and 3D views.
- Task 5 is complete: created the custom `threshold-optimizer` project skill.
- Task 6 is complete: created the `segmentation_agent` subagent config and generated required segmentation outputs for the real 9x9x9 TIFF.
- Task 7 is complete: created the segmentation evaluation rubric and evaluated the Task 6 result image.
- Part 2 Phase 0 is complete: data preflight, JSON schema audit, canonical graph adapter, nominal/registered graph transform audit, tests, and Phase 0 outputs.
- Part 2 Phase 1 is complete: mapped likely intentionally removed `0.5.stl` design struts to canonical edge IDs and prepared a registered CT sampler skeleton.
- A CT review index now maps Phase 1 edge IDs to exact TIFF z-slice ranges and x/y windows for human inspection before Phase 2.
- Targeted CT edge panels now give cleaner review images than manual Napari slice scrolling, but boundary cases still need quantitative Phase 2 sampling.
- A simplified rank 001 versus rank 100 comparison shows visual review alone cannot reliably distinguish design-removed from design-present CT evidence.
- Part 2 Phase 2A is complete as a calibration run: an edge-owned 3D CT sampler, STL-axis audit, calibration cohort, parameter sweep, and QC review panels were generated.
- Phase 2B final CT classification is still blocked because Phase 2A did not cleanly separate design-removed candidates from matched design-present controls.
- Part 2 Phase 2A.1 is complete: exact point-to-triangle STL scoring, 48-way symmetry audit, provisional design-intent map, and human gold-review packet were generated.
- Phase 2B remains blocked because Phase 2A.1 mapping status is `UNRESOLVED`.
- Part 2 Phase 2R is complete: a method-pivot benchmark tested STL voxel subtraction, CT-only strut-atlas anomaly ranks, and late-fusion transform ranking.
- Phase 2R fusion status is `PROVISIONAL`, not `VERIFIED`, because the leading transform had CT features for only `7/67` mapped deleted-volume components.
- Part 2 Phase 2R.1 is complete: expanded CT coverage, generated 5 primary anchor panels plus 5 backups, and wrote a blank human anchor label CSV.
- The Phase 2R.1 anchor gate passed: 5/5 primary anchors support `perm021_signmmm`; next step is Phase 2B CT calibration preparation, not final percentages yet.
- Part 2 Phase 2B calibration preparation is complete on the 1,300-row sampled CT feature cohort: design-removed candidates separate strongly from controls, but final percentages remain blocked until uncertain cases and broader sampling are handled.
- Part 2 Phase 2B.1 reconciled the `67` deleted STL components with the expected `~92` struts: volume-based multi-edge mapping gives `94` design-strut candidates, samples 26 additional CT edges, and keeps CT separation strong.
- Part 2 Phase 2B.2 all-edge CT sampling is complete: combined CT feature coverage is now `18,468 / 18,468` registered edges.
- Part 2 Phase 2B.3 guarded CT labels are complete: all `18,468` edges received review-aware labels, but final publication percentages remain blocked pending review.
- Part 2 Phase 2B.4 automated evidence review is complete: strict rules support `214` possible unintended missing/disconnected candidates for draft internal reporting, with `920` rows still blocked for review.
- Part 2 final report packaging is complete: `outputs/part2/final_report/20260727_123413/` contains the report, summary JSON, tables, QC figure, and agentic workflow guide.
- Part 2 Phase 2C is complete as an automatic second-pass triage: it keeps all `18,468` struts checked, promotes `14` very clear blocked rows, reports `228` auto-supported possible unintended candidates, and leaves `677` rows review-required.
- A local defect viewer is available at `outputs/part2/visualization/20260727_132343/index.html`; it colors all registered struts by current Phase 2C class.
- A config-driven pipeline runner is available: `python3 -m src.part2.run_defect_pipeline --config configs/part2.yaml`.
- The reusable Part 2 agentic-system tools are `.agents/skills/part2-defect-analysis/SKILL.md`, `.codex/agents/part2_defect_analysis_agent.toml`, `src/part2/run_defect_pipeline.py`, and `src/part2/visualization/export_defect_viewer.py`.
- A collaborator verification transfer packet is ready at `collaboration/part2_verification_handoff_20260727/`; it includes notes, agent assets, review CSVs, 120 Phase 2C panels, and the local viewer, but no raw TIFF/STL/source JSON data.
- Git LFS data has been pulled; the 9x9x9 TIFF and missing-struts TIFF/STL/JSON files are local.
- Keep detailed reasoning, tests, failures, and decisions in [[project-notebook]].

## Most Important Findings

- `data/unitcell/unitcell.npy` is usable locally.
- `unitcell.npy` shape is `(256, 256, 256)` and dtype is `float32`.
- Its intensity range is about `-0.00313` to `0.01526`, not `[0, 1]`.
- `unitcell.npy` is only the first test dataset; future work should support many datasets.
- Threshold `0.5` is wrong for this file.
- Threshold `0.003` produced a valid binary mask with `780596` foreground voxels, about `4.65%` of the volume.
- Slice visualization at axis `0`, slice `128` shows the threshold `0.003` mask captures the main lattice cross-section cleanly.
- Task 4 report shows mean intensity inside the mask is about `0.011069`, while outside the mask is about `0.000025`; this supports that the mask is selecting bright material.
- Task 4 skeleton metrics: `3,314` skeleton voxels, `17` connected components, `73` endpoints, and `158` branchpoint-like voxels.
- The `0.5` value in Task 4 visualization is only a surface-drawing level for the binary mask; the scientific threshold to sweep is the Task 1 raw-data threshold such as `0.002`, `0.003`, `0.005`, and `0.01`.
- Threshold inspection is complete for `0.001`, `0.002`, `0.003`, `0.004`, `0.005`, `0.007`, and `0.010`.
- Main result: `0.004` is the first tested threshold where both the mask and skeleton become one connected 3D component.
- The `17` connected components at `0.003` should not be treated as `17` defects because the structure becomes connected at `0.004`.
- The Task 5 skill is `.agents/skills/threshold-optimizer/SKILL.md`.
- Codex must be restarted from the repo root before the new skill is available in a fresh session.
- The Task 6 subagent is `.codex/agents/segmentation_agent.toml`.
- The Task 6 subagent uses `model = "gpt-5.5"` and `model_reasoning_effort = "xhigh"`.
- The Task 6 TIFF is now real local data: `data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif` is about `990 MB`.
- Task 6 segmentation selected threshold `36916`, which is `0.9 * sampled Otsu threshold`.
- Task 6 mask foreground fraction is about `0.149986`, meaning about `15.0%` of the full volume was labeled as material.
- Task 7 evaluation score is `3/5`: main topology is preserved, but the result is systematically over-segmented/thicker than ground truth.
- Helper metrics from cropped rendered panels: Dice `0.7655`, IoU `0.6202`, precision `0.6209`, recall `0.9981`.
- Task 7 improvement check is complete: the main issue was low precision/too many false positives from threshold `36916`.
- Improved calibration against the provided slice-380 ground truth selected threshold `38557` with `open_close2d` cleanup.
- Improved rendered-panel metrics: Dice `0.8976`, IoU `0.8142`, precision `0.8309`, recall `0.9759`.
- Improved outputs are saved under `data/9x9x9_octet_lattice/segmentation_improved/` and `evals/segmentation_eval_slice_380_improved_report.md`.
- This likely improves the rubric score, but a clean `5/5` is not guaranteed because small false positives and false negatives remain.
- Missing-struts data is now local: TIFF stack about `990 MB`, four STL files about `166-168 MB` each, plus JSON metadata.
- Missing-struts inspection is complete for file meaning, metadata, paper context, JSON/TIFF registration, STL summaries, and tilt estimate.
- The missing-struts TIFF is byte-for-byte identical to `data/9x9x9_octet_lattice/9x9x9_octet_lattice.tif`.
- Registered JSON overlay on slice `380` visually lands on the CT lattice features.
- Registered JSON scale estimates `0.057738 mm/voxel`, close to the paper's `0.0581 mm/voxel`.
- The registered graph is slightly rotated relative to the image grid, about `0.335 degrees`, or about `4.157 voxels` drift across the full graph span.
- The `0.5.stl` design implies about `92.3` intentionally removed struts; the paper reports about `105.3` CT-missing struts for specimen `0.5% (#1)` using `18468` as the approximate denominator.
- For missing-strut defect analysis, use the TIFF as the actual scan and the registered JSON as the aligned expected strut map; use STL for design intent only after registration or strut-ID recovery.
- Part 2 canonical graph counts: 8x8 fixture has `2457` physical nodes and `13056` struts; 9x9 nominal/registered graphs each have `3430` physical nodes and `18468` struts.
- Nominal and registered 9x9 graphs have matching source identity; the fitted nominal-to-registered transform residual is near numerical roundoff.
- Phase 1 found `92` likely intentionally removed design edges from `0.5.stl`, matching `round(0.005 * 18468)`.
- Direct STL triangle-set difference was not clean enough by itself: `157833` baseline-only triangle keys versus a simple triangle-count drop of `15986`.
- The useful Phase 1 signal was centerline-to-STL-surface distance increase; weakest flagged mean delta was `0.247934 mm`, strongest unflagged was `0.104477 mm`.
- These 92 edges are design-intent labels, not final CT defect labels.
- Phase 1 review images are saved under `outputs/part2/phase1/qc/review_panels/`.
- CT review index files are saved under `outputs/part2/phase1/ct_review/`.
- Targeted CT edge panels are saved under `outputs/part2/phase1/ct_review/panels/`.
- CT comparison figures are saved under `outputs/part2/phase1/ct_review/comparisons/`.
- Phase 2A outputs are saved under `outputs/part2/phase2a/`.
- Phase 2A sampled `468` calibration edges: `92` design-removed candidates, `276` matched present controls, and `100` random present controls.
- Phase 2A tested `48` STL axis/sign mappings; all preserved the 92-count, but only the identity transform preserved the exact same top edge IDs, so `A-STL-AXIS-001` remains `UNVERIFIED`.
- Phase 2A base CT diagnostic did not separate groups: present-minus-removed mean score was `-0.295609`, 95% bootstrap CI was `[-1.249036, 0.609976]`, and ROC AUC was `0.475780`.
- Phase 2A generated `30` unique CT review panels under `outputs/part2/phase2a/qc/review_panels/`.
- Phase 2A.1 exact STL scoring evaluated all `18,468` canonical edges.
- Phase 2A.1 found a natural exact-score gap after rank `91`: `0.548682 mm` above the gap versus `0.014862 mm` below it.
- Phase 2A.1 provisional states: `75` strong removed candidates, `18,326` strong present candidates, and `67` ambiguous edges.
- Phase 2A.1 symmetry audit top transforms were too close, so exact graph/STL edge-ID mapping remains `UNRESOLVED`.
- Phase 2A.1 review packet has `80` panels and a blank human-label CSV under `outputs/part2/phase2a1/gold_review/`.
- Phase 2R STL occupancy natural deleted-volume component counts: `7` for 0.1%, `67` for 0.5%, and `104` for 1.0%.
- Phase 2R CT atlas evaluated `500` edges; median anomaly was `0.000`, 95th percentile anomaly was `2.353`, and maximum anomaly was `3.944`.
- Phase 2R leading fusion transform is `perm021_signmmm`, but it is only a lead because CT coverage is too sparse.
- Phase 2R.1 expanded CT features to `1300` edges and sampled `800` new edges.
- Phase 2R.1 leading transform remains `perm021_signmmm`, now with `67/67` mapped deleted components evaluated.
- Phase 2R.1 anchor packet is `outputs/part2/phase2r1/anchor_review.html`; labels go in `outputs/part2/phase2r1/human_anchor_labels.csv`.
- Phase 2B.2 latest full all-edge run is `outputs/part2/phase2b2/20260727_013304/`.
- Phase 2B.2 candidate status counts across all `18,468` edges: `90` design-removed missing-like, `4` design-removed low-anomaly/uncertain, `1,137` unexpected missing-like candidates, `718` near-threshold uncertain, and `16,519` present-like.
- Phase 2B.2 is still not final classification because candidate statuses need uncertainty rules, review handling, and final missing/disconnected definitions.
- Phase 2B.3 latest guarded-label run is `outputs/part2/phase2b3/20260727_090709/`.
- Phase 2B.3 guarded counts: `88` designed-removed CT-absent, `1` designed-removed disconnected/residual, `4` designed-removed CT-present conflict, `420` possible unintended missing, `58` possible unintended disconnected, `3,076` uncertain review-required, and `14,820` present-like.
- Phase 2B.3 review load: `3,573` rows require review before final publication; `60` highest-priority CT review panels were generated.
- Phase 2B.4 latest automated-review run is `outputs/part2/phase2b4/20260727_092219/`.
- Phase 2B.4 strict automated counts: `202` auto-supported possible unintended missing, `12` auto-supported possible unintended disconnected, `89` auto-supported designed-removed absent/disconnected, `14,820` auto-supported present-like, `920` blocked manual-review rows, and `2,425` low-priority uncertain not defect-like rows.
- Phase 2B.4 draft automated possible unintended combined fraction is `214 / 18,468 = 0.0115876`, about `1.16%`, but this is not final publication until spot-check approval.
- Human spot-check of Phase 2B.4 ranks `001-040` found `36/40` defect-like, `4/40` ambiguous, and `0/40` present-like contradictions; this supports using the `214` count as a spot-check-supported draft estimate with caveats.
- Final report package status is `SPOTCHECK_SUPPORTED_AUTOMATED_ESTIMATE_NOT_FULL_GROUND_TRUTH`, not exhaustive human ground truth.
- Phase 2C second-pass triage result: `215` auto-supported possible unintended missing, `13` auto-supported possible unintended disconnected, `228` combined, `677` still review-required, and `2,654` low-priority uncertain not counted as defects.
- Phase 2C is an improved automatic triage layer, not new human ground truth. The `228 / 18,468 = 1.23%` number should be treated as stronger internal automation evidence, while the earlier `214 / 18,468 = 1.16%` final package remains the spot-check-supported report baseline.
- Verification handoff priority: collaborators should review the `14` newly promoted Phase 2C rows first, then high-priority rows from the `677` still-review-required queue, then audit-sample the `2,654` low-priority uncertain rows.
- Notes are now organized as an Obsidian-style vault with clickable topic files under `notes/sections/`.

## What Is Done

- Understood repo purpose and data layout.
- Confirmed Git LFS explains why local data looks small.
- Implemented threshold segmentation for `.npy` CT volumes.
- Generated and validated `outputs/task1/unitcell_mask_threshold_0p003.npy`.
- Implemented 2D slice visualization for `.npy` volumes and masks.
- Generated `outputs/task2/unitcell_raw_axis0_slice128.png`.
- Generated `outputs/task2/unitcell_mask_t0p003_axis0_slice128.png`.
- Implemented skeletonization wrapper for binary `.npy` masks.
- Generated `outputs/task3/unitcell_skeleton_t0p003.npy`.
- Generated `outputs/task3/unitcell_skeleton_t0p003_axis0_slice128.png`.
- Generated `outputs/task4/unitcell_nde_report.md`.
- Generated `outputs/task4/unitcell_nde_metrics.json`.
- Generated Task 4 3D views in `outputs/task4/`.
- Generated threshold inspection outputs in `outputs/threshold_inspection/`.
- Added reusable threshold inspection script `src/threshold_inspection.py`.
- Created `.agents/skills/threshold-optimizer/SKILL.md`.
- Created `.agents/skills/threshold-optimizer/agents/openai.yaml`.
- Validated the new skill with `quick_validate.py`.
- Created `.codex/agents/segmentation_agent.toml`.
- Validated that the subagent TOML parses correctly with Python `tomllib`.
- Generated `data/9x9x9_octet_lattice/segmentation/segment_lattice.py`.
- Generated `data/9x9x9_octet_lattice/segmentation/mask.tif`.
- Generated `data/9x9x9_octet_lattice/segmentation/slice_380.png`.
- Generated `data/9x9x9_octet_lattice/segmentation/metrics.json`.
- Generated `data/9x9x9_octet_lattice/segmentation/report.md`.
- Created `evals/rubric_segmentation_1.md`.
- Created `evals/segmentation_eval_slice_380_result.json`.
- Created `evals/segmentation_eval_slice_380_report.md`.
- Created `evals/segmentation_slice_380_data_panel_comparison.png`.
- Added `outputs/` to `.gitignore`.
- Organized notes into clickable Obsidian sections:
  - [[project-notebook]]
  - [[sections/01-how-to-run-code]]
  - [[sections/02-physics-materials-imaging]]
  - [[sections/03-data-inventory-git-lfs]]
  - [[sections/04-code-design-and-explanations]]
  - [[sections/05-task-log-and-experiments]]
  - [[sections/06-codex-workflow-and-prompts]]
  - [[sections/07-glossary]]
  - [[sections/08-open-questions]]
  - [[sections/09-missing-struts-data]]
- Created and updated `src/inspect_missing_struts_data.py`.
- Generated `outputs/missing_struts_inventory/report.md`.
- Generated `outputs/missing_struts_inventory/summary.json`.
- Generated `outputs/missing_struts_inventory/tif_sample_slices.png`.
- Generated `outputs/missing_struts_inventory/registered_json_overlay_z380.png`.
- Created `src/part2/io/lattice_graph.py`.
- Created `src/part2/phase0.py`.
- Created `tests/part2/test_lattice_graph.py`.
- Generated Phase 0 outputs under `outputs/part2/phase0/`.
- Created [[sections/10-part2-phase0-canonical-graph]].
- Created `src/part2/design_intent/stl_design_mapping.py`.
- Created `src/part2/ct_features/edge_sampler.py`.
- Created `src/part2/phase1.py`.
- Created `tests/part2/test_stl_design_mapping.py`.
- Created `tests/part2/test_edge_sampler.py`.
- Generated Phase 1 outputs under `outputs/part2/phase1/`.
- Created [[sections/11-part2-phase1-design-intent]].
- Created `src/part2/visual_review/ct_review_index.py`.
- Created `tests/part2/test_ct_review_index.py`.
- Generated CT review index outputs under `outputs/part2/phase1/ct_review/`.
- Created [[sections/12-part2-ct-review-and-phase2-readiness]].
- Created `src/part2/visual_review/ct_edge_panels.py`.
- Created `tests/part2/test_ct_edge_panels.py`.
- Created `.codex/agents/ct_visual_review_agent.toml`.
- Generated targeted CT review panels under `outputs/part2/phase1/ct_review/panels/`.
- Created `src/part2/visual_review/ct_edge_compare.py`.
- Created `tests/part2/test_ct_edge_compare.py`.
- Generated rank comparison outputs under `outputs/part2/phase1/ct_review/comparisons/`.
- Created `src/part2/design_intent/stl_axis_audit.py`.
- Created `src/part2/ct_features/edge_owned_sampler.py`.
- Created `src/part2/phase2a.py`.
- Created `tests/part2/test_stl_axis_audit.py`.
- Created `tests/part2/test_edge_owned_sampler.py`.
- Generated Phase 2A calibration outputs under `outputs/part2/phase2a/`.
- Created [[sections/13-part2-phase2a-ct-calibration]].
- Created `src/part2/design_intent/exact_stl_distance.py`.
- Created `src/part2/phase2a1.py`.
- Created `tests/part2/test_phase2a1_exact_stl_distance.py`.
- Created `docs/part2/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md`.
- Generated Phase 2A.1 outputs under `outputs/part2/phase2a1/`.
- Created [[sections/14-part2-phase2a1-design-intent-repair]].
- Created `src/part2/phase2r_tools.py`.
- Created `src/part2/phase2r.py`.
- Created `tests/part2/test_phase2r_hybrid_benchmark.py`.
- Generated Phase 2R outputs under `outputs/part2/phase2r/`.
- Created [[sections/15-part2-phase2r-method-pivot-benchmark]].
- Created `src/part2/phase2r1_tools.py`.
- Created `src/part2/phase2r1.py`.
- Generated Phase 2R.1 outputs under `outputs/part2/phase2r1/`.
- Created [[sections/16-part2-phase2r1-anchor-review]].
- Created `src/part2/phase2b3_guarded_labels.py`.
- Created `tests/part2/test_phase2b3_guarded_labels.py`.
- Generated Phase 2B.3 outputs under `outputs/part2/phase2b3/20260727_090709/`.
- Created [[sections/21-part2-phase2b3-guarded-labels]].
- Created `src/part2/phase2b4_automated_review.py`.
- Created `tests/part2/test_phase2b4_automated_review.py`.
- Generated Phase 2B.4 outputs under `outputs/part2/phase2b4/20260727_092219/`.
- Created [[sections/22-part2-phase2b4-automated-review]].

## What Is Not Done

- Final published missing/disconnected percentages are not approved yet.
- Phase 2B.4 spot-check supports the automated direction, but the `214` auto-supported possible unintended candidates are not exhaustively human-labeled.
- The `94` design-removed candidate edges are human-anchored and calibrated, but still carry design-intent assumptions from earlier phases.

## Next Step

Do not publish final CT defect percentages yet.

Next scientific gate:

Use `outputs/part2/phase2b4/20260727_092219/spotcheck_supported_report_section_draft.md` as the starting final-report section, keeping the caveat that the `214` count is spot-check-supported rather than exhaustively human-labeled.

## Working Rule

For every meaningful change, record in [[sections/05-task-log-and-experiments]]:

- What changed.
- Why it changed.
- How it was tested.
- What worked.
- What did not work.
- What should happen next.

For code we add, use learning-oriented comments and include run commands in [[sections/01-how-to-run-code]].
