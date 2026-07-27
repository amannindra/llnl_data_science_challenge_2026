# Part 2 Methods And Physics Reference Ledger

This ledger records scientific methods used by the Part 2 workflow. It is not a final paper methods section yet.

## DESIGN-EXACT-001 - Exact STL Surface Distance

Purpose:

Identify design-intended removed struts by comparing each canonical graph edge against the `0.stl` and `0.5.stl` triangle surfaces.

Equation:

```text
x(t) = (1 - t) p0 + t p1
delta(t) = distance(x(t), 0.5.stl surface) - distance(x(t), 0.stl surface)
base_score = median(delta(t)) for t in [0.20, 0.80]
```

Inputs:

- canonical nominal graph endpoints: nominal graph units;
- `0.stl` and `0.5.stl`: millimetres;
- graph-to-STL scale: `2.28 mm / nominal graph unit`.

Outputs:

- exact distance scores: millimetres;
- provisional design state: `strong_removed_candidate`, `strong_present_candidate`, or `ambiguous_design_state`.

Implementation:

- Code: `src/part2/design_intent/exact_stl_distance.py`
- Run script: `src/part2/phase2a1.py`
- Outputs: `outputs/part2/phase2a1/design_intent_exact_scores.csv`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Ericson2005RTCD`

Assumptions:

- `A-STL-AXIS-001`
- `A-STL-002`
- `A-STL-EXACT-001`

Validation:

- `tests/part2/test_phase2a1_exact_stl_distance.py`
- Candidate-count audit in `outputs/part2/phase2a1/exact_distance_method.md`

Limitations:

- This is not a signed inside/outside distance.
- Candidate-triangle KD lookup is validated for review ranking, not declared exact final truth under every possible mesh pathology.
- Transform ambiguity remains unresolved.

## SYMMETRY-AUDIT-2A1-001 - Graph/STL Axis And Reflection Audit

Purpose:

Check whether the identity graph-to-STL orientation can be trusted, or whether cube symmetry leaves multiple plausible edge-ID mappings.

Method:

```text
6 axis permutations * 8 sign choices = 48 transforms
```

Independent evidence used:

- STL skin-axis detection from flat boundary triangle normals;
- CT skin-axis detection from sparse thresholded TIFF pages;
- sparse STL-to-CT and CT-to-STL surface distances after mapping each transform into registered CT coordinates.

Outputs:

- `outputs/part2/phase2a1/symmetry_transform_ranking.csv`
- `outputs/part2/phase2a1/symmetry_audit.md`
- `outputs/part2/phase2a1/qc/top_transform_overlays/`

Decision rule:

The transform is not verified unless one physically plausible transform is clearly separated from the runner-up.

Phase 2A.1 result:

```text
UNRESOLVED
```

Reason:

The best and runner-up transform scores are too close for a defensible final edge-ID choice.

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Otsu1979`

Assumptions:

- `A-STL-AXIS-001`
- `A-COORD-001`

Limitations:

- CT surface is sparse, not a full marching-cubes surface.
- Skin axis does not prove LPBF build direction.
- This audit does not classify CT defects.

## GOLD-REVIEW-2A1-001 - Human Review Packet

Purpose:

Create a trusted manual-review packet before CT classifier calibration resumes.

Inputs:

- Phase 2A.1 exact STL scores;
- registered JSON edge coordinates;
- raw TIFF local crops;
- STL local surface neighborhoods.

Outputs:

- `outputs/part2/phase2a1/gold_review/review_index.html`
- `outputs/part2/phase2a1/gold_review/human_labels.csv`
- `outputs/part2/phase2a1/gold_review/panels/`

Human label fields:

- `human_design_label`
- `human_ct_label`
- `reviewer_confidence`
- `reviewer_notes`

Validation:

- Label fields are intentionally blank.
- The packet contains 30 clear removed, 30 clear present, and 20 ambiguous examples.

Limitations:

- The software evidence summary does not assign the final human label.
- Human review remains required before Phase 2B.

## STL-VOXEL-DIFF-2R-001 - Coarse-To-Fine STL Occupancy Difference

Purpose:

Benchmark a design-only way to find removed design volume that is less sensitive to exact STL triangle remeshing.

Equation:

```text
D_p = M_0 AND NOT M_p
```

where:

- `M_0` is the filled voxel occupancy from the 0% STL;
- `M_p` is the filled voxel occupancy from the 0.1%, 0.5%, or 1% STL;
- `D_p` is the deleted design volume.

Inputs:

- STL surface coordinates: millimetres;
- voxel pitch: millimetres per voxel;
- connected-component labels: voxel index space.

Outputs:

- deleted-volume component count;
- component volume in cubic millimetres;
- component centroid, bounding box, PCA axis, axial length, and equivalent radius.

Implementation:

- Code: `src/part2/phase2r_tools.py`
- Run script: `src/part2/phase2r.py`
- Outputs: `outputs/part2/phase2r/design/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Schroeder2006VTK`

Assumptions:

- `A-STL-VOXEL-2R`
- `A-STL-AXIS-001`

Validation:

- `tests/part2/test_phase2r_hybrid_benchmark.py`
- Synthetic cylinder voxelization and synthetic removed-cylinder subtraction tests.

Limitations:

- The released STL meshes are not watertight by the VTK feature-edge check.
- Component count depends on voxel pitch and mesh closure behavior.
- This branch does not choose the graph/STL cube orientation by itself.
- It does not classify CT defects.

Phase 2R result:

```text
0.1% deleted-volume components = 7
0.5% deleted-volume components = 67
1.0% deleted-volume components = 104
```

## CT-ATLAS-2R-001 - Straightened CT Strut Atlas And Robust Template Scores

Purpose:

Benchmark CT-only anomaly ranking without using design-removal labels to fit the template.

Method:

For each registered graph edge:

```text
x(s,u,v) = centerline(s) + u e1 + v e2
```

where:

- `s` walks along the strut axis;
- `u` and `v` are local cross-section directions;
- endpoint/node regions are excluded so node blobs do not dominate the strut signal.

For each axial station:

```text
A(s) = number of thresholded material voxels in the local cross-section
r_eq(s) = sqrt(A(s) / pi)
```

A robust group template is built from comparable struts:

```text
median_A(s) = median(A_i(s))
MAD_A(s) = median(|A_i(s) - median_A(s)|)
negative_residual(s) = max(0, median_A(s) - A_i(s)) / (MAD_A(s) + 1)
```

Inputs:

- registered JSON coordinates: CT voxel coordinates in `[x,y,z]`;
- TIFF volume: intensity values indexed as `[z,y,x]`;
- threshold: CT intensity units;
- straightened local grid: voxels.

Outputs:

- local registration correction magnitude and residual in voxels;
- area profile in voxels squared;
- equivalent radius profile in voxels;
- occupied axial fraction;
- longest low-area gap fraction;
- 6-neighbor and 26-neighbor bridge connectivity;
- negative and positive template residual scores;
- CT anomaly rank, not a final defect label.

Implementation:

- Code: `src/part2/phase2r_tools.py`
- Run script: `src/part2/phase2r.py`
- Outputs: `outputs/part2/phase2r/ct/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Otsu1979`
- `Hampel1974`
- `BeslMcKay1992ICP`

Assumptions:

- `A-COORD-001`
- `A-SEG-001`
- `A-CT-ATLAS-2R`

Validation:

- `tests/part2/test_phase2r_hybrid_benchmark.py`
- Bounded local-node correction test.
- Straightened-volume coordinate transform test.
- Median/MAD robustness with planted anomaly test.

Limitations:

- The pilot evaluated 500 edges, not all 18,468 edges.
- Template scores are anomaly ranks, not final missing/disconnected labels.
- The method still depends on registration quality, threshold stability, and enough comparable struts.

## FUSION-SYMMETRY-2R-001 - Late Fusion Of Design And CT Evidence

Purpose:

Use an asymmetric missing-pattern signal to rank the 48 possible graph/STL cube orientations.

Equation:

```text
J(T) = median(anomaly scores for mapped removed edges under transform T)
       - median(anomaly scores for matched design-present controls)
```

A rank/AUC alternative and bootstrap intervals are also reported.

Inputs:

- deleted-volume component-to-edge candidates from `STL-VOXEL-DIFF-2R-001`;
- CT anomaly scores from `CT-ATLAS-2R-001`;
- 48 axis/sign transforms.

Outputs:

- transform ranking;
- bootstrap uncertainty;
- status: `VERIFIED`, `PROVISIONAL`, or `UNRESOLVED`.

Implementation:

- Code: `src/part2/phase2r_tools.py`
- Run script: `src/part2/phase2r.py`
- Outputs: `outputs/part2/phase2r/fusion/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-STL-AXIS-001`
- `A-FUSION-2R`

Validation:

- `tests/part2/test_phase2r_hybrid_benchmark.py`
- Synthetic asymmetric cube-pattern test.
- Coverage-gate tests preventing sparse CT evidence from being called verified.

Limitations:

- Phase 2R CT coverage was too sparse for verification: the top transform evaluated only 7 of 67 mapped removed components in CT.
- This method must not publish final defect percentages.
- The current status is `PROVISIONAL`, not final ground truth.

## ANCHOR-REVIEW-2R1-001 - Manual Anchor Packet And Expanded Transform Coverage

Purpose:

Resolve the graph/STL orientation bottleneck with a small number of high-value human anchors instead of asking for broad manual labeling.

Method:

1. Start from the Phase 2R transform ranking.
2. Expand CT feature sampling around mapped deleted-volume edges for plausible transforms.
3. Rerank transforms with the same late-fusion score:

```text
J(T) = median(anomaly scores for mapped removed edges under transform T)
       - median(anomaly scores for matched design-present controls)
```

4. Select primary anchor candidates from the leading transform using CT anomaly, deleted-volume component evidence, endpoint-excluded gap behavior, and deterministic ranking.
5. Leave all human label fields blank.

Inputs:

- Phase 2R component-to-edge candidates;
- Phase 2R CT feature table;
- registered canonical graph;
- raw TIFF for added CT features and anchor panels.

Outputs:

- `outputs/part2/phase2r1/expanded_transform_ranking.csv`
- `outputs/part2/phase2r1/expanded_ct_features.csv`
- `outputs/part2/phase2r1/anchor_review.html`
- `outputs/part2/phase2r1/human_anchor_labels.csv`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-STL-AXIS-001`
- `A-CT-ATLAS-2R`
- `A-ANCHOR-2R1`

Validation:

- `tests/part2/test_phase2r_hybrid_benchmark.py`
- Tests cover deterministic expanded-cohort inclusion, anchor ranking, and preservation of any existing human labels.

Limitations:

- Phase 2R.1 still does not classify the full specimen.
- Superseded status note: the first generated human anchor labels were blank, but the repaired CSV was later filled for the 5 primary anchors.
- The anchor gate now supports Phase 2B calibration, but not final specimen-wide classification.

## PHASE2B-CAL-PREP-001 - Human-Anchored CT Calibration Preparation

Purpose:

Use the passed Phase 2R.1 anchor gate to test whether design-removed candidate struts have CT evidence that separates them from sampled design-present/control struts.

Method:

1. Require a passed anchor-gate JSON.
2. Use the human-anchored transform `perm021_signmmm`.
3. Label the sampled CT feature rows whose edge IDs are mapped from design-removed STL components.
4. Compare design-removed candidates against sampled controls using interpretable CT features:
   - CT missing-material anomaly score;
   - longest low-area gap fraction;
   - negative template residual;
   - occupied axial fraction;
   - mean cross-sectional area;
   - core-minus-background contrast.
5. Choose diagnostic thresholds by maximizing balanced accuracy on the calibration cohort.
6. Report uncertainty and review-needed rows, but do not publish final specimen-wide percentages.

Inputs:

- `outputs/part2/phase2r1/anchor_gate_runs/20260726_220926/anchor_gate_summary.json`
- `outputs/part2/phase2r1/expanded_ct_features.csv`
- `outputs/part2/phase2r/design/component_to_edge_candidates.csv`

Outputs:

- `outputs/part2/phase2b/20260726_222359/calibration_report.md`
- `outputs/part2/phase2b/20260726_222359/calibration_summary.json`
- `outputs/part2/phase2b/20260726_222359/uncertain_edges.csv`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-ANCHOR-2R1`
- `A-STL-AXIS-001-HUMAN-ANCHORED`
- `A-CT-FEATURES-001`

Validation:

- `tests/part2/test_phase2b_calibration.py`
- Full Part 2 unittest suite.

Limitations:

- The calibration cohort used 1300 sampled CT edges, not all 18468 graph edges.
- Thresholds are diagnostic calibration thresholds, not universal physical laws.
- No final missing/disconnected percentages are reported.

## PHASE2B1-MULTI-EDGE-001 - Deleted-Component To Multi-Edge Reconciliation

Purpose:

Resolve the apparent mismatch between 67 deleted STL components and the expected roughly 92 intentionally removed struts for the 0.5% design.

Method:

1. Use the human-anchored transform `perm021_signmmm`.
2. Load the 0.5% STL deleted-volume components from Phase 2R.
3. Estimate a typical single-strut deleted volume as the median component volume:

```text
V_ref = median(V_component)
```

4. Estimate each component's strut-equivalent count:

```text
n_component = max(1, round(V_component / V_ref))
```

5. Rebuild broad component-to-edge candidates under the anchored transform instead of keeping only the top three saved candidates.
6. Select the first `n_component` edge candidates for each component using deterministic midpoint-distance order with axis alignment as tie-break evidence.
7. Sample CT features for selected design-candidate edges that were missing from the 1300-row Phase 2B table.
8. Recompute robust CT templates, anomaly rankings, calibration summaries, and review-priority panels.

Inputs:

- `outputs/part2/phase2r/design/removed_components_0p5.csv`
- `outputs/part2/phase2r1/anchor_gate_runs/20260726_220926/anchor_gate_summary.json`
- `outputs/part2/phase2r1/expanded_ct_features.csv`
- `outputs/part2/phase0/canonical_graphs/nominal_9x9.canonical_graph.json`
- `outputs/part2/phase0/canonical_graphs/registered_9x9.canonical_graph.json`
- missing-struts TIFF stack

Outputs:

- `outputs/part2/phase2b1/20260726_231259/phase2b1_report.md`
- `outputs/part2/phase2b1/20260726_231259/component_multiplicity_summary.csv`
- `outputs/part2/phase2b1/20260726_231259/design_removed_edge_candidates_multi.csv`
- `outputs/part2/phase2b1/20260726_231259/ct_edge_features_reconciled.csv`
- `outputs/part2/phase2b1/20260726_231259/review_panels/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-ANCHOR-2R1`
- `A-DESIGN-VOLUME-001`
- `A-CT-ATLAS-2R`

Validation:

- `tests/part2/test_phase2b_calibration.py`
- Full Part 2 unittest suite.
- Phase 2B.1 result: 67 deleted components, 94 selected canonical edge candidates, 26 newly sampled CT edges, and AUC 0.9635 for CT missing-material anomaly score.

Limitations:

- Volume-equivalent count is a calibrated design-intent heuristic, not a direct CT defect count.
- The 94-edge set remains a candidate design-intent set until review and broader CT sampling are complete.
- No final specimen-wide missing/disconnected percentages are reported.

## PHASE2B2-ALL-EDGE-PREP-001 - Batched Registered-Edge CT Sampling Preparation

Purpose:

Expand CT feature coverage from the Phase 2B.1 calibration set toward all registered canonical 9x9x9 graph edges while keeping outputs as non-final candidate evidence.

Method:

1. Load the registered canonical graph with `18,468` expected strut edges.
2. Load an existing CT feature table. By default this is the Phase 2B.1 reconciled table with `1,326` rows.
3. Load the reconciled `94` design-removed candidate edge set from Phase 2B.1.
4. Choose a deterministic batch of unsampled edges:
   - unsampled design-removed candidates first, if any;
   - then round-robin coverage across coarse orientation, boundary bin, and spatial region.
5. For each selected edge, reuse the CT atlas sampler:
   - estimate bounded local endpoint corrections;
   - straighten the local CT volume along the registered edge;
   - exclude node-dominated endpoint regions;
   - compute core/background contrast, axial area profile, occupied fraction, longest low-area gap, bridge connectivity, centerline displacement, and sensitivity metrics.
6. Recompute robust median/MAD CT templates on the combined feature table.
7. Use the Phase 2B.1 calibrated anomaly threshold as a diagnostic candidate threshold.
8. Assign non-final candidate statuses:
   - `candidate_design_removed_missing_like`;
   - `uncertain_design_removed_low_ct_anomaly`;
   - `candidate_unexpected_missing_like`;
   - `uncertain_near_threshold_present_like`;
   - `candidate_present_like`.
9. Write review-priority rows and CT panels for the most important uncertain or surprising cases.
10. During long sampling, write partial feature checkpoints and a checkpoint manifest.
11. Stop before final specimen-wide classification.

Equations and decision quantities:

The CT anomaly score remains the project-defined robust-template score from `CT-TEMPLATE-ROBUST-001`:

```text
score = negative_template_residual
      + longest_low_area_gap_fraction
      + max(0, 0.85 - occupied_axial_fraction)
      + 0.25 * threshold_stability_occupied_fraction_range
```

The Phase 2B.2 candidate-status threshold is inherited from Phase 2B.1:

```text
ct_missing_material_anomaly_score >= 2.020833333333333
```

This threshold is a dataset-specific calibration diagnostic, not a universal physical law.

Input units:

- registered edge coordinates: CT voxels in `[x,y,z]`;
- TIFF array indexing: `[z,y,x]`;
- intensity: raw CT grayscale value;
- lengths: voxels unless a field name states `mm`.

Outputs:

- `outputs/part2/phase2b2/20260727_013304/run_manifest.json`
- `outputs/part2/phase2b2/20260727_013304/sampling_plan.csv`
- `outputs/part2/phase2b2/20260727_013304/newly_sampled_ct_features.csv`
- `outputs/part2/phase2b2/20260727_013304/newly_sampled_ct_features.partial.csv`
- `outputs/part2/phase2b2/20260727_013304/checkpoint_manifest.json`
- `outputs/part2/phase2b2/20260727_013304/combined_ct_edge_features.csv`
- `outputs/part2/phase2b2/20260727_013304/candidate_classification_prep.csv`
- `outputs/part2/phase2b2/20260727_013304/uncertain_priority_edges.csv`
- `outputs/part2/phase2b2/20260727_013304/review_panels/`
- `outputs/part2/phase2b2/20260727_013304/phase2b2_report.md`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-STL-AXIS-001-HUMAN-ANCHORED`
- `A-DESIGN-VOLUME-001`
- `A-CT-FEATURES-001`
- `A-PHASE2B2-BATCH-001`

Validation:

- `tests/part2/test_phase2b_calibration.py`
- Full Part 2 unittest suite.
- Latest run result: `16,142` new CT edges sampled; combined feature count `18,468`; remaining unsampled edges `0`; all tests passed with `71` tests OK and `1` optional VTK test skipped.

Limitations:

- Phase 2B.2 is a candidate-preparation workflow, not final CT defect classification.
- All `18,468 / 18,468` registered edges are sampled in the latest valid run.
- Candidate statuses depend on the Phase 2B.1 diagnostic threshold and must remain uncertain until final review/uncertainty rules are complete.
- The `1,137` unexpected missing-like sampled edges are not final unintended-defect counts.

## PHASE2B3-GUARDED-LABELS-001 - Guarded CT Observation Labels

Purpose:

Convert the all-edge Phase 2B.2 CT feature table into explicit guarded labels
that separate design intent, CT observation, and review status.

Method:

1. Load all `18,468` registered-edge CT feature rows from Phase 2B.2.
2. Load all-edge calibrated metric thresholds from `phase2b2_summary.json`.
3. For each edge, evaluate independent missing-material evidence flags:
   - high CT missing-material anomaly score;
   - high longest low-area gap fraction;
   - high negative template residual;
   - low occupied axial fraction;
   - low mean cross-sectional area;
   - low core-minus-background contrast;
   - broken 26-neighbor bridge connectivity.
4. Count the number of missing-material evidence flags:

```text
N_missing_flags = sum(flag_i)
```

5. Call `ct_absent_candidate` only when the CT score is high and the strut is
   mostly empty, low-area, low-occupancy, and gapped or disconnected.
6. Call `ct_disconnected_candidate` when the CT score is high and there is a
   gap or broken bridge, but some material remains.
7. Call `ct_present_like` only when missing evidence is low, the bridge is
   connected, and the score is not near a threshold.
8. Mark mixed, near-threshold, threshold-sensitive, or registration-sensitive
   cases as review-required.
9. Combine CT observation with design intent:
   - intentionally designed removal;
   - possible unintended missing/disconnected;
   - present-like;
   - uncertain/review-required.
10. Stop before publishing final specimen-wide percentages.

Main thresholds from the latest run:

```text
ct_missing_material_anomaly_score high >= 2.8135416666666666
older Phase 2B.1 warning threshold >= 2.020833333333333
longest_low_area_gap_fraction high >= 0.5208333333333333
negative_template_residual high >= 1.123397435897436
occupied_axial_fraction low <= 0.10416666666666666
area_mean_voxels2 low <= 0.3125
core_minus_background_contrast low <= 0.028496128080248578
near-threshold margin = 0.5
threshold stability warning > 0.25
local registration stability warning >= 2.5 voxels
```

Input units:

- registered edge coordinates: CT voxels in `[x,y,z]`;
- TIFF array indexing: `[z,y,x]`;
- intensity: raw CT grayscale value;
- cross-sectional area: voxels squared;
- length/gap fractions: dimensionless fractions;
- registration stability: voxels.

Outputs:

- `outputs/part2/phase2b3/20260727_090709/guarded_edge_labels.csv`
- `outputs/part2/phase2b3/20260727_090709/guarded_label_summary.json`
- `outputs/part2/phase2b3/20260727_090709/label_summary_report.md`
- `outputs/part2/phase2b3/20260727_090709/review_required_edges.csv`
- `outputs/part2/phase2b3/20260727_090709/top_possible_unintended_edges.csv`
- `outputs/part2/phase2b3/20260727_090709/design_removed_disagreements.csv`
- `outputs/part2/phase2b3/20260727_090709/review_panels/`
- `outputs/part2/phase2b3/20260727_090709/qc/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-STL-AXIS-001-HUMAN-ANCHORED`
- `A-DESIGN-VOLUME-001`
- `A-CT-FEATURES-001`
- `A-PHASE2B3-GUARDED-001`

Validation:

- `tests/part2/test_phase2b3_guarded_labels.py`
- Full Part 2 unittest suite.
- Latest run result: `18,468` input feature rows, `14,820` present-like rows, `478` possible unintended missing/disconnected candidates, `3,573` review-required rows, and `60` review panels.
- Tests after implementation: `77` tests OK with `1` optional VTK test skipped.

Limitations:

- Guarded labels are screening labels, not final user-approved publication percentages.
- Possible unintended defects require review because false positives can arise from registration, thresholding, boundary/skin effects, and local CT ambiguity.
- The intentionally removed design set depends on the human-anchored graph/STL transform and the Phase 2B.1 volume-equivalent mapping.

## PHASE2B4-AUTO-REVIEW-001 - Automated Evidence Review And Draft Candidate Reduction

Purpose:

Continue beyond the Phase 2B.3 review queue by applying stricter automatic
evidence rules. This reduces the number of blocked cases while still avoiding
unreviewed final publication percentages.

Method:

1. Load `outputs/part2/phase2b3/20260727_090709/guarded_edge_labels.csv`.
2. Preserve the Phase 2B.3 label as the upstream guarded observation.
3. For possible unintended missing/disconnected candidates, require clean
   evidence before automatic support:
   - CT anomaly score must exceed the all-edge threshold by a margin;
   - the score must not be near the threshold;
   - threshold-stability warning must be absent;
   - local-registration instability warning must be absent;
   - enough independent missing-material flags must agree.
4. Keep cases that fail these stricter rules in `manual_review_queue.csv`.
5. Keep low-evidence uncertain cases as low-priority and not reported as
   defects by the automated review.
6. Write draft automated counts and spot-check panels.

Decision quantities:

```text
minimum_auto_score = 2.8135416666666666 + 0.5
possible_missing_auto_supported if N_missing_flags >= 7
possible_disconnected_auto_supported if N_missing_flags >= 5
threshold_stability_occupied_fraction_range <= 0.25
local_registration_stability_voxels < 2.5
```

Input units:

- CT anomaly score: dimensionless project-defined score;
- threshold stability: occupied-fraction range, dimensionless;
- local registration stability: voxels;
- gap and occupied fractions: dimensionless;
- edge coordinates: registered CT voxels.

Outputs:

- `outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv`
- `outputs/part2/phase2b4/20260727_092219/phase2b4_summary.json`
- `outputs/part2/phase2b4/20260727_092219/draft_defect_summary_not_for_publication.md`
- `outputs/part2/phase2b4/20260727_092219/auto_supported_unintended_candidates.csv`
- `outputs/part2/phase2b4/20260727_092219/manual_review_queue.csv`
- `outputs/part2/phase2b4/20260727_092219/spotcheck_panels/`
- `outputs/part2/phase2b4/20260727_092219/qc/`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-PHASE2B3-GUARDED-001`
- `A-PHASE2B4-AUTO-REVIEW-001`

Validation:

- `tests/part2/test_phase2b4_automated_review.py`
- Full Part 2 unittest suite.
- Latest run result: `202` auto-supported possible unintended missing, `12` auto-supported possible unintended disconnected, `214` combined auto-supported possible unintended candidates, `920` blocked manual-review rows, and `80` spot-check panels.
- Tests after implementation: `82` tests OK with `1` optional VTK test skipped.

Limitations:

- Automated review is not the same as human visual validation.
- Many auto-supported possible unintended candidates are boundary/skin-adjacent, so spot-check approval is still needed before publication.
- Draft fractions are internal workflow quantities, not final reported defect percentages.

## FINAL-REPORT-PACKAGE-001 - Spot-Check-Supported Final Report Packaging

Purpose:

Package the Phase 2B.4 automated-review result and the user's human spot-check
labels into a reproducible final-report folder without creating new CT labels.

Method:

1. Read `outputs/part2/phase2b4/20260727_092219/phase2b4_summary.json`.
2. Read `outputs/part2/phase2b4/20260727_092219/human_spotcheck_labels_rank001_040.csv`.
3. Calculate:
   - possible unintended combined count = possible missing + possible disconnected;
   - draft automated possible-unintended fraction = combined count / total expected struts;
   - human defect-like support = material_absent + material_disconnected;
   - present-like contradiction count.
4. Copy compact supporting tables and the Phase 2B.4 label-count QC figure into a new final-report run folder.
5. Write a Markdown report, JSON summary, run manifest, and agentic workflow guide.

Decision quantities:

```text
draft_fraction = 214 / 18468 = 0.011587611002815681
draft_percent = 1.158761100281568
human_defect_like_support = 36 / 40 = 0.9
present_like_contradictions = 0 / 40
```

Input units:

- counts: struts or review panels;
- fractions and percentages: dimensionless;
- labels: categorical review outcomes.

Outputs:

- `outputs/part2/final_report/20260727_123413/final_ct_defect_report.md`
- `outputs/part2/final_report/20260727_123413/final_ct_defect_summary.json`
- `outputs/part2/final_report/20260727_123413/agentic_workflow.md`
- `outputs/part2/final_report/20260727_123413/tables/`
- `outputs/part2/final_report/20260727_123413/figures/`
- `outputs/part2/final_report/20260727_123413/run_manifest.json`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-FINAL-SPOTCHECK-001`
- `A-PHASE2B4-AUTO-REVIEW-001`

Validation:

- `tests/part2/test_final_report.py`
- Targeted test result: `4` tests OK.
- Skill validation result: `.agents/skills/part2-defect-analysis` is valid.

Limitations:

- The package does not add new CT evidence or labels.
- The top `40` spot-check panels support the estimate, but all `214` auto-supported candidates were not manually labeled.
- The `920` blocked manual-review rows remain unresolved and are not counted as defects.

## PHASE2C-MANUAL-QUEUE-TRIAGE-001 - Second-Pass Automatic Triage

Purpose:

Reduce the Phase 2B.4 blocked manual-review queue using stricter, explainable
second-pass rules while keeping mixed or unstable rows unresolved.

Method:

1. Load `outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv`.
2. Preserve all Phase 2B.4 auto-supported rows.
3. For blocked possible-missing rows, promote only when the row has:
   - high anomaly score with an added margin;
   - enough independent missing-evidence flags;
   - almost zero occupied strut body;
   - almost zero mean cross-sectional area;
   - almost full-length low-material gap;
   - broken 26-neighbor bridge connectivity;
   - bounded threshold and local-registration instability.
4. For blocked possible-disconnected rows, promote only when the row has:
   - high anomaly score;
   - enough missing-evidence flags;
   - long low-material gap;
   - broken 26-neighbor bridge connectivity;
   - bounded threshold and local-registration instability.
5. Demote low-score, low-evidence uncertain rows to low-priority uncertain.
6. Keep all mixed, design-conflict, or highly unstable rows review-required.

Decision quantities:

```text
score_extreme = ct_missing_material_anomaly_score >= anomaly_score_high + 0.75
missing_promote if:
    N_missing_flags >= 6
    occupied_axial_fraction <= 0.05
    area_mean_voxels2 <= 0.25
    longest_low_area_gap_fraction >= 0.95
    bridge_connected_26 == false
    threshold_stability_occupied_fraction_range <= 0.50
    local_registration_stability_voxels <= 4.0

disconnected_promote if:
    ct_missing_material_anomaly_score >= anomaly_score_high + 0.50
    N_missing_flags >= 5
    longest_low_area_gap_fraction >= 0.70
    bridge_connected_26 == false
    threshold_stability_occupied_fraction_range <= 0.50
    local_registration_stability_voxels <= 4.0
```

Input units:

- CT anomaly score: dimensionless project-defined score;
- missing-evidence flags: integer count;
- occupied axial fraction and low-area gap fraction: dimensionless fractions;
- area mean: voxels squared;
- threshold stability: occupied-fraction range, dimensionless;
- local registration stability: voxels;
- edge coordinates: registered CT voxels in `[x,y,z]`.

Outputs:

- `outputs/part2/phase2c/20260727_132248/phase2c_labels.csv`
- `outputs/part2/phase2c/20260727_132248/phase2c_summary.json`
- `outputs/part2/phase2c/20260727_132248/phase2c_auto_supported_unintended_candidates.csv`
- `outputs/part2/phase2c/20260727_132248/phase2c_remaining_review_queue.csv`
- `outputs/part2/phase2c/20260727_132248/review_packet/`
- `outputs/part2/phase2c/20260727_132248/run_manifest.json`

References:

- `LLNLDSC2026`
- `FisherTran2023RUS`
- `Hampel1974`

Assumptions:

- `A-PHASE2B4-AUTO-REVIEW-001`
- `A-PHASE2C-TRIAGE-001`

Validation:

- `tests/part2/test_phase2c_manual_queue_triage.py`
- Full Part 2 unittest suite after implementation: `93` tests OK with `1` optional VTK test skipped.
- Latest dedicated run result: `215` possible unintended missing, `13` possible unintended disconnected, `228` combined, `14` newly promoted from blocked rows, `677` still review-required rows, and `2,654` low-priority uncertain rows.

Limitations:

- Phase 2C reuses existing all-edge CT features; it does not perform a new raw-TIFF sampling pass.
- Promoted rows should still be spot-checked before replacing the Phase 2B.4 final-report baseline.
- Remaining review-required rows are not counted as defects.
- The thresholds are project-defined triage thresholds, not universal physical laws.

## DEFECT-VIEWER-001 - Local Graph-Level Defect Viewer

Purpose:

Export a dependency-free local HTML viewer showing all registered canonical
struts colored by current automated class.

Method:

1. Load the registered canonical 9x9x9 graph.
2. Load the latest label CSV, usually Phase 2C labels.
3. Convert each edge into a line segment from canonical registered endpoint
   coordinates.
4. Assign a viewer class by label string:
   - present-like;
   - possible unintended missing;
   - possible unintended disconnected;
   - designed removed;
   - review required;
   - low-priority uncertain.
5. Write compact JSON plus a standalone HTML/canvas viewer.

Input units:

- edge endpoint coordinates: registered CT voxels in `[x,y,z]`;
- labels: categorical strings from Phase 2B.4 or Phase 2C.

Outputs:

- `outputs/part2/visualization/20260727_132343/index.html`
- `outputs/part2/visualization/20260727_132343/viewer_data.json`
- `outputs/part2/visualization/20260727_132343/legend.json`
- `outputs/part2/visualization/20260727_132343/run_manifest.json`

References:

- `LLNLDSC2026`

Assumptions:

- `A-COORD-001`
- `A-PHASE2C-TRIAGE-001`

Validation:

- `tests/part2/test_pipeline_and_viewer.py`
- Latest viewer class counts: `14,820` present-like, `215` possible unintended missing, `13` possible unintended disconnected, `89` designed removed, `677` review-required, and `2,654` low-priority uncertain.

Limitations:

- This viewer draws the expected graph, not a segmented CT surface or STL mesh.
- It is meant for global spatial context and fast review, not final visual proof.
- Local CT panels are still needed to judge individual ambiguous struts.

## PIPELINE-RUNNER-001 - Config-Driven Part 2 Orchestration

Purpose:

Provide a single command that validates the configured dataset package and
orchestrates the current deterministic Part 2 workflow layers.

Method:

1. Read `configs/part2.yaml`.
2. Check required raw TIFF, JSON, and STL files exist and are not Git LFS pointer text.
3. Record input hashes and Git state.
4. Build a stage plan covering preflight, canonical graph reuse, Phase 2B.4 reuse,
   Phase 2C triage, final-report packaging, and viewer export.
5. In dry-run mode, stop after preflight and manifest writing.
6. In normal mode, run Phase 2C, export a viewer, and create a conservative
   final-report package.

Input units:

- File paths and run options from `configs/part2.yaml`;
- raw file sizes in bytes;
- SHA-256 hashes as provenance strings.

Outputs:

- `outputs/part2/pipeline_runs/20260727_132540/pipeline_run_manifest.json`
- `outputs/part2/pipeline_runs/20260727_132552/pipeline_run_manifest.json`
- `outputs/part2/pipeline_runs/20260727_132552/phase2c/`
- `outputs/part2/pipeline_runs/20260727_132552/visualizer/`
- `outputs/part2/pipeline_runs/20260727_132552/final_report/`

References:

- `LLNLDSC2026`

Assumptions:

- `A-AGENTIC-PIPELINE-001`
- `A-PHASE2C-TRIAGE-001`
- `A-FINAL-SPOTCHECK-001`

Validation:

- `tests/part2/test_pipeline_and_viewer.py`
- Dry-run output `outputs/part2/pipeline_runs/20260727_132540/` reported `can_run_strut_level_pipeline = true`.
- Full pipeline output `outputs/part2/pipeline_runs/20260727_132552/` reproduced the Phase 2C `228` combined count and exported a viewer with `18,468` edges.

Limitations:

- The current runner reuses existing Phase 2B.4 and all-edge CT feature outputs.
- A brand-new specimen still needs registered JSON and design-intent inputs before strut-level classification can run safely.
- The pipeline does not bypass stop gates or human-review caveats.
