# Part 2 Collaboration Handoff: Audited End-to-End Guide

Generated 2026-07-28 from the local handoff and raw-data checkout. This document explains the intended system, records what was actually verified, catalogs every one of the 176 packaged files, and gives a safe path forward.

## Executive verdict

**Overall status: needs revision before the Part 2 result can be called reproducible or ground truth.** The handoff itself is unusually thorough and internally consistent: all 176 files were inventoried, all 175 non-self manifest hashes match, every structured file parses, all 121 PNGs decode, the all-edge tables and viewer reconcile, and the viewer passed runtime interaction tests. However, the packet contains **zero Python source files**. The documented `src/part2/` implementation and `tests/part2/` suite are absent from this working tree and from every reachable Git revision.

The provenance is conclusive rather than speculative. `final_report_baseline/run_manifest.json` records `?? src/part2/` and `?? tests/` in the originating worktree, which means the friend generated the outputs while those directories were untracked and then committed the handoff without them. Consequently, the historical claim of 93 passing tests plus one optional VTK skip cannot be reproduced here. Re-implementing the algorithms from prose would create a new method, not validate the old one.

The original packet's most conservative numerical result is the **Phase 2B.4 214-candidate queue**: 202 possible unintended missing plus 12 possible unintended disconnected among 18,468 expected struts, or a 1.158761% candidate fraction. This audit found that three of those 202 possible-missing rows have both endpoints beyond the evidence pipeline's apparent x=767 support limit, `no_local_material` endpoint statuses, and all-zero area profiles, despite being marked clean for auto-support. The raw TIFF is 761 x 815 x 837, so the x=767 clamp is an unexplained sampling/cropping problem rather than the TIFF's true boundary. Those three must become `coverage_blocked`; therefore even 214 cannot be presented as a fully defensible auto-supported count until that logic is fixed. Phase 2C's 228 is still more provisional because all 14 promotions have blank human-review fields.

## What was verified

The automated audit records **43 passes, 19 warnings, and 2 blocking failures**. The failures are absent production/test source and invalid CT support for three auto-supported candidates; neither indicates corruption of the preserved packet files. The audit checked:

- all 176 package paths, sizes, and streamed SHA-256 hashes;
- every CSV, JSON, YAML, and TOML for parseability and table shape;
- exact set/count reconciliation across Phase 2B.4, Phase 2C, review queues, and viewer data;
- every one of 121 PNGs sequentially, avoiding simultaneous full-resolution image loads;
- exact rank, edge-ID, filename, panel-summary, and panel-index mapping for all 120 CT panels;
- viewer data, embedded JSON, legend styles, finite geometry, and all 18,468 edge IDs;
- live viewer search, legend toggling, zoom, reset, canvas rendering, console health, and screenshots;
- scientific stress checks against the cited 2023 paper, the top-40 review design, all 14 Phase 2C promotions, and boundary enrichment;
- CT-support checks against raw TIFF metadata, exposing three unsupported baseline candidates and 40 zero-signal top-120 panels;
- method/assumption/reference registries, config freshness, Boolean/NaN conventions, viewer numeric types, and source-artifact lineage.

These checks validate **artifact integrity and internal consistency**. They do not validate the absent feature extractor, registration, classification thresholds, or physical truth of each candidate.

## How the specialist skills changed this audit

The packaged `part2-defect-analysis` skill made coordinate-frame auditing, junction welding, provenance, design/CT separation, and conservative label language mandatory. The `threshold-optimizer` skill shifted attention from raw voxel agreement to structural stability and sensitivity. The `nde_report_expert` skill motivated consistent visual inventories and traceable summaries. The external data-validation workflow then required grain checks, reconciliation, representativeness, caveats, and an explicit readiness verdict. These instructions are why this guide does not silently equate an anomaly score, a colored viewer edge, or a top-ranked panel with a confirmed physical defect.

## Physical and coordinate context

The cited paper describes Ti-5553 lattices with nominal 424 micrometer struts, 4.56 mm cells, build direction along y, skins normal to z, and CT voxel size 58.1 micrometers. Its MATLAB workflow aligned the scan and model with translation, rotation, and scale, thresholded the volume, extracted an expected-strut subvolume, flagged gaps/deviation, and **manually reviewed every flagged subvolume**.

Graph/registered coordinates are stored as `[x,y,z]`; NumPy/TIFF volumes are indexed `[z,y,x]`. Therefore an expected edge with endpoints `(x1,y1,z1)` and `(x2,y2,z2)` must be sampled by converting physical/registered coordinates through the documented transform and then indexing `volume[z, y, x]`. A 'vortex' in earlier discussion is more accurately a **vertex/junction**. The TIFF does not directly store named vertices; vertex coordinates come from the registered design graph, while CT evidence tells whether material is present around each expected segment.

The graph also requires positional welding. Raw junction IDs repeat across unit-cell boundaries; treating them as globally distinct creates hundreds of false components. The documented canonical graph has 3,430 physical nodes and 18,468 unique expected edges only after aliases are welded.

## End-to-end pipeline

```text
design JSON + registered JSON + 0%/0.5% STL + CT TIFF
  -> Phase 0 canonical welded graph and frame audit
  -> Phase 1 provisional design-removed mapping and CT crop locations
  -> Phase 2A / 2A.1 negative calibration and exact-distance/frame audits
  -> Phase 2R hybrid STL subtraction + CT feature benchmark (provisional)
  -> Phase 2R.1 expanded coverage + five human transform anchors
  -> Phase 2B calibrated CT evidence
  -> Phase 2B.1 component-to-multiple-edge reconciliation
  -> Phase 2B.2 checkpointed all-18,468-edge feature sampling
  -> Phase 2B.3 guarded observations and uncertainty
  -> Phase 2B.4 strict 214-candidate conservative baseline
  -> top-40 non-random human spot check
  -> Phase 2C 14 provisional promotions + 677-row review queue
  -> all-edge graph viewer, reports, and manifests
```

### Phase 0: canonical design graph

The pipeline first parses nominal and registered graph JSON, detects LFS placeholders, welds coincident junction aliases, preserves raw provenance, and verifies connectivity and topology. This produces the only defensible edge universe. Any downstream method built directly on raw per-cell IDs can hallucinate disconnections at cell boundaries.

### Phase 1: provisional design intent and review locations

The two STL meshes are compared to find geometry apparently removed from the 0.5% design, then candidates are mapped to canonical edges. The initial heuristic yielded 92 candidates and was explicitly provisional. Registered edge geometry is also converted to TIFF slice/crop instructions; this locates evidence but does not itself decide present, missing, or disconnected.

### Phase 2A and 2A.1: methods that correctly stopped

Phase 2A calibrated an edge-owned CT sampler against the provisional removed/control groups and found poor separation (documented AUC 0.4758). Phase 2A.1 replaced the weak STL mapping with point-to-triangle distance scoring over all edges and audited 48 axis/sign symmetries, but stopped because the transform remained ambiguous. These negative results are useful: they prevent an attractive but invalid classifier from becoming a final answer.

### Phase 2R and 2R.1: hybrid transform selection

Phase 2R combined voxelized STL subtraction, deleted-component geometry, local CT alignment, straightened-strut features, robust templates, and late fusion over transforms. The apparent best transform `perm021_signmmm` was initially overclaimed because it covered only 7 of 67 components; the status was corrected to PROVISIONAL. Phase 2R.1 expanded CT coverage from 500 to 1,300 edges, achieved 67/67 candidate-component coverage for the leading transform, and used five manually reviewed anchors to pass a transform gate. This supports the frame choice but is not a specimen-wide defect truth set.

### Phase 2B through 2B.2: calibration and all-edge features

Phase 2B used the passed transform gate to calibrate removed candidates against controls and documented AUC 0.9626. Phase 2B.1 corrected the one-component/one-edge assumption by expanding 67 deleted components to 94 plausible edges. Phase 2B.2 then sampled all 18,468 expected edges with checkpoints and recomputed robust orientation/boundary/spatial templates. The journal says this all-edge run took about 2.74 hours and roughly 3.15 GB; it was not rerun on this 16 GB Mac because the source and prerequisite artifacts are absent.

### Phase 2B.3 and 2B.4: guarded labels and baseline

Phase 2B.3 combined anomaly score, axial occupancy, longest low-area gap, area, core/background contrast, template residual, 26-connectivity bridge status, threshold stability, and registration stability. It deliberately left mixed evidence unresolved. Phase 2B.4 raised the bar with stricter margins and minimum evidence counts, resulting in 202 possible unintended missing, 12 possible unintended disconnected, 89 designed-removed absent/disconnected, 14,820 present-like, 920 blocked, and 2,425 low-priority edges. That is the documented 214-candidate baseline, but the newly detected three-row support failure means its auto-support guard is incomplete.

### Human spot check and Phase 2C

A human reviewed only the top-ranked 40 of the baseline 214 and reported 29 absent, 7 disconnected, 4 ambiguous, and zero clearly present-like contradictions. This supports the ranking directionally but is a consecutive top-score sample with no present controls, so it cannot estimate whole-list precision, recall, or calibration. Phase 2C then reprocessed the blocked queue with stricter deterministic rules, promoted 14 rows, left 677 review-required, and moved 2,654 to low priority. Because none of the 14 is reviewed, 228 remains provisional.

### Viewer and reporting

The viewer draws every expected graph edge with a color representing its Phase 2C state. It is useful for global context, searching by edge ID, and toggling categories. It is **not a MeshLab/CT surface rendering** and cannot show voxel evidence by itself. The default view is cluttered because 2,654 low-priority and 677 review-required edges are enabled; a defect-focused preset is easier to interpret.

### CT evidence-coverage failure found by this audit

The raw TIFF metadata is `(z,y,x) = (761,815,837)`, yet every top-120 crop stops at x=767 and the viewer graph extends to x=773.744. Exactly 1,008 expected edges have at least one endpoint beyond x=767. Forty top-120 panels have completely zero edge-aligned slabs and traces; all 40 are review-required, which prevented those particular rows from being promoted, but they occupy one third of the review packet and need an explicit OUT OF SUPPORT watermark. More seriously, `E_N008309_N008313`, `E_N009317_N009321`, and `E_N009443_N009447` are already inside both the 214 and 228 candidate tables with two `no_local_material` endpoints, all-zero area profiles, and `phase2b4_clean_for_auto_support=true`. Rank 13 of the Phase 2C panels, `E_N001379_N001506`, also crosses the support boundary and needs endpoint caution. This is a pipeline-logic defect, not a new human judgment about whether any strut is physically present.

## External scientific cross-check against 2246722.pdf

For the paper's 0.5% specimen #1, Table 3 reports 0.57% total missing and 4.97% disconnected, with 0.50% nominal design removal; missing and disconnected are mutually exclusive there. Using 18,468 only as a common comparison denominator gives roughly 105 total missing, 92 nominally removed, about 13 excess/unintended missing, and 918 disconnected. Phase 2C instead contains 89 designed-removed, 215 possible unintended missing, and only 13 possible unintended disconnected.

This mismatch does not automatically prove individual candidates wrong because the denominators, label rules, and pipeline purposes differ. It does prove the packet is **not paper-equivalent classification**: missing-like candidates are much more numerous and disconnected candidates much less numerous than the manually reviewed paper distribution. The leading interpretation is that the current output is a high-recall/uncertainty triage queue with a disconnected rule that is too strict or semantically different. It must be validated against a representative manual sample before physical percentages are claimed.

## Documented production scripts (source absent)

Every paragraph in this section is reconstructed from the journals and ledgers. None of these files exists in the packet, current worktree, or reachable Git history, so no function body was code-reviewed and no listed script was executed.

### `src/part2/io/lattice_graph.py`

Parsed the real junction/strut/unit-cell schema, welded coincident raw junction aliases into physical nodes, retained provenance, and checked connectivity/topology. This welding is mandatory: raw per-cell IDs do not represent the global physical graph. **Verification status: documentation-only; source absent.**

### `src/part2/phase0.py`

Orchestrated input preflight, LFS checks, canonicalization, graph consistency, nominal-to-registered transform estimation, and Phase 0 reports. **Verification status: documentation-only; source absent.**

### `src/part2/design_intent/__init__.py`

Marked the design-intent helper package; no standalone behavior is documented. **Verification status: documentation-only; source absent.**

### `src/part2/design_intent/stl_design_mapping.py`

Implemented the original provisional STL-difference heuristic and ranked 92 apparent design-removed edges; later methods superseded its mapping. **Verification status: documentation-only; source absent.**

### `src/part2/ct_features/__init__.py`

Marked the CT-feature package; no standalone behavior is documented. **Verification status: documentation-only; source absent.**

### `src/part2/ct_features/edge_sampler.py`

Prepared registered graph-edge samples in CT coordinates and handled the critical JSON [x,y,z] to TIFF-array [z,y,x] indexing conversion. **Verification status: documentation-only; source absent.**

### `src/part2/phase1.py`

Ran initial STL inspection, provisional design mapping, edge previews, score plots, and review panels without claiming design labels were CT truth. **Verification status: documentation-only; source absent.**

### `src/part2/visual_review/__init__.py`

Marked the visual-review package; no standalone behavior is documented. **Verification status: documentation-only; source absent.**

### `src/part2/visual_review/ct_review_index.py`

Mapped edge geometry to exact TIFF slices and crop windows. It located evidence but did not classify a defect. **Verification status: documentation-only; source absent.**

### `src/part2/visual_review/ct_edge_panels.py`

Rendered XY/XZ/YZ projections, a straightened edge slab, intensity profile, centerline overlay, and optional threshold contours from local TIFF crops. **Verification status: documentation-only; source absent.**

### `src/part2/visual_review/ct_edge_compare.py`

Made shared-intensity side-by-side edge comparisons for visual teaching and QA, not final classification. **Verification status: documentation-only; source absent.**

### `src/part2/design_intent/stl_axis_audit.py`

Enumerated axis permutations/reflections and audited skins, boundary directions, and graph/STL frames so identity orientation was not assumed. **Verification status: documentation-only; source absent.**

### `src/part2/ct_features/edge_owned_sampler.py`

Excluded node-dominated endpoints, assigned voxels to the nearest eligible edge, measured core/background evidence, and evaluated threshold/radius/registration sensitivity. **Verification status: documentation-only; source absent.**

### `src/part2/phase2a.py`

Swept CT sampler parameters on candidate and control edges. Its negative separation result was an appropriate stop rather than a classification success. **Verification status: documentation-only; source absent.**

### `src/part2/design_intent/exact_stl_distance.py`

Compared sampled edge centerlines to both STL surfaces with point-to-triangle distances; despite its name, documentation says this was not a signed exact solid distance. **Verification status: documentation-only; source absent.**

### `src/part2/phase2a1.py`

Scored all 18,468 edges under 48 frame symmetries and stopped because orientation remained unresolved. **Verification status: documentation-only; source absent.**

### `src/part2/phase2r_tools.py`

Held heavy hybrid primitives for voxelized STL subtraction, deleted-component mapping, local CT correction, straightening, feature extraction, robust templates, transform fusion, bootstrap summaries, and gates. **Verification status: documentation-only; source absent.**

### `src/part2/phase2r.py`

Ran the design/CT late-fusion benchmark. The logged run took about 464 seconds and 3.1 GB peak RAM and ended PROVISIONAL because the apparent best transform initially covered only 7 of 67 components. **Verification status: documentation-only; source absent.**

### `src/part2/phase2r1_tools.py`

Expanded transform cohorts, ranked anchor cases, preserved human fields, validated CSV inputs, and performed numerical gate decisions. **Verification status: documentation-only; source absent.**

### `src/part2/phase2r1.py`

Expanded CT coverage from 500 to 1,300 edges, obtained 67/67 coverage for the leading transform, and produced five primary human-anchor cases. **Verification status: documentation-only; source absent.**

### `src/part2/phase2r1_anchor_gate.py`

Applied a lightweight post-review gate; five supplied anchors supported perm021_signmmm, but five anchors do not validate all defect labels. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b_tools.py`

Provided AUC/threshold summaries, robust template updates, deleted-component multiplicity estimates, candidate collapse, and safe boolean parsing. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b_calibration.py`

Calibrated 1,300 CT rows after the transform gate, obtaining documented AUC 0.9626 while still avoiding final specimen-wide percentages. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b1_reconcile.py`

Recognized one deleted STL component could represent several struts, expanding 67 components to 94 candidate edges and sampling missing CT rows. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b2_all_edge_prep.py`

Checkpointed, resumed, and prioritized feature sampling for all 18,468 edges. The logged full run took about 2.74 hours and reached roughly 3.15 GB memory. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b3_guarded_labels.py`

Converted complete CT features into guarded observations using anomaly, gap, area, occupancy, contrast, bridge, template, and stability evidence, leaving mixed cases unresolved. **Verification status: documentation-only; source absent.**

### `src/part2/phase2b4_automated_review.py`

Applied stricter margins and evidence-count requirements to form the conservative 214-candidate baseline, 920 blocked cases, and 2,425 low-priority cases. **Verification status: documentation-only; source absent.**

### `src/part2/final_report.py`

Packaged existing Phase 2B.4 artifacts and supplied top-40 labels into tables, figures, reports, and provenance; it did not generate new CT evidence. **Verification status: documentation-only; source absent.**

### `src/part2/phase2c_manual_queue_triage.py`

Reused existing features for a stricter second pass, promoting 14 rows, retaining 677 for review, and demoting 2,654 to low priority. **Verification status: documentation-only; source absent.**

### `src/part2/visualization/__init__.py`

Marked the visualization package; no standalone behavior is documented. **Verification status: documentation-only; source absent.**

### `src/part2/visualization/export_defect_viewer.py`

Joined registered endpoints to labels and exported the dependency-free graph viewer and legend. **Verification status: documentation-only; source absent.**

### `src/part2/run_defect_pipeline.py`

Checked inputs/hashes, planned stages, supported dry-run, reused Phase 2B.4 evidence, invoked Phase 2C and viewer export, and packaged reports. **Verification status: documentation-only; source absent.**

## Documented original tests (also absent)

The journals say this suite reached 93 passing tests with one optional VTK skip. The following files and responsibilities are documentation-derived; the claim is historical testimony, not a reproducible result in this checkout.

### `tests/part2/test_lattice_graph.py`

This test module reportedly covered schema parsing, alias welding, provenance, connectivity, and nominal/registered consistency. **Verification status: test source absent and not runnable.**

### `tests/part2/test_stl_design_mapping.py`

This test module reportedly covered initial STL-to-edge scoring and deterministic ranking. **Verification status: test source absent and not runnable.**

### `tests/part2/test_edge_sampler.py`

This test module reportedly covered registered edge sampling and CT-axis conversion. **Verification status: test source absent and not runnable.**

### `tests/part2/test_ct_review_index.py`

This test module reportedly covered deterministic edge-to-TIFF slice/window instructions. **Verification status: test source absent and not runnable.**

### `tests/part2/test_ct_edge_panels.py`

This test module reportedly covered crop extraction and repeatable panel rendering. **Verification status: test source absent and not runnable.**

### `tests/part2/test_ct_edge_compare.py`

This test module reportedly covered shared-scale comparison rendering and metadata. **Verification status: test source absent and not runnable.**

### `tests/part2/test_stl_axis_audit.py`

This test module reportedly covered coordinate-frame evidence and transform enumeration. **Verification status: test source absent and not runnable.**

### `tests/part2/test_edge_owned_sampler.py`

This test module reportedly covered endpoint exclusion, finite-edge ownership, local sampling, and perturbations. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2a1_exact_stl_distance.py`

This test module reportedly covered point-to-triangle scoring and review ranking. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2r_hybrid_benchmark.py`

This test module reportedly covered voxel subtraction, straightening, registration, robust statistics, transform fusion, coverage/anchor gates, and CSV validation; one VTK case was optional. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2b_calibration.py`

This test module reportedly covered calibration statistics, multiplicity, candidate collapse, boolean parsing, batches, checkpoints, and all-edge preparation. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2b3_guarded_labels.py`

This test module reportedly covered guarded-label boundaries, warnings, uncertainty, and design/CT separation. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2b4_automated_review.py`

This test module reportedly covered strict auto-support, blocking, and low-priority rules. **Verification status: test source absent and not runnable.**

### `tests/part2/test_final_report.py`

This test module reportedly covered arithmetic, preservation of human labels, conservative wording, and packaging. **Verification status: test source absent and not runnable.**

### `tests/part2/test_phase2c_manual_queue_triage.py`

This test module reportedly covered promotion, demotion, preservation, and unresolved-case rules. **Verification status: test source absent and not runnable.**

### `tests/part2/test_pipeline_and_viewer.py`

This test module reportedly covered viewer joining/export and configuration-driven dry/full orchestration. **Verification status: test source absent and not runnable.**

## How to use what is available now

### 1. Run the memory-conscious artifact audit

From the repository root:

```bash
/Users/amannindra/miniconda3/envs/DSC/bin/python -m unittest \
  Aman_Scripts.collaboration_codex.tests.test_audit -v

/Users/amannindra/miniconda3/envs/DSC/bin/python \
  Aman_Scripts/collaboration_codex/run_audit.py
```

The unit tests should pass. `run_audit.py` intentionally exits with status 1 while production source is missing; inspect the JSON/Markdown outputs rather than suppressing that blocker. Image inspection is sequential, and contact sheets are capped at 20 panels each.

### 2. Open and exercise the viewer

Opening index.html directly may be sufficient because data are embedded. For a local web server:

```bash
cd collaboration/part2_verification_handoff_20260727/viewer
/Users/amannindra/miniconda3/envs/DSC/bin/python -m http.server 8000 --bind 127.0.0.1
```

Then visit `http://127.0.0.1:8000/`. Search by exact edge ID, turn off present-like and uncertain categories for a defect-focused view, and use the review index to open CT evidence. The automated headless check is:

```bash
/Users/amannindra/miniconda3/envs/DSC/bin/python \
  Aman_Scripts/collaboration_codex/browser_smoke.py
```

### 3. Review Phase 2C without contaminating labels

Start with `newly_promoted_14_to_verify.csv`, find each edge in `review_panel_index.csv`, inspect all available panel views, and enter only the allowed human label plus confidence/initials/date in a copy of `human_verification_template.csv`. Do not join the old baseline human labels to these panels by rank, and do not train/tune thresholds on the held-out verification decisions before reporting evaluation.

### 4. Recover the real code before rerunning science

Ask the friend for the exact untracked `src/part2/`, `tests/part2/`, root `configs/part2.yaml`, and the missing upstream Phase 2R/2B.2/2B.4 outputs or their immutable manifests. Preserve their original hashes and environment. First run unit tests serially with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, then a pipeline dry run. Do not initially launch Phase 2R, all-edge sampling, or a full pipeline on this 16 GB Mac; run heavy stages one at a time only after source and prerequisite recovery.

## Audit scripts added in `Aman_Scripts/collaboration_codex`

These are independent verification utilities written for this review. They do not modify the collaboration packet or invent replacement Part 2 science.

### `__init__.py`

Marks this audit directory as an importable Python package.

### `common.py`

Defines finding/report data models, streaming SHA-256, a strict ragged-row-aware CSV reader, JSON loading, and deterministic file enumeration.

### `file_audit.py`

Inventories all handoff files, reconciles the manifest, parses every structured artifact, detects raw-data exclusion and nonportable paths, and proves the documented production source is absent.

### `table_audit.py`

Checks row grain, edge-ID format, numeric domains, Phase 2B.4/2C counts, queue unions and disjointness, summaries, human-field blankness, and the exact 214-plus-14 set relationship.

### `scientific_audit.py`

Challenges external validity by comparing the candidate taxonomy with the paper, measuring top-rank review bias, checking the 14 unreviewed promotions, and profiling boundary concentration.

### `provenance_audit.py`

Checks assumption/method/reference registries, stale configuration, Boolean and NaN schema conventions, the Phase 2C change flag, viewer numeric types, and source-artifact hash lineage.

### `coverage_audit.py`

Reads only TIFF metadata plus saved tables/viewer geometry to detect invalid evidence support, zero-signal panels, partly covered promotions, and the mislabeled panel anomaly-score unit.

### `viewer_audit.py`

Confirms embedded/external viewer JSON equality, unique all-edge coverage, class counts, finite geometry, legend styles, and required static controls.

### `visual_audit.py`

Decodes all PNGs sequentially, checks dimensions and duplicates, reconciles panel ranks/edge IDs/indexes, and creates bounded-size contact sheets without holding the packet in memory.

### `make_contact_sheets.py`

Provides a focused CLI for regenerating the six 20-panel visual audit sheets.

### `browser_smoke.py`

Starts an ephemeral local viewer server and headless Chrome session, exercises search/toggle/zoom/reset/canvas behavior, captures two screenshots, and records console errors.

### `run_audit.py`

Orchestrates all static, tabular, provenance, scientific, coverage, viewer, and visual checks; saves inspectable evidence and exits nonzero while any blocking finding remains.

### `build_end_to_end.py`

Generates this guide from audited metadata, asserts exact 56-file description coverage, and emits one evidence paragraph for each of 120 panels.

### `report_audit.py`

Validates this generated Markdown's local links, catalog counts, required sections, current audit totals, coverage-failure IDs, and claim-language guardrails.

### `tests/__init__.py`

Marks the regression-test directory as a package.

### `tests/test_audit.py`

Runs the real packet through every audit component and locks in 43 integrity, scientific, coverage, provenance, viewer, visual, and report regressions.

## Tests actually run in this audit

- **43/43 local audit unit tests passed.** These cover inventory, non-self hashes, parser coverage, missing-source detection, Phase 2B.4/2C reconciliation, viewer equivalence, all-image decode, panel mapping, contact-sheet coverage, ragged-CSV rejection, hash determinism, chart readability, paper mismatch, sampling bias, unreviewed promotions, provenance registries, stale config, schema hazards, source lineage, and CT-support failures.
- **64 consolidated checks:** 43 passed, 19 warned, and 2 failed. The failures are retained for absent production/test source and three auto-supported candidates without valid CT support.
- **Three packaged skills validated** with the skill validator.
- **All 121 PNGs decoded**, including 120 panels at 2790 x 1655; no exact duplicates were found.
- **Viewer runtime passed 10/10 checks** in headless Chrome, including 18,468 edges, seven legend classes, search, toggle, wheel zoom, reset, screenshots, and no material console errors. A favicon 404 was recorded separately as harmless.
- **The original claimed 93-test suite was not run** because no such test or production source exists in the checkout.
- **Heavy scientific stages were not rerun** because their implementation and cumulative inputs are absent; doing so would also be an unnecessary memory/runtime risk at this stage.

## Errors and improvements, in priority order

### P0 - fix the CT valid-sample gate

Demote the three fully unsupported candidate edges to a new `coverage_blocked` state immediately. Find why edge/panel support clamps at x=767 while the source TIFF contains x indices 0 through 836, then regenerate their features from the correct axis/volume. Require a minimum valid-sample/in-bounds fraction before any missing or disconnected auto-support rule can fire. Watermark all 40 zero-signal panels as OUT OF SUPPORT and retain an explicit validity mask. Recheck the partially covered Phase 2C rank-13 promotion before accepting it.

### P0 - recover reproducibility

Recover and commit the exact source, tests, root config, lock/environment file, and required upstream outputs. Add a run manifest for every stage containing source commit/tree hash, config hash, raw-input hashes, upstream-output hashes, command, Python/package versions, seed, timestamps, and peak memory. Exclude MANIFEST.json from its own internal hash and instead publish an external checksum or signature.

Do not reuse the packaged `method_and_config/part2.yaml` as-is: it still encodes an unverified identity/unknown STL mapping, whereas later outputs depend on `perm021_signmmm`. Recover the exact effective run config and register the missing method IDs `CT-ATLAS-001`, `CT-REG-LOCAL-001`, `CT-STRAIGHTEN-001` and assumption IDs `A-CT-FEATURES-001`, `A-STL-AXIS-001-HUMAN-ANCHORED`.

### P0 - build a defensible truth/evaluation set

Blindly review all 14 Phase 2C promotions plus a stratified random sample from the remaining 200 baseline candidates, 677 review-required rows, 2,654 low-priority rows, and 14,820 present-like controls. Stratify by orientation, boundary bin, spatial region, anomaly score, and label type. Use at least two reviewers on a subset, adjudicate disagreement, and report confidence intervals, inter-rater agreement, per-class precision/recall, and calibration. The present pipeline has no recall estimate.

### P0 - align physical class definitions

Match the paper's mutually exclusive missing/disconnected definitions or clearly publish a different taxonomy. Investigate why the paper-equivalent comparison suggests roughly 918 disconnected edges while the pipeline flags only 13, and why 215 unintended-missing candidates greatly exceed the paper's approximate excess of 13. Treat this as a calibration/semantic alarm, not as a reason to force counts to match.

### P1 - challenge boundary and registration artifacts

Possible-unintended candidates are disproportionately boundary/near-boundary. Add boundary/skin-specific templates, crop-completeness flags, perturbation tests around the transform, local alignment residual thresholds, and negative controls. Report how candidate counts change under plausible registration, threshold, radius, and endpoint-exclusion perturbations.

### P1 - make review evidence easier to use

Default the viewer to defect-focused classes, add a preset for all/defects/review-required, center and zoom a searched edge, prevent a selected class from becoming invisibly hidden, link directly to its CT panel, add depth sorting or a 3D library, and optionally overlay CT/STL surfaces. A graph line alone cannot prove material loss.

### P1 - improve reporting and portability

Replace collaborator-specific absolute paths with repository-relative paths and a single configurable data root. Rename `mean_delta_mm` to `ct_anomaly_score`, normalize `LLNLDSC2026`/`LLNL-DSC-2026`, serialize booleans consistently, replace literal `nan` with null plus validity status, make viewer scores/evidence counts numeric, and rename the Phase 2C change flag to distinguish lexical changes from promotions. Redesign the class-count chart with direct labels and either a separate defect-only panel, broken axis, or log scale. Record exactly which panels were reviewed and avoid reusing rank as identity across runs.

## Simple high-level explanation

Think of the design as a list of 18,468 expected sticks. The JSON says where each stick should be. The TIFF is a 3D X-ray image that says where metal appears to be. The intended code follows each expected stick through the X-ray volume, measures whether metal continues from one end to the other, compares it with similar healthy sticks, and gives suspicious sticks to a person for review.

The packet is good at preserving the **results of that process**: tables, panels, counts, notes, and a viewer all agree with one another. What is missing is the **machine that produced them**: the Part 2 Python files and their tests. That means we can prove the package is internally intact, but we cannot yet prove the underlying detector was implemented exactly as described.

The best current answer is therefore: the original system nominated 214 edges and the 40 highest-ranked looked defect-like or ambiguous to the reviewer, but at least three lower-ranked nominees lack valid CT support because of an x-coverage bug. This is not enough to claim 214 confirmed defects. Fourteen more candidates are unreviewed, and one of those is only partly covered. Fix coverage, recover the source, review a representative sample including normal-looking controls, and then calculate real accuracy before publishing a physical defect percentage.

## Audit artifacts produced by Codex terminal 2

- [Consolidated audit summary](audit_outputs/audit_summary.md)
- [Machine-readable audit report](audit_outputs/audit_report.json)
- [Complete file inventory](audit_outputs/file_inventory.csv)
- [Complete image inventory](audit_outputs/image_inventory.csv)
- [Viewer runtime result](audit_outputs/browser/viewer_runtime_result.json)
- [Viewer default screenshot](audit_outputs/browser/viewer_runtime.png)
- [Viewer candidate-focused screenshot (also includes designed removals)](audit_outputs/browser/viewer_defects_only.png)
- [Panels 001-020 contact sheet](audit_outputs/contact_sheets/phase2c_panels_001_020.jpg)
- [Panels 021-040 contact sheet](audit_outputs/contact_sheets/phase2c_panels_021_040.jpg)
- [Panels 041-060 contact sheet](audit_outputs/contact_sheets/phase2c_panels_041_060.jpg)
- [Panels 061-080 contact sheet](audit_outputs/contact_sheets/phase2c_panels_061_080.jpg)
- [Panels 081-100 contact sheet](audit_outputs/contact_sheets/phase2c_panels_081_100.jpg)
- [Panels 101-120 contact sheet](audit_outputs/contact_sheets/phase2c_panels_101_120.jpg)

## File-by-file catalog: 56 documents, tables, configs, agents, viewer files, and figure

The following paragraphs cover every packaged file except the 120 review-panel PNGs, which have their own one-by-one catalog afterward. Hashes are from the fresh local audit.

### `AGENT_INVENTORY.md`

A directory-level index of the packaged Codex agents and skills. It explains which specialist prompt is intended for segmentation, CT review, Part 2 defect analysis, and calibration; it is routing information, not scientific evidence or executable implementation. Audit metadata: 1,771 bytes; SHA-256 `2a8e919b7930c9ba9ab9a3b657ee0afdfa0583f85b2a24747ea28d2b9499ff11`. [Open file](../../collaboration/part2_verification_handoff_20260727/AGENT_INVENTORY.md).

### `DEFECT_FINDING_PROCESS.md`

A concise description of the intended defect-finding chain, from design geometry and registered CT evidence through guarded labels, human spot checks, Phase 2C triage, and viewer export. Its wording correctly treats the outputs as candidates, but it cannot make the absent implementation reproducible. Audit metadata: 3,111 bytes; SHA-256 `ac5eda0b24b94decddc59f058529a013d00320e98eee2d5c3678b4591a2cbb50`. [Open file](../../collaboration/part2_verification_handoff_20260727/DEFECT_FINDING_PROCESS.md).

### `LABEL_DEFINITIONS.md`

The semantic contract for designed-removed, possible unintended missing, possible unintended disconnected, present-like, review-required, and low-priority uncertain states. This file is essential because several names encode evidence strength rather than physical ground truth; downstream reports must preserve those distinctions. Audit metadata: 3,633 bytes; SHA-256 `215005daa5e8157240762ea1460b4efb2a15c55c28ef2acfe94099458ba13428`. [Open file](../../collaboration/part2_verification_handoff_20260727/LABEL_DEFINITIONS.md).

### `MANIFEST.json`

The package inventory with expected paths, sizes, and SHA-256 values. All 175 non-self entries match the files on disk, but its entry for MANIFEST.json itself is stale because embedding a file's own final hash is self-referential; future packages should sign or checksum the manifest externally. Audit metadata: 37,600 bytes; SHA-256 `c7624c316ee26f41c3824162d9f8accf8971e6cc5e96e199e42b4f3eb5845652`. [Open file](../../collaboration/part2_verification_handoff_20260727/MANIFEST.json).

### `NEXT_AGENT_PROMPT.md`

A handoff prompt telling a later agent how to continue review without silently promoting candidates to truth. It provides useful operational guardrails, although collaborator-specific paths and missing source prevent literal end-to-end execution. Audit metadata: 2,169 bytes; SHA-256 `47588a393f1b49faa47771d1a1544a81992adf1c34e11e6cce1c7620ad2810ed`. [Open file](../../collaboration/part2_verification_handoff_20260727/NEXT_AGENT_PROMPT.md).

### `README_START_HERE.md`

The packet's front door. It identifies the conservative 214-candidate baseline, the provisional 228-candidate Phase 2C extension, the review queues, viewer, and documentation; this is the right first human-readable file, subject to the reproducibility warning in this audit. Audit metadata: 2,522 bytes; SHA-256 `0424496e1959d3c67faae5fbfd29b946b8fc55164560d907af05902c86889bd0`. [Open file](../../collaboration/part2_verification_handoff_20260727/README_START_HERE.md).

### `VERIFICATION_PROTOCOL.md`

The manual-review protocol and allowed label vocabulary. It requires evidence-based CT inspection and preservation of ambiguous cases; this is scientifically safer than treating the automated score as truth, but the supplied Phase 2C verification fields are still blank. Audit metadata: 2,628 bytes; SHA-256 `f97c0378e58657ca91a5eb4555b1be7f4ba5866b822fc5a829a5ea70491f647b`. [Open file](../../collaboration/part2_verification_handoff_20260727/VERIFICATION_PROTOCOL.md).

### `agent_assets/.agents/skills/nde_report_expert/SKILL.md`

Instructions for extracting volume, mask, and skeleton features and building consistent NDE visual reports. The audit used its emphasis on traceable metrics and fixed views when checking the packet's summaries and imagery; it does not implement the missing Part 2 classifier. Audit metadata: 1,809 bytes; SHA-256 `91a3d6ac5d9345591207994b359f62aaf3cf43db56a2d192e1f0139af43ccef1`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.agents/skills/nde_report_expert/SKILL.md).

### `agent_assets/.agents/skills/part2-defect-analysis/SKILL.md`

The main specialist workflow for design-aware CT defect analysis. It enforces coordinate-frame checks, welded graph topology, conservative labels, review gates, and provenance, which directly shaped this audit's separation of verified artifacts from provisional inference. Audit metadata: 7,316 bytes; SHA-256 `98a820ba5956d3e5183c47fc829d1a42f5a58bc446e39e9dfb48deb9bfad702a`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.agents/skills/part2-defect-analysis/SKILL.md).

### `agent_assets/.agents/skills/part2-defect-analysis/agents/openai.yaml`

Display and invocation metadata for the Part 2 defect-analysis skill. It tells an agent when to select the skill but contains no numerical method or trained model. Audit metadata: 349 bytes; SHA-256 `b25b501728ebd71bdc34d8c85cd3383fe968c7621a71dc54d9af23f4fdd27b29`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.agents/skills/part2-defect-analysis/agents/openai.yaml).

### `agent_assets/.agents/skills/threshold-optimizer/SKILL.md`

Guidance for threshold selection using structural metrics rather than voxel accuracy alone. It is relevant to Task 1 and to sensitivity analysis, while Part 2's final labels rely on a broader feature pipeline documented elsewhere. Audit metadata: 6,562 bytes; SHA-256 `bbcdab580862461f8824ddfe782426fe8904e88b2d016751706d9abab0a15c62`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.agents/skills/threshold-optimizer/SKILL.md).

### `agent_assets/.agents/skills/threshold-optimizer/agents/openai.yaml`

Display and invocation metadata for the threshold-optimizer skill. It is configuration for agent routing, not a threshold result or test fixture. Audit metadata: 256 bytes; SHA-256 `c69c540bcf9a6f20fd2f4d12e79f26e2849018a8aea75c28b187e05684908082`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.agents/skills/threshold-optimizer/agents/openai.yaml).

### `agent_assets/.codex/agents/ct_visual_review_agent.toml`

A specialist-agent prompt for inspecting CT review panels conservatively, checking multiple projections and recording uncertainty. It supports human-in-the-loop review but cannot substitute for the absent raw-panel generation code. Audit metadata: 2,696 bytes; SHA-256 `0e2cbc8edd99b37a9d2a9f7524a5a627a7345bdd4da3cce27ec80fd7bad474b8`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.codex/agents/ct_visual_review_agent.toml).

### `agent_assets/.codex/agents/part2_defect_analysis_agent.toml`

The broad Part 2 analysis-agent prompt. It coordinates graph, design, CT, calibration, and reporting concerns and repeatedly warns against overclaiming; its claims about script behavior remain documentation-only here. Audit metadata: 6,133 bytes; SHA-256 `53eabd148e7a2eb7f3154257e1ab0ffcc16b9164c29d1b263ed8f9f6daba7415`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.codex/agents/part2_defect_analysis_agent.toml).

### `agent_assets/.codex/agents/phase2b_ct_calibration_agent.toml`

A focused agent prompt for CT feature calibration and gate evaluation. It is useful for assigning a bounded calibration task, but it contains no executable sampler or learned parameters by itself. Audit metadata: 3,735 bytes; SHA-256 `4025bddbc68a853e66bba1fff57e641d17a8739fe365aed8b6c855d266abbaed`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.codex/agents/phase2b_ct_calibration_agent.toml).

### `agent_assets/.codex/agents/segmentation_agent.toml`

A specialist prompt for segmentation work and structural validation. It belongs to the broader project toolchain and is not evidence that the Part 2 TIFF was re-segmented in this packet. Audit metadata: 5,205 bytes; SHA-256 `621222e0075c7add0a63ce75f34fbf1efb8f58264289630faad1bcf826c30d5d`. [Open file](../../collaboration/part2_verification_handoff_20260727/agent_assets/.codex/agents/segmentation_agent.toml).

### `final_report_baseline/agentic_workflow.md`

A narrative of how agents, deterministic scripts, and manual review were intended to cooperate. It is valuable as an orchestration design, but the claimed commands cannot be rerun until the original untracked source, tests, configs, and upstream outputs are recovered. Audit metadata: 3,355 bytes; SHA-256 `854f3cdc9a6d14c23a3ebfa994c0e6911354187380e1389e38d91e5203ba0dd0`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/agentic_workflow.md).

### `final_report_baseline/figures/automated_review_label_counts.png`

The only non-panel PNG, a bar chart of automated-review class counts. It decodes correctly at 2160 x 1170, but the 14,820 present-like bar is more than 1,000 times the smallest headline defect class, making the small categories unreadable on one linear scale. Audit metadata: 130,690 bytes; SHA-256 `a6f21d6291d8addcb8382e2ebcaf96fe8f5d5cd603b5ee70b4b7329a243d06f0`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/figures/automated_review_label_counts.png).

### `final_report_baseline/final_ct_defect_report.md`

The conservative written result for Phase 2B.4. It reports 202 possible unintended missing plus 12 possible unintended disconnected candidates (214 combined, 1.158761% of 18,468 expected struts), alongside 89 designed-removed and 14,820 present-like edges; its status explicitly says this is a spot-check-supported automated estimate, not full ground truth. Audit metadata: 3,762 bytes; SHA-256 `60fe77db319e3ee9038b06a68f48d6a28931dcf3dab47f75ffa6c22b597ee59a`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/final_ct_defect_report.md).

### `final_report_baseline/final_ct_defect_summary.json`

The machine-readable counterpart to the baseline report. Its counts and percentages reconcile exactly with the baseline tables, and it records the 40 top-ranked human spot checks: 29 absent, 7 disconnected, 4 ambiguous, and no clearly present-like contradiction. Audit metadata: 2,182 bytes; SHA-256 `4a326dd8b96f4ee30395cdb99ed85e0967c17ef7665e0424b080332758c95ba3`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/final_ct_defect_summary.json).

### `final_report_baseline/run_manifest.json`

A provenance snapshot for baseline packaging. It records hashes and Git state, and it supplies the decisive evidence that src/part2 and tests were untracked on the originating machine; it also contains machine-specific paths and therefore is evidence, not a portable run recipe. Audit metadata: 3,358 bytes; SHA-256 `5c0ffe5804a4eb1c5a65931e07d5240a7eef2d23a577996d7afc0a1cb1bbcfca`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/run_manifest.json).

### `final_report_baseline/tables/auto_supported_unintended_candidates.csv`

The 214-row Phase 2B.4 candidate list: 202 possible missing and 12 possible disconnected. Row grain and edge IDs are internally consistent, but only the top 40 were manually spot-checked and that non-random sample cannot establish recall or whole-list precision. Audit metadata: 114,366 bytes; SHA-256 `13adfe5339816cf6dd2968cb5941f0452edc87c6519f14aea318a3753e08b334`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/auto_supported_unintended_candidates.csv).

### `final_report_baseline/tables/headline_numbers.csv`

A compact table of baseline counts, denominators, and draft percentages used by the report. The arithmetic reconciles with the JSON summary and full candidate table. Audit metadata: 324 bytes; SHA-256 `1a0b756b63ad236df52c377e578199d546fa35dfb273d7680a6194050899df51`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/headline_numbers.csv).

### `final_report_baseline/tables/human_spotcheck_label_counts.csv`

The aggregate of the 40 supplied human labels. It correctly preserves absent, disconnected, and ambiguous as separate outcomes; because the sample is ranks 1 through 40 only and lacks present-like controls, it is supportive evidence rather than a validation study. Audit metadata: 77 bytes; SHA-256 `999ae9440c4519e8a18d7acbf917db9b99bf3c51976a0cc8a9735ffb78a2b706`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/human_spotcheck_label_counts.csv).

### `final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv`

The row-level record of the top-40 baseline spot check, including normalized label, notes, and source. These edge IDs are not the same set as ranks 1 through 40 in the later Phase 2C top-120 panel packet, so the labels must never be joined by rank alone. Audit metadata: 4,773 bytes; SHA-256 `c4926fbe9640ce72384db2e374d27d78bcf3ebec2eb8e3665c7c4b9e6946d45f`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv).

### `final_report_baseline/tables/manual_review_queue.csv`

The 920 Phase 2B.4 blocked cases retained for review. It represents uncertainty rather than confirmed defects and is a key safeguard against forcing mixed or unstable evidence into a binary label. Audit metadata: 475,506 bytes; SHA-256 `8f2b5efb879351b6a4e52a3aae79d22e9c105c1880a7f1e27066c5e7b697e06d`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/manual_review_queue.csv).

### `final_report_baseline/tables/spotcheck_panel_index.csv`

The lookup between the baseline top-40 reviewed candidates and their original panel metadata. It supports provenance for the recorded human labels but the corresponding baseline panel PNGs are not included in this handoff. Audit metadata: 27,478 bytes; SHA-256 `b7c5bfd53ceecc53ac86e86571c964ecb36db89c89c4a55a0d4910c3b094e100`. [Open file](../../collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/spotcheck_panel_index.csv).

### `method_and_config/AGENTS.md`

Repository-level operating rules copied into the packet. It documents scope, terminology, and scientific caution expected of agents; it should guide work but does not provide missing runtime dependencies or source. Audit metadata: 4,270 bytes; SHA-256 `ef1278c4fe4ba7a1e406ed359d943bf965887787c26e26c22dceeff4554c72ab`. [Open file](../../collaboration/part2_verification_handoff_20260727/method_and_config/AGENTS.md).

### `method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md`

The 1,078-line method ledger linking method IDs, assumptions, physics, literature, thresholds, and phase decisions. It is the best technical rationale in the packet and was read in full, but several entries describe historical execution that cannot be independently rerun from this checkout. Audit metadata: 35,166 bytes; SHA-256 `8216e5175922b92514c4f13b22cdde887632ba7d20e6ce5398c3edc0e163b185`. [Open file](../../collaboration/part2_verification_handoff_20260727/method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md).

### `method_and_config/part2.yaml`

An early snapshot of Part 2 paths, stage settings, thresholds, and output conventions. It is useful for reconstructing intent, but it still says specimen mapping is UNVERIFIED, STL axis mapping is null, and the Phase 1 identity mapping is unverified, whereas later artifacts say the anchor gate selected perm021_signmmm. It is therefore stale planning context, not a ready-to-rerun Phase 2C configuration. Audit metadata: 6,906 bytes; SHA-256 `2116443802b955c5357173211268028d5c2cf558295729e04daa647d52a70567`. [Open file](../../collaboration/part2_verification_handoff_20260727/method_and_config/part2.yaml).

### `method_and_config/requirements.txt`

A dependency snapshot from the originating environment. The current DSC environment contains the listed packages plus YAML support; optional VTK is absent, and the original run used Python 3.9 while DSC currently uses Python 3.11, so recovered source would still need compatibility testing. Audit metadata: 53 bytes; SHA-256 `83ef31db0d539b302812f65a5cc48bb789d96df68944fdaffa6e529037eb660e`. [Open file](../../collaboration/part2_verification_handoff_20260727/method_and_config/requirements.txt).

### `method_and_config/scientific_assumptions.yaml`

A structured registry of coordinate, segmentation, design, CT-feature, calibration, reporting, and triage assumptions. It is especially useful for identifying what must be challenged experimentally rather than silently accepted. Audit metadata: 16,582 bytes; SHA-256 `0c43946b2555fbd1ee965af09298d1c071179ec3632a1c7e6d2b497ab4932ffc`. [Open file](../../collaboration/part2_verification_handoff_20260727/method_and_config/scientific_assumptions.yaml).

### `notes_snapshot/00-big-picture.md`

A high-level map of the entire challenge, separating completed MCP tasks from the Part 2 research pipeline. It provides context and emphasizes that missing-strut analysis is design-aware rather than simple connected-component counting. Audit metadata: 21,670 bytes; SHA-256 `74490a218a7c70581087453aeab54609cdaac76d0379039077afac1613e13250`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/00-big-picture.md).

### `notes_snapshot/01-how-to-run-code.md`

A 2,465-line chronological command journal covering Tasks 1 through 7 and all Part 2 phases. It is detailed enough to reconstruct intended CLI interfaces, but many commands reference absent Python modules, missing upstream output directories, and the collaborator's absolute paths. Audit metadata: 61,933 bytes; SHA-256 `a0ca1bb2255c238fee8b205e0a29627bade7a9fbe9d2cd2b025d393580fe2b38`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/01-how-to-run-code.md).

### `notes_snapshot/05-task-log-and-experiments.md`

A 2,971-line experiment log recording decisions, failures, test-count growth, timings, memory use, and status changes. It is valuable provenance: notably, Phase 2A failed to separate groups and Phase 2R was downgraded from verified to provisional after sparse transform coverage was recognized. Audit metadata: 100,767 bytes; SHA-256 `42ce30d7c80343c62820074cdc8a9136ec501ffeeea2f74aa6441108c3564b0e`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/05-task-log-and-experiments.md).

### `notes_snapshot/21-part2-phase2b3-guarded-labels.md`

The focused record for converting complete CT features into guarded observations. It documents the 420 possible-missing, 58 possible-disconnected, 3,076 uncertain, 14,820 present-like, and 3,573 review-required Phase 2B.3 state before stricter automation. Audit metadata: 8,445 bytes; SHA-256 `373287bbea1272f18c93e18fe0518e55b85de5b8c8184ca281944aea492435ae`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/21-part2-phase2b3-guarded-labels.md).

### `notes_snapshot/22-part2-phase2b4-automated-review.md`

The focused record for the stricter Phase 2B.4 rules that produced the conservative 214-candidate baseline, 920 blocked rows, and 2,425 low-priority uncertain rows. It explains why strong evidence flags and stability margins were required. Audit metadata: 7,148 bytes; SHA-256 `a52dd33eaddd2fd2f199494ac2b58e25f9da6c0985206c3713fcc7e8c86e4acf`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/22-part2-phase2b4-automated-review.md).

### `notes_snapshot/23-part2-final-report-and-agentic-system.md`

The focused record for final baseline packaging, top-40 human labels, and the role of agents. It correctly distinguishes deterministic evidence generation from LLM orchestration and human judgment. Audit metadata: 5,115 bytes; SHA-256 `f3544e150d14b412b98ef239fcc40a2aeac6c14b99d1da9988bc5ddb34e9067c`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/23-part2-final-report-and-agentic-system.md).

### `notes_snapshot/24-part2-phase2c-automatic-triage-and-viewer.md`

The focused record for the second-pass queue triage, the 14 new promotions, 677 remaining review-required rows, 2,654 low-priority cases, and the all-edge viewer. The new promotions remain provisional because their human verification fields are blank. Audit metadata: 9,273 bytes; SHA-256 `496c6bdc76ad51e553ea396ede14704123fc795391a661b750f6612758ba78cf`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/24-part2-phase2c-automatic-triage-and-viewer.md).

### `notes_snapshot/project-notebook.md`

A short notebook/index that directs readers to the larger logs and records the packet's overall state. It is useful orientation, not a substitute for the detailed journals or executable code. Audit metadata: 12,703 bytes; SHA-256 `2856e7b73b1ad29f34478b5bfa20436da08a2e5bbbcfcbc353f809a5e8e64141`. [Open file](../../collaboration/part2_verification_handoff_20260727/notes_snapshot/project-notebook.md).

### `review_panels_phase2c_top120/ct_edge_panel_summary.csv`

The 120-row panel-generation summary with rank, edge ID, design state, crop shape, display window, and along-edge intensity statistics. It maps exactly to the 120 PNG filenames and JSON summary, but the field mean_delta_mm is misleading: it equals the dimensionless CT anomaly score in all 120 rows. Audit metadata: 34,918 bytes; SHA-256 `da450abb4bbec2b879c9004b62367bb89f81a428a632469d1675a0ecba5111c4`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/ct_edge_panel_summary.csv).

### `review_panels_phase2c_top120/ct_edge_panel_summary.json`

The JSON form of the top-120 panel summary. It preserves the same ranking and quantitative panel metadata for programmatic consumers and reconciles with the CSV/PNG set, including the same incorrectly unit-labeled mean_delta_mm field. Audit metadata: 127,220 bytes; SHA-256 `a587a80ecb9bf4cc15ec9c79ce543996e9fd2ad5eeb50e4f1baeca20568abd7e`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/ct_edge_panel_summary.json).

### `review_tables/human_verification_template.csv`

The 3,345-row blank review workbook covering the 14 Phase 2C promotions, 677 remaining review-required rows, and 2,654 low-priority audit rows. All human fields are blank, which is correct for a template but proves Phase 2C has not yet been verified. Audit metadata: 1,500,407 bytes; SHA-256 `b20c590e7aa00808a8f2bf65164ba27f60f86eb7d725fc5345ff480762ed84d1`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/human_verification_template.csv).

### `review_tables/low_priority_uncertain_2654_audit_table.csv`

The 2,654 cases demoted to low priority by Phase 2C. These are not asserted present and not counted as defects; a probability sample should still be reviewed to measure false negatives. Audit metadata: 1,188,120 bytes; SHA-256 `f6262bd0d596a13fc140f48a74d568e0f366a9c84aab6ab1fa9b3230bee0f132`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/low_priority_uncertain_2654_audit_table.csv).

### `review_tables/manual_queue_triage_report.md`

The written Phase 2C triage report. It explains the second-pass rules, 14 promotions, remaining queue, and limitations, and should be read together with the structured summary rather than as ground truth. Audit metadata: 3,406 bytes; SHA-256 `b054bf1e9a8d01c2647cbe62b8742231820aecad91bc4a9e756eceb0c70f1e6c`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/manual_queue_triage_report.md).

### `review_tables/newly_promoted_14_to_verify.csv`

The first-priority verification list for the 14 cases promoted beyond the 214 baseline. Every corresponding human-review field is blank, so these rows cannot yet justify replacing the 214 baseline with 228. Audit metadata: 7,224 bytes; SHA-256 `669108c2373318cdb7b7fb78c00658ac52f1c5e885157ae187a4ff736e220f4a`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/newly_promoted_14_to_verify.csv).

### `review_tables/phase2c_auto_supported_unintended_candidates.csv`

The combined 228 Phase 2C candidate rows: the baseline 214 plus exactly 14 promotions. Internal set reconciliation passes, but the file is a candidate queue, not a manually confirmed defect list. Audit metadata: 89,018 bytes; SHA-256 `4c470c20948b0a76f8b93f7cd13d9601182f0550b93d4260c88f85c97f757f83`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/phase2c_auto_supported_unintended_candidates.csv).

### `review_tables/phase2c_labels.csv`

The all-edge Phase 2C table with one unique record for each of 18,468 expected edges and extensive inherited features, evidence flags, prior labels, and current triage state. It is the central late-stage analytical artifact and the source for viewer classes. Audit metadata: 46,814,255 bytes; SHA-256 `a852062f89ebd90023966cf07449468704e661d4877842eca0a1ec154e58cb39`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/phase2c_labels.csv).

### `review_tables/phase2c_remaining_review_queue.csv`

The 677 cases still requiring review after Phase 2C, including five design-intent conflicts. Keeping these unresolved is appropriate; reporting them as defects or present would overstate the evidence. Audit metadata: 252,332 bytes; SHA-256 `1fc3ff05c9775e1291443ca3da4e5ad023f7460a882d897d141ee1e6b36aaf0f`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/phase2c_remaining_review_queue.csv).

### `review_tables/phase2c_summary.json`

The machine-readable Phase 2C counts, settings, thresholds, and output paths. Its seven class counts sum exactly to 18,468 and its 228-candidate set reconciles to 214 prior candidates plus 14 promotions. Audit metadata: 3,019 bytes; SHA-256 `9b419699eb43b509302be926cde820cdaab5fe20dd50b5bb4cd89e5ef10a56cf`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/phase2c_summary.json).

### `review_tables/remaining_review_required_677_to_verify.csv`

A verification-focused copy/order of the same 677 unresolved rows. It is designed for human review and is not an additional population beyond phase2c_remaining_review_queue.csv. Audit metadata: 282,700 bytes; SHA-256 `a0f007ecf4c4e90e6434ed638abf50ede06d3b5bdaea6a34ad7927e0d49a437f`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/remaining_review_required_677_to_verify.csv).

### `review_tables/review_panel_index.csv`

The detailed top-120 review index with graph endpoints, midpoint, exact TIFF Z slice/crop limits, anomaly score, and reason. It is the bridge between an edge ID and the CT evidence panel and agrees exactly with panel filenames and summaries. Audit metadata: 43,652 bytes; SHA-256 `522dbf1294fafe2f23f389b954d30395b8d4f6f8057316f8ba80b578d0693e90`. [Open file](../../collaboration/part2_verification_handoff_20260727/review_tables/review_panel_index.csv).

### `viewer/index.html`

A self-contained canvas-based graph viewer with embedded data, search, rotation, zoom, class toggles, reset, and click selection. Runtime smoke testing passed all 10 checks; it visualizes expected graph edges, not the CT surface, and default uncertain layers create substantial clutter. Audit metadata: 7,607,196 bytes; SHA-256 `201b57e7579f236ac0914f13b2abb40d04d1453236dee715a6c3dc168511ef90`. [Open file](../../collaboration/part2_verification_handoff_20260727/viewer/index.html).

### `viewer/legend.json`

The seven-class legend and style mapping used by the viewer. Every edge style in viewer_data.json matches this mapping. Audit metadata: 762 bytes; SHA-256 `11f630c3050951fcce97f7434ce1aaa7ccf2e77212329d4df69d12e489c55acc`. [Open file](../../collaboration/part2_verification_handoff_20260727/viewer/legend.json).

### `viewer/run_manifest.json`

Viewer export provenance and input hashes. Its recorded Phase 2C label hash matches the packaged table, while the canonical graph input it cites is not included and therefore cannot be independently rehashed here. Audit metadata: 1,541 bytes; SHA-256 `7a0d1fdeb83a48d41c81dda71fee9e24c31591b85685248c31f39d2f04ac86c9`. [Open file](../../collaboration/part2_verification_handoff_20260727/viewer/run_manifest.json).

### `viewer/viewer_data.json`

The external viewer payload containing 18,468 unique graph edges, endpoints, current class, color, width, opacity, and metadata. It matches the JSON embedded in index.html exactly, and all endpoints are finite and lie within the recorded bounds. Audit metadata: 10,962,441 bytes; SHA-256 `9bbf35a520c4865bec525651e4f55d427a836744d7658240a4e4ea93fc4f37b0`. [Open file](../../collaboration/part2_verification_handoff_20260727/viewer/viewer_data.json).

## File-by-file catalog: all 120 CT review panels

Every panel was decoded and visually sampled through six contact sheets. No panel is silently assigned a new human label here. The quantitative metadata below identify exactly what each file represents and where its CT crop lies.

### Panel 001: `rank_001_E_N001012_N002152_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001012_N002152` (source strut `3781`), ranked 1 with recorded state **possible unintended missing**, CT anomaly score `5.25`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 73, 58]` in array `[z,y,x]` order, centered near Z slice `123`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_001_E_N001012_N002152_ct_panel.png).

### Panel 002: `rank_002_E_N001010_N001021_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001010_N001021` (source strut `1772`), ranked 2 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 34, 97]` in array `[z,y,x]` order, centered near Z slice `44`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_002_E_N001010_N001021_ct_panel.png).

### Panel 003: `rank_003_E_N001012_N001021_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001012_N001021` (source strut `1774`), ranked 3 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[61, 34, 98]` in array `[z,y,x]` order, centered near Z slice `84`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_003_E_N001012_N001021_ct_panel.png).

### Panel 004: `rank_004_E_N001015_N001035_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001015_N001035` (source strut `1802`), ranked 4 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[61, 34, 98]` in array `[z,y,x]` order, centered near Z slice `84`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_004_E_N001015_N001035_ct_panel.png).

### Panel 005: `rank_005_E_N001015_N002155_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001015_N002155` (source strut `3788`), ranked 5 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[61, 34, 97]` in array `[z,y,x]` order, centered near Z slice `123`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_005_E_N001015_N002155_ct_panel.png).

### Panel 006: `rank_006_E_N001024_N001035_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001024_N001035` (source strut `1800`), ranked 6 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 34, 97]` in array `[z,y,x]` order, centered near Z slice `44`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_006_E_N001024_N001035_ct_panel.png).

### Panel 007: `rank_007_E_N001029_N001049_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001029_N001049` (source strut `1830`), ranked 7 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[61, 34, 98]` in array `[z,y,x]` order, centered near Z slice `84`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_007_E_N001029_N001049_ct_panel.png).

### Panel 008: `rank_008_E_N001029_N002169_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001029_N002169` (source strut `3816`), ranked 8 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 34, 97]` in array `[z,y,x]` order, centered near Z slice `123`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_008_E_N001029_N002169_ct_panel.png).

### Panel 009: `rank_009_E_N001038_N001049_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001038_N001049` (source strut `1828`), ranked 9 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 35, 97]` in array `[z,y,x]` order, centered near Z slice `44`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_009_E_N001038_N001049_ct_panel.png).

### Panel 010: `rank_010_E_N001043_N002183_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001043_N002183` (source strut `3844`), ranked 10 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 35, 97]` in array `[z,y,x]` order, centered near Z slice `123`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_010_E_N001043_N002183_ct_panel.png).

### Panel 011: `rank_011_E_N002146_N002155_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002146_N002155` (source strut `3790`), ranked 11 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[62, 33, 98]` in array `[z,y,x]` order, centered near Z slice `163`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_011_E_N002146_N002155_ct_panel.png).

### Panel 012: `rank_012_E_N002149_N002169_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002149_N002169` (source strut `3818`), ranked 12 with recorded state **possible unintended missing**, CT anomaly score `3.79444`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[61, 34, 98]` in array `[z,y,x]` order, centered near Z slice `163`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_012_E_N002149_N002169_ct_panel.png).

### Panel 013: `rank_013_E_N001379_N001506_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001379_N001506` (source strut `4665`), ranked 13 with recorded state **possible unintended missing**, CT anomaly score `3.6`, and review reason `second_pass_zero_material_body_despite_bounded_instability`. The TIFF crop is `[22, 98, 65]` in array `[z,y,x]` order, centered near Z slice `184`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_013_E_N001379_N001506_ct_panel.png).

### Panel 014: `rank_014_E_N000361_N000363_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000361_N000363` (source strut `625`), ranked 14 with recorded state **possible unintended disconnected**, CT anomaly score `3.43333`, and review reason `second_pass_long_gap_and_broken_bridge_despite_bounded_instability`. The TIFF crop is `[22, 98, 98]` in array `[z,y,x]` order, centered near Z slice `66`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_014_E_N000361_N000363_ct_panel.png).

### Panel 015: `rank_015_E_N001385_N001495_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001385_N001495` (source strut `2667`), ranked 15 with recorded state **phase2c still review required**, CT anomaly score `3.68333`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[23, 97, 97]` in array `[z,y,x]` order, centered near Z slice `145`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_015_E_N001385_N001495_ct_panel.png).

### Panel 016: `rank_016_E_N008313_N008315_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008313_N008315` (source strut `14765`), ranked 16 with recorded state **phase2c still review required**, CT anomaly score `3.62083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 65]` in array `[z,y,x]` order, centered near Z slice `619`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_016_E_N008313_N008315_ct_panel.png).

### Panel 017: `rank_017_E_N000357_N000372_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000357_N000372` (source strut `2651`), ranked 17 with recorded state **phase2c still review required**, CT anomaly score `3.54792`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 97]` in array `[z,y,x]` order, centered near Z slice `105`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_017_E_N000357_N000372_ct_panel.png).

### Panel 018: `rank_018_E_N002643_N002645_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002643_N002645` (source strut `4685`), ranked 18 with recorded state **phase2c still review required**, CT anomaly score `3.54792`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 65]` in array `[z,y,x]` order, centered near Z slice `224`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_018_E_N002643_N002645_ct_panel.png).

### Panel 019: `rank_019_E_N000245_N000372_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000245_N000372` (source strut `2649`), ranked 19 with recorded state **phase2c still review required**, CT anomaly score `3.5375`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 65]` in array `[z,y,x]` order, centered near Z slice `106`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_019_E_N000245_N000372_ct_panel.png).

### Panel 020: `rank_020_E_N000375_N000377_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000375_N000377` (source strut `653`), ranked 20 with recorded state **phase2c still review required**, CT anomaly score `3.5375`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 97, 65]` in array `[z,y,x]` order, centered near Z slice `66`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_020_E_N000375_N000377_ct_panel.png).

### Panel 021: `rank_021_E_N007049_N007176_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007049_N007176` (source strut `14745`), ranked 21 with recorded state **phase2c still review required**, CT anomaly score `3.5375`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 97, 65]` in array `[z,y,x]` order, centered near Z slice `579`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_021_E_N007049_N007176_ct_panel.png).

### Panel 022: `rank_022_E_N000245_N000251_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000245_N000251` (source strut `647`), ranked 22 with recorded state **phase2c still review required**, CT anomaly score `3.52808`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 58, 65]` in array `[z,y,x]` order, centered near Z slice `86`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_022_E_N000245_N000251_ct_panel.png).

### Panel 023: `rank_023_E_N001509_N001511_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001509_N001511` (source strut `2669`), ranked 23 with recorded state **phase2c still review required**, CT anomaly score `3.52708`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 65]` in array `[z,y,x]` order, centered near Z slice `145`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_023_E_N001509_N001511_ct_panel.png).

### Panel 024: `rank_024_E_N000240_N000375_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000240_N000375` (source strut `640`), ranked 24 with recorded state **phase2c still review required**, CT anomaly score `3.51667`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `46`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_024_E_N000240_N000375_ct_panel.png).

### Panel 025: `rank_025_E_N003773_N003777_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003773_N003777` (source strut `6691`), ranked 25 with recorded state **phase2c still review required**, CT anomaly score `3.50625`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 26]` in array `[z,y,x]` order, centered near Z slice `323`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_025_E_N003773_N003777_ct_panel.png).

### Panel 026: `rank_026_E_N003647_N003651_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003647_N003651` (source strut `6471`), ranked 26 with recorded state **phase2c still review required**, CT anomaly score `3.49583`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `323`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_026_E_N003647_N003651_ct_panel.png).

### Panel 027: `rank_027_E_N004907_N004911_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004907_N004911` (source strut `8707`), ranked 27 with recorded state **phase2c still review required**, CT anomaly score `3.49583`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 26]` in array `[z,y,x]` order, centered near Z slice `402`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_027_E_N004907_N004911_ct_panel.png).

### Panel 028: `rank_028_E_N000119_N001383_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000119_N001383` (source strut `2436`), ranked 28 with recorded state **phase2c still review required**, CT anomaly score `3.46458`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 26]` in array `[z,y,x]` order, centered near Z slice `125`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_028_E_N000119_N001383_ct_panel.png).

### Panel 029: `rank_029_E_N000245_N000249_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000245_N000249` (source strut `423`), ranked 29 with recorded state **phase2c still review required**, CT anomaly score `3.46458`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 26]` in array `[z,y,x]` order, centered near Z slice `86`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_029_E_N000245_N000249_ct_panel.png).

### Panel 030: `rank_030_E_N002640_N003777_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002640_N003777` (source strut `6700`), ranked 30 with recorded state **phase2c still review required**, CT anomaly score `3.45764`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 58, 65]` in array `[z,y,x]` order, centered near Z slice `283`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_030_E_N002640_N003777_ct_panel.png).

### Panel 031: `rank_031_E_N000249_N000251_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000249_N000251` (source strut `433`), ranked 31 with recorded state **phase2c still review required**, CT anomaly score `3.45417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 97, 65]` in array `[z,y,x]` order, centered near Z slice `66`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_031_E_N000249_N000251_ct_panel.png).

### Panel 032: `rank_032_E_N001379_N002643_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001379_N002643` (source strut `4672`), ranked 32 with recorded state **phase2c still review required**, CT anomaly score `3.45417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `204`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_032_E_N001379_N002643_ct_panel.png).

### Panel 033: `rank_033_E_N001505_N001511_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001505_N001511` (source strut `2883`), ranked 33 with recorded state **phase2c still review required**, CT anomaly score `3.4485`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 59, 65]` in array `[z,y,x]` order, centered near Z slice `165`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_033_E_N001505_N001511_ct_panel.png).

### Panel 034: `rank_034_E_N000361_N000372_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000361_N000372` (source strut `648`), ranked 34 with recorded state **phase2c still review required**, CT anomaly score `3.44602`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 58, 97]` in array `[z,y,x]` order, centered near Z slice `86`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_034_E_N000361_N000372_ct_panel.png).

### Panel 035: `rank_035_E_N000372_N001509_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000372_N001509` (source strut `2668`), ranked 35 with recorded state **phase2c still review required**, CT anomaly score `3.4356`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 58, 65]` in array `[z,y,x]` order, centered near Z slice `125`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_035_E_N000372_N001509_ct_panel.png).

### Panel 036: `rank_036_E_N008813_N010077_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008813_N010077` (source strut `18156`), ranked 36 with recorded state **phase2c still review required**, CT anomaly score `3.42708`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `677`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_036_E_N008813_N010077_ct_panel.png).

### Panel 037: `rank_037_E_N002639_N002643_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002639_N002643` (source strut `4675`), ranked 37 with recorded state **phase2c still review required**, CT anomaly score `3.42292`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 26]` in array `[z,y,x]` order, centered near Z slice `244`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_037_E_N002639_N002643_ct_panel.png).

### Panel 038: `rank_038_E_N008813_N008817_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008813_N008817` (source strut `15635`), ranked 38 with recorded state **phase2c still review required**, CT anomaly score `3.41667`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `638`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_038_E_N008813_N008817_ct_panel.png).

### Panel 039: `rank_039_E_N005789_N007053_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005789_N007053` (source strut `12516`), ranked 39 with recorded state **phase2c still review required**, CT anomaly score `3.40208`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 26]` in array `[z,y,x]` order, centered near Z slice `520`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_039_E_N005789_N007053_ct_panel.png).

### Panel 040: `rank_040_E_N008057_N009321_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008057_N009321` (source strut `16620`), ranked 40 with recorded state **phase2c still review required**, CT anomaly score `3.40208`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 26]` in array `[z,y,x]` order, centered near Z slice `678`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_040_E_N008057_N009321_ct_panel.png).

### Panel 041: `rank_041_E_N007553_N008817_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007553_N008817` (source strut `15632`), ranked 41 with recorded state **phase2c still review required**, CT anomaly score `3.39583`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `598`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_041_E_N007553_N008817_ct_panel.png).

### Panel 042: `rank_042_E_N008687_N009951_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008687_N009951` (source strut `17900`), ranked 42 with recorded state **phase2c still review required**, CT anomaly score `3.375`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `677`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_042_E_N008687_N009951_ct_panel.png).

### Panel 043: `rank_043_E_N009191_N009321_ct_panel.png`

This is the Phase 2C review panel for edge `E_N009191_N009321` (source strut `16622`), ranked 43 with recorded state **phase2c still review required**, CT anomaly score `3.36042`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 27]` in array `[z,y,x]` order, centered near Z slice `718`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_043_E_N009191_N009321_ct_panel.png).

### Panel 044: `rank_044_E_N003144_N004283_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003144_N004283` (source strut `7587`), ranked 44 with recorded state **phase2c still review required**, CT anomaly score `3.35417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 58]` in array `[z,y,x]` order, centered near Z slice `282`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_044_E_N003144_N004283_ct_panel.png).

### Panel 045: `rank_045_E_N000245_N001509_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000245_N001509` (source strut `2656`), ranked 45 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `125`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_045_E_N000245_N001509_ct_panel.png).

### Panel 046: `rank_046_E_N000371_N000375_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000371_N000375` (source strut `643`), ranked 46 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 25]` in array `[z,y,x]` order, centered near Z slice `86`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_046_E_N000371_N000375_ct_panel.png).

### Panel 047: `rank_047_E_N001052_N001063_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001052_N001063` (source strut `1856`), ranked 47 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 35, 97]` in array `[z,y,x]` order, centered near Z slice `44`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_047_E_N001052_N001063_ct_panel.png).

### Panel 048: `rank_048_E_N001052_N001077_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001052_N001077` (source strut `1885`), ranked 48 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 35, 98]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_048_E_N001052_N001077_ct_panel.png).

### Panel 049: `rank_049_E_N001066_N001077_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001066_N001077` (source strut `1884`), ranked 49 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 36, 97]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_049_E_N001066_N001077_ct_panel.png).

### Panel 050: `rank_050_E_N001066_N001091_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001066_N001091` (source strut `1913`), ranked 50 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 36, 98]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_050_E_N001066_N001091_ct_panel.png).

### Panel 051: `rank_051_E_N001071_N002225_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001071_N002225` (source strut `3929`), ranked 51 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 35, 98]` in array `[z,y,x]` order, centered near Z slice `124`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_051_E_N001071_N002225_ct_panel.png).

### Panel 052: `rank_052_E_N001080_N001091_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001080_N001091` (source strut `1912`), ranked 52 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 36, 97]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_052_E_N001080_N001091_ct_panel.png).

### Panel 053: `rank_053_E_N001085_N001091_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001085_N001091` (source strut `1915`), ranked 53 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 36, 97]` in array `[z,y,x]` order, centered near Z slice `84`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_053_E_N001085_N001091_ct_panel.png).

### Panel 054: `rank_054_E_N001505_N001509_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001505_N001509` (source strut `2659`), ranked 54 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 25]` in array `[z,y,x]` order, centered near Z slice `165`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_054_E_N001505_N001509_ct_panel.png).

### Panel 055: `rank_055_E_N002191_N003345_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002191_N003345` (source strut `5917`), ranked 55 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 35, 98]` in array `[z,y,x]` order, centered near Z slice `202`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_055_E_N002191_N003345_ct_panel.png).

### Panel 056: `rank_056_E_N002205_N002211_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002205_N002211` (source strut `3903`), ranked 56 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 35, 97]` in array `[z,y,x]` order, centered near Z slice `163`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_056_E_N002205_N002211_ct_panel.png).

### Panel 057: `rank_057_E_N002219_N002225_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002219_N002225` (source strut `3931`), ranked 57 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 36, 97]` in array `[z,y,x]` order, centered near Z slice `163`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_057_E_N002219_N002225_ct_panel.png).

### Panel 058: `rank_058_E_N003339_N004493_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003339_N004493` (source strut `7961`), ranked 58 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 35, 98]` in array `[z,y,x]` order, centered near Z slice `282`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_058_E_N003339_N004493_ct_panel.png).

### Panel 059: `rank_059_E_N003353_N003359_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003353_N003359` (source strut `5947`), ranked 59 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 35, 97]` in array `[z,y,x]` order, centered near Z slice `242`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_059_E_N003353_N003359_ct_panel.png).

### Panel 060: `rank_060_E_N003521_N003525_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003521_N003525` (source strut `6251`), ranked 60 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `323`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_060_E_N003521_N003525_ct_panel.png).

### Panel 061: `rank_061_E_N003521_N004659_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003521_N004659` (source strut `8265`), ranked 61 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 26]` in array `[z,y,x]` order, centered near Z slice `363`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_061_E_N003521_N004659_ct_panel.png).

### Panel 062: `rank_062_E_N004487_N004493_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004487_N004493` (source strut `7963`), ranked 62 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 35, 97]` in array `[z,y,x]` order, centered near Z slice `321`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_062_E_N004487_N004493_ct_panel.png).

### Panel 063: `rank_063_E_N007049_N007053_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007049_N007053` (source strut `12519`), ranked 63 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `560`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_063_E_N007049_N007053_ct_panel.png).

### Panel 064: `rank_064_E_N007049_N008313_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007049_N008313` (source strut `14752`), ranked 64 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 26]` in array `[z,y,x]` order, centered near Z slice `599`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_064_E_N007049_N008313_ct_panel.png).

### Panel 065: `rank_065_E_N008183_N009447_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008183_N009447` (source strut `16876`), ranked 65 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 26]` in array `[z,y,x]` order, centered near Z slice `678`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_065_E_N008183_N009447_ct_panel.png).

### Panel 066: `rank_066_E_N008309_N009447_ct_panel.png`

This is the Phase 2C review panel for edge `E_N008309_N009447` (source strut `16877`), ranked 66 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 26]` in array `[z,y,x]` order, centered near Z slice `678`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_066_E_N008309_N009447_ct_panel.png).

### Panel 067: `rank_067_E_N009317_N009447_ct_panel.png`

This is the Phase 2C review panel for edge `E_N009317_N009447` (source strut `16878`), ranked 67 with recorded state **phase2c still review required**, CT anomaly score `3.35`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 26]` in array `[z,y,x]` order, centered near Z slice `718`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_067_E_N009317_N009447_ct_panel.png).

### Panel 068: `rank_068_E_N001128_N002267_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001128_N002267` (source strut `4031`), ranked 68 with recorded state **phase2c still review required**, CT anomaly score `3.3125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 76, 59]` in array `[z,y,x]` order, centered near Z slice `124`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_068_E_N001128_N002267_ct_panel.png).

### Panel 069: `rank_069_E_N003396_N004535_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003396_N004535` (source strut `8063`), ranked 69 with recorded state **phase2c still review required**, CT anomaly score `3.3125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 76, 59]` in array `[z,y,x]` order, centered near Z slice `282`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_069_E_N003396_N004535_ct_panel.png).

### Panel 070: `rank_070_E_N006419_N007683_ct_panel.png`

This is the Phase 2C review panel for edge `E_N006419_N007683` (source strut `13616`), ranked 70 with recorded state **phase2c still review required**, CT anomaly score `3.3125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `519`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_070_E_N006419_N007683_ct_panel.png).

### Panel 071: `rank_071_E_N000371_N000377_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000371_N000377` (source strut `867`), ranked 71 with recorded state **phase2c still review required**, CT anomaly score `3.3106`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 58, 65]` in array `[z,y,x]` order, centered near Z slice `86`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_071_E_N000371_N000377_ct_panel.png).

### Panel 072: `rank_072_E_N004277_N005541_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004277_N005541` (source strut `9804`), ranked 72 with recorded state **phase2c still review required**, CT anomaly score `3.29167`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `361`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_072_E_N004277_N005541_ct_panel.png).

### Panel 073: `rank_073_E_N001889_N002010_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001889_N002010` (source strut `3553`), ranked 73 with recorded state **phase2c still review required**, CT anomaly score `3.28125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 59]` in array `[z,y,x]` order, centered near Z slice `164`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_073_E_N001889_N002010_ct_panel.png).

### Panel 074: `rank_074_E_N003143_N004407_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003143_N004407` (source strut `7788`), ranked 74 with recorded state **phase2c still review required**, CT anomaly score `3.28125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `282`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_074_E_N003143_N004407_ct_panel.png).

### Panel 075: `rank_075_E_N010199_N010203_ct_panel.png`

This is the Phase 2C review panel for edge `E_N010199_N010203` (source strut `18447`), ranked 75 with recorded state **phase2c still review required**, CT anomaly score `3.28125`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 75, 24]` in array `[z,y,x]` order, centered near Z slice `716`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_075_E_N010199_N010203_ct_panel.png).

### Panel 076: `rank_076_E_N002262_N003401_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002262_N003401` (source strut `6047`), ranked 76 with recorded state **phase2c still review required**, CT anomaly score `3.27083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 76, 59]` in array `[z,y,x]` order, centered near Z slice `203`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_076_E_N002262_N003401_ct_panel.png).

### Panel 077: `rank_077_E_N003395_N003399_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003395_N003399` (source strut `6027`), ranked 77 with recorded state **phase2c still review required**, CT anomaly score `3.27083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 76, 23]` in array `[z,y,x]` order, centered near Z slice `242`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_077_E_N003395_N003399_ct_panel.png).

### Panel 078: `rank_078_E_N005663_N005667_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005663_N005667` (source strut `10059`), ranked 78 with recorded state **phase2c still review required**, CT anomaly score `3.27083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 76, 23]` in array `[z,y,x]` order, centered near Z slice `400`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_078_E_N005663_N005667_ct_panel.png).

### Panel 079: `rank_079_E_N006545_N006549_ct_panel.png`

This is the Phase 2C review panel for edge `E_N006545_N006549` (source strut `11603`), ranked 79 with recorded state **phase2c still review required**, CT anomaly score `3.27083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `480`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_079_E_N006545_N006549_ct_panel.png).

### Panel 080: `rank_080_E_N006797_N006801_ct_panel.png`

This is the Phase 2C review panel for edge `E_N006797_N006801` (source strut `12075`), ranked 80 with recorded state **phase2c still review required**, CT anomaly score `3.27083`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 75, 23]` in array `[z,y,x]` order, centered near Z slice `479`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_080_E_N006797_N006801_ct_panel.png).

### Panel 081: `rank_081_E_N000870_N001005_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000870_N001005` (source strut `1740`), ranked 81 with recorded state **phase2c still review required**, CT anomaly score `3.26042`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_081_E_N000870_N001005_ct_panel.png).

### Panel 082: `rank_082_E_N000996_N001131_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000996_N001131` (source strut `1992`), ranked 82 with recorded state **phase2c still review required**, CT anomaly score `3.26042`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 23]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_082_E_N000996_N001131_ct_panel.png).

### Panel 083: `rank_083_E_N004529_N004533_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004529_N004533` (source strut `8043`), ranked 83 with recorded state **phase2c still review required**, CT anomaly score `3.26042`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 76, 23]` in array `[z,y,x]` order, centered near Z slice `321`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_083_E_N004529_N004533_ct_panel.png).

### Panel 084: `rank_084_E_N000749_N002013_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000749_N002013` (source strut `3536`), ranked 84 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `124`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_084_E_N000749_N002013_ct_panel.png).

### Panel 085: `rank_085_E_N000875_N000879_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000875_N000879` (source strut `1523`), ranked 85 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `85`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_085_E_N000875_N000879_ct_panel.png).

### Panel 086: `rank_086_E_N000875_N002139_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000875_N002139` (source strut `3756`), ranked 86 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `124`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_086_E_N000875_N002139_ct_panel.png).

### Panel 087: `rank_087_E_N001001_N001005_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001001_N001005` (source strut `1743`), ranked 87 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 23]` in array `[z,y,x]` order, centered near Z slice `85`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_087_E_N001001_N001005_ct_panel.png).

### Panel 088: `rank_088_E_N001001_N002265_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001001_N002265` (source strut `4008`), ranked 88 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 23]` in array `[z,y,x]` order, centered near Z slice `124`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_088_E_N001001_N002265_ct_panel.png).

### Panel 089: `rank_089_E_N001127_N001131_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001127_N001131` (source strut `1995`), ranked 89 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 77, 23]` in array `[z,y,x]` order, centered near Z slice `84`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_089_E_N001127_N001131_ct_panel.png).

### Panel 090: `rank_090_E_N001883_N003147_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001883_N003147` (source strut `5552`), ranked 90 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `203`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_090_E_N001883_N003147_ct_panel.png).

### Panel 091: `rank_091_E_N002009_N002013_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002009_N002013` (source strut `3539`), ranked 91 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 24]` in array `[z,y,x]` order, centered near Z slice `164`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_091_E_N002009_N002013_ct_panel.png).

### Panel 092: `rank_092_E_N002009_N003273_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002009_N003273` (source strut `5772`), ranked 92 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `203`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_092_E_N002009_N003273_ct_panel.png).

### Panel 093: `rank_093_E_N002135_N002139_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002135_N002139` (source strut `3759`), ranked 93 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 23]` in array `[z,y,x]` order, centered near Z slice `164`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_093_E_N002135_N002139_ct_panel.png).

### Panel 094: `rank_094_E_N002261_N002265_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002261_N002265` (source strut `4011`), ranked 94 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 76, 23]` in array `[z,y,x]` order, centered near Z slice `163`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_094_E_N002261_N002265_ct_panel.png).

### Panel 095: `rank_095_E_N003017_N004281_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003017_N004281` (source strut `7568`), ranked 95 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 24]` in array `[z,y,x]` order, centered near Z slice `282`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_095_E_N003017_N004281_ct_panel.png).

### Panel 096: `rank_096_E_N003143_N003147_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003143_N003147` (source strut `5555`), ranked 96 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `243`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_096_E_N003143_N003147_ct_panel.png).

### Panel 097: `rank_097_E_N003269_N003273_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003269_N003273` (source strut `5775`), ranked 97 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `243`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_097_E_N003269_N003273_ct_panel.png).

### Panel 098: `rank_098_E_N004151_N005415_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004151_N005415` (source strut `9584`), ranked 98 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 97, 24]` in array `[z,y,x]` order, centered near Z slice `361`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_098_E_N004151_N005415_ct_panel.png).

### Panel 099: `rank_099_E_N004277_N004281_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004277_N004281` (source strut `7571`), ranked 99 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `322`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_099_E_N004277_N004281_ct_panel.png).

### Panel 100: `rank_100_E_N004403_N004407_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004403_N004407` (source strut `7791`), ranked 100 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `322`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_100_E_N004403_N004407_ct_panel.png).

### Panel 101: `rank_101_E_N005285_N006549_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005285_N006549` (source strut `11600`), ranked 101 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `440`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_101_E_N005285_N006549_ct_panel.png).

### Panel 102: `rank_102_E_N005411_N005415_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005411_N005415` (source strut `9587`), ranked 102 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `401`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_102_E_N005411_N005415_ct_panel.png).

### Panel 103: `rank_103_E_N005411_N006675_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005411_N006675` (source strut `11820`), ranked 103 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 24]` in array `[z,y,x]` order, centered near Z slice `440`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_103_E_N005411_N006675_ct_panel.png).

### Panel 104: `rank_104_E_N009947_N009951_ct_panel.png`

This is the Phase 2C review panel for edge `E_N009947_N009951` (source strut `17903`), ranked 104 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `717`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_104_E_N009947_N009951_ct_panel.png).

### Panel 105: `rank_105_E_N010073_N010077_ct_panel.png`

This is the Phase 2C review panel for edge `E_N010073_N010077` (source strut `18159`), ranked 105 with recorded state **phase2c still review required**, CT anomaly score `3.25`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `716`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_105_E_N010073_N010077_ct_panel.png).

### Panel 106: `rank_106_E_N003899_N005163_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003899_N005163` (source strut `9144`), ranked 106 with recorded state **phase2c still review required**, CT anomaly score `3.24583`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 25]` in array `[z,y,x]` order, centered near Z slice `362`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_106_E_N003899_N005163_ct_panel.png).

### Panel 107: `rank_107_E_N007301_N008565_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007301_N008565` (source strut `15192`), ranked 107 with recorded state **phase2c still review required**, CT anomaly score `3.23542`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 25]` in array `[z,y,x]` order, centered near Z slice `599`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_107_E_N007301_N008565_ct_panel.png).

### Panel 108: `rank_108_E_N005033_N006297_ct_panel.png`

This is the Phase 2C review panel for edge `E_N005033_N006297` (source strut `11160`), ranked 108 with recorded state **phase2c still review required**, CT anomaly score `3.225`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 25]` in array `[z,y,x]` order, centered near Z slice `441`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_108_E_N005033_N006297_ct_panel.png).

### Panel 109: `rank_109_E_N000366_N000501_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000366_N000501` (source strut `860`), ranked 109 with recorded state **phase2c still review required**, CT anomaly score `3.20417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 25]` in array `[z,y,x]` order, centered near Z slice `46`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_109_E_N000366_N000501_ct_panel.png).

### Panel 110: `rank_110_E_N001505_N002769_ct_panel.png`

This is the Phase 2C review panel for edge `E_N001505_N002769` (source strut `4892`), ranked 110 with recorded state **phase2c still review required**, CT anomaly score `3.20417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 25]` in array `[z,y,x]` order, centered near Z slice `204`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_110_E_N001505_N002769_ct_panel.png).

### Panel 111: `rank_111_E_N002765_N002769_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002765_N002769` (source strut `4895`), ranked 111 with recorded state **phase2c still review required**, CT anomaly score `3.20417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 25]` in array `[z,y,x]` order, centered near Z slice `243`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_111_E_N002765_N002769_ct_panel.png).

### Panel 112: `rank_112_E_N006293_N006297_ct_panel.png`

This is the Phase 2C review panel for edge `E_N006293_N006297` (source strut `11163`), ranked 112 with recorded state **phase2c still review required**, CT anomaly score `3.20417`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 97, 25]` in array `[z,y,x]` order, centered near Z slice `480`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_112_E_N006293_N006297_ct_panel.png).

### Panel 113: `rank_113_E_N000744_N000879_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000744_N000879` (source strut `1520`), ranked 113 with recorded state **phase2c still review required**, CT anomaly score `3.19792`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 98, 24]` in array `[z,y,x]` order, centered near Z slice `45`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_113_E_N000744_N000879_ct_panel.png).

### Panel 114: `rank_114_E_N002135_N003399_ct_panel.png`

This is the Phase 2C review panel for edge `E_N002135_N003399` (source strut `6024`), ranked 114 with recorded state **phase2c still review required**, CT anomaly score `3.19792`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 23]` in array `[z,y,x]` order, centered near Z slice `203`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_114_E_N002135_N003399_ct_panel.png).

### Panel 115: `rank_115_E_N004533_N004535_ct_panel.png`

This is the Phase 2C review panel for edge `E_N004533_N004535` (source strut `8057`), ranked 115 with recorded state **phase2c still review required**, CT anomaly score `3.19583`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 76, 62]` in array `[z,y,x]` order, centered near Z slice `302`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_115_E_N004533_N004535_ct_panel.png).

### Panel 116: `rank_116_E_N006167_N007431_ct_panel.png`

This is the Phase 2C review panel for edge `E_N006167_N007431` (source strut `13176`), ranked 116 with recorded state **phase2c still review required**, CT anomaly score `3.19375`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 25]` in array `[z,y,x]` order, centered near Z slice `520`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_116_E_N006167_N007431_ct_panel.png).

### Panel 117: `rank_117_E_N000861_N000876_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000861_N000876` (source strut `3531`), ranked 117 with recorded state **phase2c still review required**, CT anomaly score `3.18542`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 98]` in array `[z,y,x]` order, centered near Z slice `105`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_117_E_N000861_N000876_ct_panel.png).

### Panel 118: `rank_118_E_N003273_N003275_ct_panel.png`

This is the Phase 2C review panel for edge `E_N003273_N003275` (source strut `5785`), ranked 118 with recorded state **phase2c still review required**, CT anomaly score `3.18542`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[22, 98, 63]` in array `[z,y,x]` order, centered near Z slice `223`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_118_E_N003273_N003275_ct_panel.png).

### Panel 119: `rank_119_E_N000492_N000627_ct_panel.png`

This is the Phase 2C review panel for edge `E_N000492_N000627` (source strut `1080`), ranked 119 with recorded state **phase2c still review required**, CT anomaly score `3.18333`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[61, 98, 25]` in array `[z,y,x]` order, centered near Z slice `46`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage caution:** one endpoint crosses the observed x=767 evidence-support boundary, so endpoint evidence is incomplete. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_119_E_N000492_N000627_ct_panel.png).

### Panel 120: `rank_120_E_N007931_N009069_ct_panel.png`

This is the Phase 2C review panel for edge `E_N007931_N009069` (source strut `16105`), ranked 120 with recorded state **phase2c still review required**, CT anomaly score `3.17708`, and review reason `blocked_or_mixed_evidence_remains_unresolved`. The TIFF crop is `[62, 75, 23]` in array `[z,y,x]` order, centered near Z slice `598`. The PNG decoded successfully at 2790 x 1655 and maps exactly to both index tables. **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x=767 evidence-support boundary. This is unreviewable coverage failure, not proof of absent material. It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel](../../collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120/rank_120_E_N007931_N009069_ct_panel.png).
