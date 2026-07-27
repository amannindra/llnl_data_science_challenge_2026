# Deferred Plan: Design-Aware TIFF Strut-Defect Inspector

> **STATUS: DEFERRED — DO NOT IMPLEMENT AS PART OF THE COMPONENT REFACTOR**
>
> This file preserves the proposed TIFF defect-detection work for a later pass.
> The current implementation includes only reusable foundations and the clearly
> labeled historical occupancy diagnostic. No item below is currently claimed
> as a validated detector.

## Intended result

Compare the registered ideal lattice with the raw and segmented CT volumes and
produce one conservative state per expected physical strut:

- `present`
- `missing`
- `disconnected`
- `manual_review`
- `unobservable`

The output would be a per-strut table, structural summary, candidate projections,
registration evidence, sensitivity results, and an auditable validation report.

## Evidence and fixed conventions

- Raw TIFF: shape `(761, 815, 837)`, axes `ZYX`, dtype `uint16`.
- Corrected segmented TIFF: same shape/axes, dtype `uint8`, values `{0, 255}`.
- Registered JSON: 10,206 junction records, 3,430 welded physical nodes, and
  18,468 expected struts.
- JSON positions and transforms use `(x, y, z)`; arrays use `[z, y, x]`.
- Voxel pitch from Fisher/Tran et al.: `58.1 µm`.
- Paper strut diameter: `424 µm`, giving radius `3.65 voxels`.
- Challenge nominal diameter: `350 µm`, giving sensitivity radius `3.01 voxels`.
- The segmented TIFF is supporting evidence, not ground truth.
- Reported paper defect rates are diagnostic comparisons only; they must not be
  used to tune thresholds or force the output distribution.
- The old 25-point/radius-2 JSON occupancy method produced 3,875/18,468
  candidate-missing struts (20.98%) and cannot distinguish endpoint disconnects.
  It is not an acceptable detector baseline without the caveats above.

## Deferred architecture

Future implementation would add focused modules under `Scripts/Components/`:

- `registration.py`
- `strut_extraction.py`
- `strut_features.py`
- `defect_classifier.py`
- `defect_reporting.py`

Future CLIs would live under `Scripts/tif_defect_detection/`:

- `inspect.py`
- `compare_frames.py`
- `validate.py`

No MCP, `src`, `src2`, or new Napari code is part of this design.

## Phase 1 — Independent frame estimation

Estimate a separate correction transform for the raw TIFF and segmented TIFF.
Do not hard-code a 3-degree rotation and do not assume the two files differ by
that amount merely because one filename says “Tilted.”

1. Start from the existing design-to-registered JSON similarity transform.
2. Fit a bounded seven-degree-of-freedom correction using a robust one-way
   design-centerline-to-foreground distance objective.
3. Use multi-resolution, multi-start optimization.
4. Exclude solid skins and the outer one-cell boundary from the fit.
5. Bound rotation to `±5°` per axis, translation to `±50 voxels` per axis, and
   scale multiplier to `[0.98, 1.02]`.
6. Save the 4×4 XYZ transform, objective values, residual quantiles, optimizer
   status, and uncertainty/sensitivity evidence for each volume.

Registration gates:

- Synthetic recovery: translation error `≤0.5 voxel`, rotation error `≤0.1°`,
  and scale error `≤0.1%`.
- Real interior fit: median centerline-to-material distance `≤1.5 voxels` and
  90th percentile `≤3.65 voxels`.
- A failed gate makes affected struts `unobservable`; it must not be hidden by a
  permissive classification threshold.

## Phase 2 — Physical graph construction

1. Parse the registered JSON with strict endpoint validation.
2. Weld coincident junction records before connectivity calculations.
3. Preserve every source junction ID and source strut ID as provenance.
4. Confirm the welded design is one physical component.
5. Reject or report dangling source references, self-loops, and duplicate edges.

Raw record IDs must never be treated as a global physical graph. Doing so creates
hundreds of false components because shared cell-boundary nodes are duplicated.

## Phase 3 — Per-strut ROI extraction

For each expected strut, construct an oriented cylindrical sampling frame:

- Primary radius: `3.65 voxels`.
- Sensitivity radius: `3.01 voxels`.
- Axial range: `-2r` through `length + 2r` to include both junction caps.
- Axial step: `0.5 voxel`.
- Cross-section half-width: `2r + 2 voxels`.
- Cross-section step: `0.75 voxel`.
- Raw intensity interpolation: trilinear.
- Segmented-mask interpolation: nearest neighbor.
- Batch size: approximately 16–32 struts, using memory-mapped volumes.

Every ROI record must include source coverage. Out-of-bounds coordinates are not
silently clipped and counted as background; inadequate coverage is
`unobservable`.

## Phase 4 — Source-specific features

Calculate features independently for raw intensity and segmented-mask evidence:

- axial supported-area profile
- axial intensity profile
- cross-sectional centroid drift
- body support fraction
- longest unsupported interior gap
- number and span of connected material components
- whether a dominant component reaches both endpoint caps
- endpoint-sphere support
- source agreement/disagreement
- field-of-view coverage
- registration and radius sensitivity

An axial bin is supported only when material covers at least 20% of the nominal
disk area. This threshold must be tested rather than inferred from paper rates.

## Phase 5 — Conservative rule classifier

Initial interpretable rules to test, not final truth:

1. `unobservable`
   - registration gate failed, or
   - ROI coverage is below 95%, or
   - required features are nonfinite.
2. `missing`
   - body support is at most 20%,
   - dominant component spans at most 25% of the strut body, and
   - raw and segmented evidence agree.
3. `disconnected`
   - body support is at least 50%, and
   - no component reaches both endpoint caps, or an interior unsupported gap is
     at least 3 voxels.
4. `present`
   - body support is at least 80%,
   - longest unsupported gap is below 3 voxels, and
   - one component reaches both endpoint caps.
5. `manual_review`
   - every remaining case, including source disagreement and sensitivity flips.

`manual_review` and `unobservable` are safety outcomes, not errors to force into
the other three classes.

## Phase 6 — Perturbation sensitivity

Recalculate labels over 15 transforms:

- nominal transform
- translation `±1 voxel` on X, Y, and Z (6)
- rotation `±0.25°` about X, Y, and Z (6)
- uniform scale `±0.25%` (2)

Any label that changes under plausible perturbations becomes `manual_review` or
`unobservable`, with the changing features retained in the report.

## Deferred outputs

Write under `Scripts/outputs/tif_defects/<configuration-hash>/`:

- `manifest.json`
- `registration_raw.json`
- `registration_segmented.json`
- registration overlay images
- `struts.csv`
- `struts.jsonl`
- `summary.json`
- candidate top/side projections
- axial-profile plots
- `validation.json`
- `validation.md`

The configuration hash must include input hashes, transforms, thresholds, radii,
code/config version, and coordinate convention.

## Deferred fail-fast validation

Each major component requires at least 10 independent checks. Planned gates:

1. existing 128 Task 1–3 checks
2. component/backward-compatibility checks
3. volume I/O: at least 12
4. graph parsing/welding: at least 12
5. registration: at least 12
6. ROI extraction: at least 12
7. feature calculation: at least 12
8. classifier: at least 16
9. reporting: at least 10
10. end-to-end pipeline: at least 12

Synthetic fixtures:

- deterministic seed `20260724`
- no larger than `96³`
- known present, absent, severed, boundary-truncated, low-contrast, and
  registration-perturbed struts

Real-data checks:

- 12 high-confidence interior struts spanning six design orientations
- more than 96 perturbed ROI detections derived from those cases
- 60 untouched-strut smoke sample
- raw-only, segmented-only, and paired-source modes
- full paired traversal of all 18,468 expected struts only after every earlier
  gate passes

Resource/determinism gates:

- smoke-test RSS growth `≤512 MiB`
- full-run RSS below `2.5 GiB`
- repeat numerical outputs within `1e-6`
- normalized report bytes identical across repeated runs

If any gate fails, stop, fix the current stage, and rerun all earlier stages.

## Explicitly not authorized by this document

- No implementation merely because this file exists.
- No tuning to reproduce the paper's aggregate percentages.
- No claim that the segmented TIFF is hand-labeled truth.
- No hard-coded 3-degree transform.
- No training a 3D CNN, GNN, LLM, or RL policy before a validated geometric
  baseline and adequate labels exist.
- No modification to MCP code or `src`/`src2` without a separate request.

## Completion status

- [x] Design archived as a separate Markdown document.
- [ ] Registration optimizer implemented.
- [ ] ROI extractor implemented.
- [ ] Feature extractor implemented.
- [ ] Five-state classifier implemented.
- [ ] Full raw/segmented inspection executed.
- [ ] Detector scientifically validated.

All unchecked work remains deferred.
