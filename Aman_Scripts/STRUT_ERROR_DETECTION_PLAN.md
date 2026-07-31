# Direct STL-to-TIFF Strut Comparison Plan

## Objective

Compare the expected geometry in `data/missing_struts/stls/0.5.stl`
directly with material observed in the native-resolution raw CT TIFF.  The
registered JSON is used only to enumerate stable strut IDs, provide endpoint
coordinates in the CT frame, and carry results into a visualization-compatible
JSON file.  The example 3D screenshot is not an input and no new 3D viewer is
part of this implementation.

## Pipeline

1. Recover the STL-to-native-CT transform using the existing design/registered
   JSON correspondence, the established STL axis mapping, and the paper's
   physical `4.56 mm` cell edge (`2.28 mm` per graph coordinate unit).  Do not
   derive centreline scale from the STL outer-surface bounding box, which
   includes approximately one extra strut diameter.
2. Read and spatially index every STL triangle without decimation.  Use
   `0.stl` only as a CAD identity reference: the differential surface coverage
   between `0.stl` and `0.5.stl` resolves which graph IDs the monolithic
   `0.5.stl` intentionally omits.  The physical inspection remains exclusively
   `0.5.stl` versus the TIFF.
3. For each registered strut, query only nearby transformed `0.5.stl` surface
   evidence and form an axial expected-material profile.
4. Sample the raw TIFF at the same native CT coordinates and form a realized
   axial profile using a three-threshold ensemble.
5. Measure STL-to-CT realization, the longest unsupported run, and 3D material
   continuity.  Repeat with small alignment perturbations.
6. Save all source junctions, struts, and unit cells, adding a nullable binary
   `has_error`, validity/review fields, confidence, endpoints, and numeric
   evidence to each strut record.

## Fixed Defaults

- Native TIFF resolution only; no downsampling.
- All `0.5.stl` triangles; no mesh decimation.
- Physical graph scale: `2.28 mm/design unit`; nominal strut diameter:
  `0.424 mm`, both from Fisher/Tran et al.
- CT thresholds: `38557`, `40054`, `41018`.
- STL-to-CT spatial tolerance: `2.0` native voxels.
- Endpoint exclusion: `10%` at each junction.
- Supported axial bin: at least `20%` of its STL samples realized by CT.
- Error gap: at least `3` consecutive native-voxel axial bins.
- Minimum realized fraction: `80%`.
- Minimum threshold/alignment agreement: `80%`.

## Fail-Fast Gates

- Validate exact XYZ-to-ZYX conventions, transform residuals, source hashes,
  graph references, and TIFF memory mapping before comparison.
- Pass at least 20 synthetic/adversarial tests before reading every real strut.
- Require exactly 18,468 unique source strut records in the full output.
- Treat cropped, unstable, or otherwise unobservable comparisons as
  `has_error: null`, never as healthy.
- Stop the full run if peak resident memory exceeds 2.5 GiB or any earlier
  validation gate fails.

## Out of Scope

- No missing-versus-broken subtype.
- No MeshLab or other 3D visualization generation.
- No MCP, `src`, or `src2` edits.
- No paper-total tuning or claim of manually confirmed ground truth.

## Completion Log

- [x] Corrected plan saved before implementation.
- [x] Reusable STL spatial index implemented. It retains all original
  triangles, uses exact point-to-triangle distances after spatial candidate
  lookup, performs no decimation, and passed its focused tests.
- [x] CAD identity calibration implemented. Streaming every triangle from
  `0.stl` and `0.5.stl` produces a clean, unforced cluster of **94** strut IDs
  intentionally absent from `0.5.stl`; those IDs are not treated as physical
  TIFF defects.
- [x] Native TIFF comparator implemented with native XYZ/ZYX coordinates,
  unique-voxel cross-sections, axial realization, three intensity thresholds,
  ±1-voxel translation trials, longest-gap evidence, and one central-threshold
  26-connected bridge test.
- [x] Visualization-compatible augmented JSON writer and command-line entry
  point implemented. Source junction/strut/unit-cell records are preserved;
  comparison evidence cannot overwrite source identity or endpoint fields.
- [x] **139 tests pass** in the DSC environment. These cover decision
  boundaries, synthetic missing/gapped/shifted/noisy struts, coordinate order,
  real asset contracts, full-triangle indexing, CAD omission clustering,
  deterministic JSON, malformed inputs, and identity-overwrite attacks.
- [x] A first real 10-strut smoke run completed. It exposed sparse reverse STL
  ownership and an inherited scale error, so that output was rejected rather
  than promoted.
- [x] Registration scale corrected from the invalid outer-bounding-box value
  `2.3052 mm/unit` to the paper/design value `2.28 mm/unit`. The STL X/Z outer
  extents then differ from the expected centreline span plus the `0.424 mm`
  strut diameter by only `0.0288` and `0.0316 mm`.
- [x] Sparse STL radius inference replaced with exact queries over all
  `3,498,656` specimen triangles. In the corrected 10-strut smoke run, measured
  radii were `3.32–3.58` voxels around the physical `3.6718`-voxel radius;
  **7** were stable matches, **3** were conservatively undecided, and peak RSS
  was **1.50 GiB**.
- [x] Corrected 500-strut smoke run completed in **39.13 s** at **1.29 GiB**
  RSS: **425 stable matches, 34 error candidates, 40 review/undecided, and 1
  intentionally absent/not-applicable**. This is a diagnostic prefix, not a
  final accuracy claim or representative defect rate.
- [x] Native full-resolution CT X-band diagnostic added and run. Local Otsu
  thresholds across the lattice-bearing X range were `39,498–40,703`, covered
  by the three-threshold ensemble; the far-X material fraction falls with the
  specimen boundary rather than demonstrating that a lower threshold should
  be inserted blindly.
- [ ] Finish and test the solid-skin observability gate. The helper identifying
  struts geometrically embedded in the two skin planes has been added, but was
  **not yet connected to the final pipeline when work paused**.
- [ ] Add stratified real-data checks across lattice position/direction and
  validation controls from the 94 known CAD omissions. These controls must be
  reported as sensitivity evidence only and must not tune final counts.
- [ ] Full 18,468-strut comparison completes within resource gates.
- [ ] Final artifacts and limitations documented.

### Current stop point

Do **not** treat either smoke JSON as the finished defect map. The executable
pipeline is substantially implemented and its core tests pass, but the
skin-observability integration, stratified real checks, final full run, and
final artifact audit remain open. No missing-versus-broken subtype or 3D
visualization has been implemented.

## Continuous Audit Protocol

This document is the authoritative implementation ledger for the remainder of
the work. It is updated **before** starting each phase with the intended change,
why the change is necessary, its acceptance tests, and its possible failure
modes. It is updated **after** each phase with commands run, observed numbers,
artifacts produced, failures found, and the decision to accept, revise, or
reject the change. A passing test count alone is not treated as evidence of
scientific validity.

The detector is intentionally allowed to return `has_error: null`. A second
agent attempting to disprove the result should be able to distinguish:

1. an automatically supported mismatch candidate (`true`),
2. a stable expected-versus-observed match (`false`),
3. an unstable or unobservable comparison (`null` with review required), and
4. geometry that is not independently inspectable (`comparison_applicable:
   false`, such as a source edge embedded in a solid skin).

Every future result must state which of these populations its counts include.

## Remaining Implementation Phases

### Phase A — Solid-skin observability

**Why it exists:** the two solid skins geometrically absorb struts lying wholly
in their boundary planes. CT cannot determine whether such a strut exists as an
independent member because the surrounding skin is also material. Calling it
healthy would be a false certainty.

**Implementation:** derive the two skin planes from the design graph rather
than hard-coding source IDs. Preserve all original records, but mark members
whose two design endpoints lie in either skin plane as not independently
applicable. CAD-omitted status remains a separate field.

**Acceptance evidence:** unit tests for lower skin, upper skin, one-endpoint-only
members, invalid axes/tolerances, and the real graph count. Verify the three
previously noted CAD-omitted skin members are contained in the derived set.

### Phase B — Deterministic image-based detector tests

**Why it exists:** scalar assertions can hide a geometrically nonsensical
sampling corridor. Each synthetic case will therefore produce a review image
showing the CT maximum projection, the expected STL centerline/corridor, the
axial material profile, and the classifier result.

**Images are not generated by an image model.** They are rendered directly
from deterministic 3D arrays with known voxel ground truth, ensuring that every
pixel and expected answer can be recreated. Planned cases include:

- intact axial and oblique struts;
- completely missing and mid-span broken struts;
- endpoint disconnection;
- one-voxel pinhole;
- within-tolerance and beyond-tolerance lateral shifts;
- thin and thick continuous members;
- random bright speckles;
- a nearby parallel member without the target member;
- global intensity scaling and a spatial intensity gradient;
- threshold disagreement;
- field-of-view truncation.

**Acceptance evidence:** at least 12 labeled cases, a PNG contact sheet plus
individual PNGs, a JSON manifest recording parameters and outcomes, and an
automated test that fails if an expected label changes. The images will be
opened and inspected after generation; visual findings and any resulting
parameter changes will be recorded below.

### Phase C — Stratified real-data and known-omission controls

**Why it exists:** the first 500 source IDs overrepresent one boundary layer.
A prefix smoke test cannot establish spatial robustness.

**Implementation:** select deterministic controls across lattice X/Y/Z,
orientation, boundary/interior status, and CAD-present/CAD-omitted state. The
94 omissions inferred from `0.stl → 0.5.stl` may be used only as a sensitivity
control by asking whether a complete-design corridor appears absent in CT.
They must not be inserted as final `0.5.stl → TIFF` defect labels or used to
force thresholds. Report control AUC/sensitivity, stable-negative rate, review
rate, and position-stratified results.

**Acceptance evidence:** control IDs and selection rules saved in JSON; at
least 10 cases from each relevant population; no single spatial prefix; results
reported even if they fail the gate.

### Phase D — Full comparison and artifact audit

**Why it exists:** only the all-strut execution can prove output completeness,
determinism, memory compliance, and compatibility with the later 3D viewer.

**Acceptance evidence:** exactly 18,468 augmented source records, no overwritten
identity fields, all endpoints finite and in the documented XYZ/ZYX frames,
strict JSON serialization, consistent summary counts, peak RSS below 2.5 GiB,
two identical output hashes on repeated deterministic runs (excluding runtime
telemetry), and a final rerun of every automated and image-based test.

## Live Phase Status

- **Phase A complete:** the pipeline
  now derives skin-embedded IDs from design-Z boundary planes, writes
  `skin_embedded` and `cad_intentionally_absent` separately, assigns
  `comparison_applicable: false` and `has_error: null`, and excludes those
  records from healthy/error/undecided populations. Twenty-one focused tests
  verify lower/upper planes, one-endpoint and interior counterexamples, axis and
  tolerance validation, malformed graphs, ordering, and real data. The real
  graph contains **648** such source records (**324 per skin**); CAD-omitted
  IDs `170`, `1223`, and `1465` are derived members of the lower design-Z skin.
  Combined suite after integration: **160 passed in 1.57 s**.
- Phase A real smoke rerun: the first 500 source records completed in **41.51
  s** at **0.87 GiB** measured peak RSS. Counts were **343 stable matches, 34
  error candidates, 39 applicable-but-undecided, and 84 not applicable** (83
  skin-present plus one CAD-omitted skin member). All 84 not-applicable records
  had `has_error: null`, `review_required: false`, and preserved identities;
  no not-applicable record leaked into the healthy/error/undecided totals.
- The console and metadata now call the `3.33e-12`-voxel residual a
  **design-JSON → registered-JSON control-point fit**, not independent image
  registration accuracy.
- **Next:** implement and inspect Phase B before changing any further detector
  thresholds.
- **Do not yet run Phase D:** the full output remains blocked on Phases A–C.

### Phase B intermediate evidence — not yet closed

The first deterministic visual suite generated **18 individual PNGs**, one
contact sheet, and a strict manifest. Automated rendering/manifest tests passed
(`3 passed in 13.10 s`), and all 18 expected detector outcomes matched: 8
healthy, 8 error, and 2 review/null.

Main-agent visual inspection (not only automated image statistics) confirmed:

- the seven-voxel lateral shift is separated from the cyan expected line in XY
  and YZ while appearing coincident in XZ, exactly as coordinate geometry
  predicts;
- the oblique mid-span void is visible in all applicable projections and
  coincides with seven unsupported axial bins;
- threshold disagreement has intact geometry but a null/review decision;
- field-of-view truncation visibly clips the expected member and produces no
  valid axial profile;
- speckles, endpoint blobs, and a distant parallel neighbor do not fabricate a
  continuous target profile.

This suite is **not accepted as sufficient yet**. The existing intensity
gradient remains entirely above all thresholds, and the parallel neighbor is
comfortably outside the target corridor. Two harder counterexamples must be
added before Phase B can close:

1. an intact, smoothly varying member whose intensity crosses the threshold
   ensemble (it must not become a confident physical-break claim); and
2. a close parallel neighbor whose material approaches/enters the tolerance
   corridor while the target itself is absent (testing false support from
   unowned CT voxels).

If either produces an incorrect confident binary result, the failure and its
image remain in the manifest while the algorithm is revised; expected truth
must not be edited to make the test pass.

#### Phase B failure F1 — smooth intensity gradient falsely called broken

The extended suite produced **19/20 matches**. The close parallel-neighbor case
remained a correct error, but case `19_gradient_crosses_thresholds` failed:

- physical geometry: continuous radius-two cylinder;
- intensity: smooth `80 → 120`, background `0`;
- thresholds: `90, 100, 110`;
- expected conservative response: review/null;
- actual response: confident error (`confidence=0.913`);
- central realized fraction: `0.5185`;
- reported gap: `13` bins;
- perturbation agreement: `1.0`;
- failure-image SHA-256:
  `bbce84bb9316419ce53c55ca8aa94e873ff90368371e9f1864ac65c4050cac1c`.

Visual inspection shows uninterrupted material along the cyan expected line;
the binary axial profile changes exactly where the smooth intensity crosses
the central threshold. The threshold ensemble agrees on the broad low-intensity
region and therefore cannot detect this shared systematic failure.

**Planned correction before code change:** calculate, for each axial bin, the
intensity of the weakest voxel needed to meet the existing 20% material-area
requirement and compare it with the median intensity in that same expanded
cross-section. If every/most bins retain continuous local contrast even though
the absolute threshold profile claims a break, downgrade `has_error: true` to
review/null with reason `subthreshold_continuous_contrast`. This secondary
evidence may only remove false certainty; it must never promote an otherwise
missing strut directly to healthy. Initial fixed contrast fraction is `0.25` of
the central-threshold-to-local-background gap.

**Correction acceptance gates:** case 19 becomes review, all established true
gaps/missing/shift/neighbor/noise cases remain error, all established intact
cases remain healthy or review as specified, support intensity/background
profiles are serialized for audit, and the complete non-visual plus visual
suites pass without editing expected labels.

#### Phase B correction F1 implementation — awaiting verification

The planned safeguard has now been implemented in
`Components/strut_comparison.py`, but it is deliberately **not accepted yet**.
For each valid axial cross-section, the comparator records:

- the support intensity: the weakest of the brightest unique voxels needed to
  satisfy the existing minimum material-sample requirement;
- the local background: the median intensity in the expanded cross-section;
- a normalized local-contrast fraction relative to the central absolute
  threshold.

Those contrast values form a second axial support profile with a fixed initial
minimum of `0.25`. The correction is asymmetric by design: when the absolute
threshold classifier says `has_error: true` but local contrast remains
continuous, the result is downgraded to `has_error: null`,
`comparison_valid: false`, and `review_required: true`. It retains both the
original absolute-threshold decision and its reason as audit fields. Local
contrast is **not allowed to promote any candidate to healthy**, so a nearby
member, noise, or a completely missing target cannot become a false negative
through this safeguard.

Additional serialized evidence includes the support-intensity,
local-background, normalized-contrast, and contrast-support profiles, plus the
central contrast realized fraction. An empty exact-surface query was also
guarded explicitly so it cannot emit a NaN through `np.max`.

**Verification now starting:** first run the complete non-visual suite; then
regenerate all 20 deterministic images without permitting mismatches; then run
the visual artifact tests and manually inspect the regenerated failure image
and contact sheet. If a true missing/gap/neighbor case is downgraded, or case 19
remains a confident defect, stop and revise this correction before Phase C.

#### Phase B correction F1 verification result

The correction passed its initial gates without changing any expected label:

- complete non-visual suite: **160 passed in 1.51 s**;
- deterministic generation: **20/20 outcomes matched**, zero permitted
  mismatches;
- PNG/manifest suite: **3 passed in 13.71 s**;
- case 19 changed from the preserved false error to review/null with
  `decision_reason: subthreshold_continuous_contrast`, confidence `0.0`, while
  retaining the absolute profile (`realized_fraction=0.5185`, gap `13`) as
  evidence;
- case 20 remained an error despite the close parallel member
  (`realized_fraction=0.0`, gap `27`);
- fully missing, mid-span gap, and endpoint-blobs-only cases all remained
  errors.

The regenerated case-19 SHA-256 is
`208aa9c7aa16aebcd5381f68bd98200accf70acc165bf1cc206ccf4ab1b5ba44`;
case 20 is
`494c73255f2fd463e7335895fafb01cf2a3c2f5aebdcd5e050e0951522c3c3c9`.
The original failing case-19 hash remains documented above, so the correction
is externally distinguishable from changing the expected answer.

Manual inspection of the regenerated images confirms that case 19 contains a
continuous white member on the cyan centerline even though its magenta
absolute-threshold profile switches at bin 13. Case 20 instead shows the white
member offset above the cyan target line and no realized target bins. The
contact sheet shows no red failure banner and preserves the visibly genuine
gaps in cases 4, 5, and 17.

One auditability improvement remains before closing Phase B: the case image
currently plots the absolute binary profile but only states the contrast-veto
reason in text. The renderer should overlay the serialized local-contrast
support profile when present, so another reviewer can see exactly which
evidence caused the downgrade. Focused non-visual tests must also exercise this
new branch directly rather than relying only on the rendered scenario.

The same fixed parameter must be wired through the production pipeline and
command line as `minimum_local_contrast_fraction` /
`--minimum-local-contrast-fraction`, validated in `[0, 1]`, and written into
the output metadata. This does not introduce adaptive tuning: the default
remains the predeclared `0.25`, and Phase C controls may reject it but may not
silently optimize it on the same sample. The summary text must distinguish
skin-unobservable records from intentionally absent CAD records, because both
are non-applicable but for different physical reasons.

That integration is now implemented and awaiting regression verification. The
behavioral algorithm identifier was advanced from
`native-surface-corridor-v1` to `native-surface-corridor-v2`; the output schema
remains `stl-tiff-strut-error-map.v1` because no existing source identity or
nullable-decision semantics changed. The visual renderer now plots a green
dotted local-contrast support profile beside the magenta absolute-threshold
profile, and its text reports the contrast realized fraction. A separate
20-test focused safeguard file was added by an independent test agent; its
isolated run passed, but the authoritative combined rerun is still required.

#### Phase B failure F2 — first local-contrast veto is too permissive

An independent adversarial audit disproved the first correction even though
the original 20 images passed. Phase B is therefore **reopened and blocked**.
The following counterexamples must remain visible in this ledger:

1. A real eight-bin gap plus a faint axial halo at exactly `0.25 ×` the central
   threshold was downgraded from error to review. The same occurred for a faint
   nearby parallel member at small offsets. Because `error_candidates.csv`
   currently contains only `has_error: true`, such a downgrade can be missed by
   a reviewer who ignores the full JSON.
2. Three faint voxels in every axial bin, intentionally placed in alternating
   disconnected positions, produced 34 separate 26-neighbour components but
   still activated the veto. The first correction evaluated per-bin counts and
   hard-coded the contrast evidence as connected and perfectly stable.
3. The smooth `80 → 120` intact gradient was handled at radii 2–2.5 voxels but
   reverted to a false error at radii 3–4. The median of the same sampling disk
   is not a valid background estimate when a thick member occupies more than
   half that disk.
4. Allowing a contrast fraction of zero was degenerate: zero-intensity empty
   space satisfies `0 >= 0` and could downgrade a completely missing member.
5. The normalized fraction had no absolute contrast/noise floor and could
   become arbitrarily large as the local background approached the central
   threshold from below.
6. The first correction calculated contrast only at the central registration
   shift, so its downgrade lacked the seven-shift stability evidence required
   of the absolute classifier.
7. The image renderer has since gained the green contrast profile, but the
   manifest's selected metrics still omit the new audit fields and must be
   expanded.

The direct combined runner passed **180 tests in 1.74 s**, and the isolated
20-test safeguard file passed in **0.44 s** when third-party pytest plugin
autoload was disabled. A redundant direct pytest invocation without that
isolation failed before test execution because napari attempted to write its
theme cache outside the workspace; this is an environment error, not counted
as a detector pass or failure. The regenerated visual suite remained 20/20 and
its three artifact tests passed, but these successes are insufficient in light
of the counterexamples above.

**Replacement design before implementation:** remove the count-only contrast
veto. Estimate background from an annulus outside the expected member rather
than the target disk. A downgrade may occur only if the lower-intensity
candidate material forms a 26-connected path through the target corridor,
supports the axial body, exceeds both a positive normalized-contrast cutoff and
an absolute robust-noise/SNR floor, and remains a healthy contrast decision
across the same seven ±1-voxel registration shifts. This evidence remains a
one-way error→review veto and can never produce healthy. A separate review CSV
must ensure downgraded cases are operationally visible.

**New mandatory attacks:** faint halo sweep around the cutoff, disconnected
per-bin voxels, faint-neighbor offset sweep, radius-2-through-4 gradients,
background-near-threshold/noise sweeps, zero/epsilon parameter boundaries,
seven-shift instability, dense-background/junction cases, and manifest checks
for every new audit field. The replacement must pass all established cases and
these attacks before Phase C.

#### Phase B correction F2 replacement specification — frozen before code

The replacement will live in a separate component so
`strut_comparison.py` does not grow past 1,000 lines. It runs only after the
absolute comparator produces `has_error: true`; therefore ordinary healthy
struts pay no added connected-component cost.

For expected radius `r`, body centerline `p(s)`, and each registration shift
`d ∈ {0, ±x, ±y, ±z}`:

- core tube: radial distance `ρ(x, p+d) ≤ r + 0.75` voxels;
- guarded background annulus: inner radius `r + 2.0` and outer radius
  `r + 2.0 + max(2.0, r)`. The two-voxel guard covers the one-voxel
  perturbation and one additional voxel, preventing the target member from
  defining its own background;
- for every axial bin, annular background `B` is the median and raw noise is
  `1.4826 × MAD`. A bin requires at least 24 annular voxels and is invalid if
  over 20% of them already exceed the central material threshold `T`;
- effective noise is the maximum of bin MAD, pooled median MAD, and a fixed
  floor derived from image quantization plus 5% of the threshold-ensemble
  span;
- adaptive lower threshold is
  `L = B + max(alpha × (T-B), 5 × effective_noise)`, initially
  `alpha=0.25`. It is usable only when `0 < alpha ≤ 1`, `B < T`, and `L < T`.

Voxels inside the core tube and above their bin's `L` form a low-threshold
mask. A review veto requires one **actual 26-connected component** that:

1. intersects the first and last 10% body bands;
2. contains above-`T` seed voxels in at least three (or 10% of) axial bins;
3. supplies at least `ceil(0.20 × πr²)` voxels in at least 80% of bins; and
4. leaves no unsupported run of three or more bins.

At least 95% of annular bins must be valid. The central shift must pass, at
least six shifts must be valid, and at least six of seven shifts must pass.
Only then may the absolute error become review/null. The complete per-shift
outcomes, connected support profile, annular background/noise/contamination,
adaptive thresholds, and original absolute decision will be serialized.

This is deliberately hysteresis, not a second global segmentation: high
threshold voxels anchor a lower-threshold path. A real gap containing a
noise-significant, 26-connected faint reconstruction bridge remains physically
ambiguous and must be review/null; no intensity-only method can honestly prove
whether that bridge is partial-volume artifact or residual metal. The new
review-candidates CSV ensures such cases are never hidden merely because they
are not in the confirmed-error CSV.

#### Phase B correction F2 implementation — initial gates only

The frozen replacement is implemented in
`Components/local_contrast.py` and integrated into
`Components/strut_comparison.py`. It runs only for an absolute error. The
production algorithm identifier is now `native-surface-corridor-v3`; zero is
rejected as a contrast fraction, and `None` (exposed by
`--disable-local-contrast-review`) is the explicit disable state. Full runs now
write both `error_candidates.csv` and `review_candidates.csv`.

Initial regression evidence:

- updated focused safeguard suite: **22 passed in 0.56 s**;
- complete non-visual suite: **182 passed in 1.90 s**;
- original visual suite: **20/20 matched** after replacement;
- case 19 now records an actual connected low-threshold component, high-
  threshold anchors, **7 valid / 7 passing shifts**, annular background/noise,
  adaptive thresholds, and a `0.963` connected-support fraction;
- its image visibly overlays the green connected-support profile over the
  magenta absolute profile. One native sampling bin has no usable annular
  cross-section, producing a one-bin green interruption; this remains below
  the declared three-bin gap and leaves 26/27 (`0.963`) valid bins.

These are not closure evidence. Independent agents are adding the mandatory F2
counterexamples as both scalar tests and deterministic images. Phase C remains
blocked until those results are generated, opened, and analyzed.

The scalar adversarial expansion is now complete: **27 new attacks passed in
1.35 s**, and the authoritative combined suite is **216 passed in 2.92 s**.
It verifies disconnected faint triplets, radius-2/3/4 gradients, a 24/25/26/35
faint-gap bridge sweep, faint-neighbor offsets 1–6, backgrounds at 90/95/99,
threshold-adjacent seeded noise, zero and epsilon contrast boundaries, actual
6-of-7 shift accounting, contaminated annuli, oblique gradients/gaps, strict
JSON, and determinism. The important scientific outcome is conservative:
connected significant faint material through a nominal gap becomes review,
never healthy; disconnected or sufficiently separated artifacts remain an
error. Seven additional tests verify that confirmed-error and review CSVs are
disjoint and that the CLI rejects degenerate contrast settings.

The image expansion and manual pixel inspection are still pending, so Phase B
is not yet marked complete.

#### Phase B closed — adversarial image evidence accepted

The main agent independently regenerated the expanded suite and reproduced:

- **26/26 expected outcomes**, zero mismatches, all PNG checks true in 5.14 s;
- **6 visual artifact tests passed in 34.68 s**;
- strict manifest SHA-256
  `a0eeaa388c7c2eb2125f908e1d05f2831e66113f9a87e1bc47689700ce408c9d`;
- contact-sheet SHA-256
  `3a378149f290416b152eed83d5e34da2da948e340460f5a6acb40ff710f71259`.

All six new originals and the complete contact sheet were opened manually:

- case 21 visibly shows a continuous radius-four gradient; the green connected
  path survives all 7 shifts and the result is review, proving the prior
  thickness-dependent failure is corrected;
- case 22's XY view shows alternating separated faint samples while its XZ
  maximum projection misleadingly looks continuous. The 3D path test correctly
  reports no connected support and retains error—an explicit demonstration of
  why a 2D projection alone is unsafe;
- case 23 visibly contains a dark continuous bridge across a bright gap. Its
  7/7 stable path produces review rather than healthy, matching the stated
  physical ambiguity;
- case 24's labeled `[99.4, 99.5]` display range makes the near-threshold texture
  visible, while the SNR/path gate retains error;
- case 25 visibly shows a bright hollow annulus with an empty target core; zero
  shifts are valid and the result remains error;
- case 26 shows an intact oblique gradient in all three projections and a 7/7
  connected path, producing review.

No case has a red mismatch banner, and the original cases 1–20 were not edited.
Phase B is now **complete**. This validates deterministic synthetic behavior and
failure safeguards; it does not establish physical accuracy on the real part.
Phase C real-data controls are now permitted.

### Phase C frozen protocol — written before implementation

Phase C is a retrospective weak-label control on this one physical specimen,
not external validation. Its labels come only from the current all-triangle
`0.stl → 0.5.stl` CAD differencing object already produced by this pipeline.
An independently supplied collaboration list also contains 94 alleged removed
IDs, but its intersection with the current 94 IDs is **zero**. Importing it
would mix incompatible registrations/identity mappings and invalidate the
experiment, so the implementation must reject all external removal lists.

Verified feasibility for the current mapping:

- 94 CAD omissions total;
- three skin-unobservable positives (`170`, `1223`, `1465`);
- 91 evaluable weak positives and zero of those outside the padded TIFF FOV;
- two unique matched CAD-present controls per evaluable positive = 182
  negatives and 273 evaluated rows total;
- exact matching remains feasible: 80 occupied positive strata, at least 16
  eligible candidates for every positive, and at least 15 surplus candidates
  in the tightest group after assigning two controls each.

The CT-free manifest must be built and atomically written **before TIFF
intensities are read**. Each positive receives two globally assigned negatives
that match exactly on canonical undirected design orientation, boundary class,
X/Y/Z design-space tertiles, and padded FOV eligibility. Negatives must be CAD
present, non-skin, source ID ≥500, globally unique, and share no welded physical
endpoint position with their positive. Matching uses sorted inputs plus a
global linear assignment minimizing design-midpoint distance and complete-STL
coverage difference; it may not inspect TIFF intensity, specimen-STL coverage,
detector results, confidence, prior candidate lists, or collaboration labels.

Both positive and negative controls are compared against nearest surface
samples retained from the **complete `0.stl`**. Using complete geometry only for
positives would leak the label through the reference. Retaining 18,468 × 45 × 3
float32 points costs about 9.5 MiB, so a second complete-STL spatial index is
forbidden. These arrays must be released before constructing the much larger
specimen-STL exact-triangle index.

The frozen continuous raw threshold-evidence score is:

`max((1 - realized_axial_fraction) / 0.20,
     longest_unrealized_gap_voxels / 3)`.

Score `1` is the current hard-error boundary. The report must include tie-aware
ROC AUC, worst-case missing-score AUC bounds, decidable and conservative
positive sensitivity, decidable and conservative negative stable-match rate,
review rates, positive-versus-each-matched-negative win rate, Wilson intervals,
and the same positive metrics by orientation, boundary class, and XYZ tertile.
Raw-score AUC and final ternary decisions must both be reported because the
annular safeguard can turn an absolute error into review without altering the
raw score.

Predeclared pass gates (no retuning on these controls):

- AUC ≥0.90;
- decidable positive sensitivity ≥0.90;
- decidable matched-negative stable rate ≥0.90;
- review rate ≤0.10 for each class;
- conservative positive capture and conservative negative stable rate ≥0.80;
- pairwise win rate ≥0.85;
- every stratum with at least 10 positives has conservative sensitivity ≥0.75.

Any failed gate stops the pipeline before the full 18,468-strut run and remains
in the report. The manifest/report bind algorithm version, exact transform,
input hashes, current omission-ID hash, comparator parameters, selection rules,
and manifest content hash. The complete STL's role in metadata will be updated
to “CAD identity calibration and frozen control validation”; final production
classification remains strictly `0.5.stl → TIFF`.

Exact frozen feature formulas are now fixed. With design bounds `[0,18]³`, an
edge is `boundary_endpoint` if either endpoint touches any bounding face within
`1e-8`; otherwise it is `near_boundary` when its midpoint is within 2 design
units of any face, else `interior`. This reproduces 5,412 / 5,412 / 7,644
records. Axis tertiles are `[0,6)`, `[6,12)`, and `[12,18]`, reproducing
6,048 / 6,048 / 6,372 records per axis. Undirected orientation flips the design
vector so its first nonzero XYZ component is positive, removes negative zero,
and stores one of six integer keys.

FOV eligibility mirrors the actual comparator crop: in CT XYZ, with nominal
radius `3.6717665`, corridor radius `5.6717665`, and padding `6.6717665`, every
axis requires `floor(min(endpoint)-padding) ≥ 0` and
`ceil(max(endpoint)+padding)+1 ≤ shape`. Matching cost is squared design-
midpoint distance plus `0.1 ×` absolute complete-STL coverage-quality
difference and a `1e-9` deterministic candidate-rank tie break; forbidden
shared-welded-node pairs receive a sentinel cost and are rejected after global
assignment.

Implementation has begun by adding an opt-in complete-STL station-retention
flag and moving the specimen triangle index after the future control gate. Five
stubbed tests pass in 0.08 s: only the complete STL receives the retention flag,
the specimen mapping always remains non-retaining, both calls share the exact
atlas/transform/sampling controls, and omission inference receives the original
atlas IDs. The broader suite remains **216 passed** after this sequencing
change. The pure manifest/metric implementation is not yet accepted until its
own tests and main-agent review finish.

#### Phase C pre-implementation correction C1 — stricter FOV padding

An integration audit found that the originally frozen `6.6717665`-voxel FOV
padding exactly covers the absolute-threshold corridor but not the new guarded
annular fallback. Its maximum local radius is
`r + 2 + max(2,r) + 1 = 10.3435330` voxels for the nominal radius. The manifest
will therefore record both values and use the stricter **10.3435330-voxel**
padding for eligibility/matching. This change is made before reading CT or
evaluating controls; it cannot be a response to detector outcomes. The real
manifest must re-prove that all 91 positives and all selected negatives remain
eligible, rather than assuming the earlier feasibility result.

The audited event order is also mandatory: TIFF header only → registration and
CAD mapping → atomic CT-free manifest → TIFF mapping/histogram → 273 complete-
STL control comparisons → atomic report → gate decision → release complete
arrays → specimen triangle index → production loop. On failure, the report must
still exist and the index/checkpoint/full output must never start.

#### Phase C implementation checkpoint C2 — validator handoff (before integration)

The isolated control-manifest/statistics component has now been delivered, but
it is **not yet accepted into the production pipeline**. The handoff reports:

- `Components/strut_control_validation.py`: 993 lines;
- `StrutComparisonTests/test_strut_control_validation.py`: 453 lines;
- 28 focused tests passed and 249 tests passed in the contributor's broader
  run;
- the real graph fixture reproduced 94 CAD omissions, three skin-hidden IDs,
  91 evaluable positives, and 182 unique matched negatives at the corrected
  10.343533-voxel selection padding;
- the real feasibility fixture intentionally used uniform complete-STL
  coverage, so it establishes graph/FOV/matching feasibility only. It does not
  prove that measured complete-STL quality produces the same matching or that
  the CT detector passes the frozen gates.

Before any production integration edit, the main implementation will now:

1. read the complete component and test file, not just trust the handoff;
2. independently rerun syntax, focused, and complete tests;
3. red-team the matching, provenance seals, tie/missing-score statistics,
   aligned pairwise calculation, powered-stratum gate, and deterministic output;
4. reject the component or correct it if a concrete counterexample is found;
5. only after those checks, add a separate control runner plus ordering tests,
   keeping every source file below 1,000 lines.

The integration will be fail-closed. In particular, a report write is not a
successful gate: the specimen index may be constructed only after the report
has been atomically written **and** all frozen gates pass. A dedicated
`--control-only` execution path may stop after a passing gate for low-memory
validation, but there will be no option that bypasses the gate on a production
run.

#### Phase C audit finding C3 — green tests missed a frozen gate

The main-agent source review found a release-blocking omission before pipeline
integration. The component computes stratified metrics, but `DEFAULT_GATES`
and `summarize_control_results()` contain only the eight aggregate gates. They
do **not** enforce the ninth predeclared rule: every stratum containing at least
10 inspectable positives must have conservative positive sensitivity at least
0.75. Consequently, a result could pass globally while failing badly for one
orientation, boundary class, or spatial tertile. The contributor's 28 focused
tests and 249-test full run did not contain this counterexample.

This is evidence that passing tests alone are not acceptance. Before any
integration, the validator must add a distinct powered-stratum threshold,
evaluate all five frozen stratification dimensions, record every powered group
and its outcome, and fail if even one such group fails. Tests must include both
a globally passing / locally failing counterexample and an underpowered group
that is reported but does not control the gate. The original aggregate tests
must continue to pass.

#### Phase C audit findings C4–C8 — pre-CT contract corrections

Further line-by-line and independent integration review found five additional
ways a superficially valid artifact could violate the frozen experiment. These
are recorded before any TIFF intensity is decoded or any real control is
scored.

**C4 — all-shift FOV padding.** The C1 value `10.3435330` is the central
annular crop padding, but the safeguard first shifts the inspected axis by one
voxel in each of ±X/±Y/±Z. Guaranteeing the complete crop for every one of
the seven stability trials therefore requires
`r + 2 + max(2,r) + 1 crop voxel + 1 shift voxel = 11.3435330` voxels.
The final manifest will retain all three named margins—absolute corridor,
central annulus, and all-shift selection—and use **11.3435330** for selection.
Matching feasibility must be recomputed at this final value.

**C5 — score-parameter binding.** The current result summarizer accepts
`minimum_realized_fraction` and `minimum_gap_voxels` independently of the
sealed comparator parameters. That would permit an accidental or deliberate
post-control score redefinition. Evaluation must reject any score parameters
that do not exactly equal the values sealed in manifest provenance.

**C6 — geometry-parameter binding.** The manifest builder currently accepts
radius, distance tolerance, and selection padding without cross-checking the
raw comparator-parameter object whose hash is sealed in provenance. It must
reject a contradiction rather than record two mutually inconsistent truths.
The public FOV helper may remain general, but the frozen manifest builder must
require at least the all-shift annular padding when local-contrast review is
enabled.

**C7 — canonical gate ordering.** Gate-check output currently inherits input
dictionary order. Reading a key-sorted JSON manifest back can therefore change
the result artifact's row ordering/content hash without changing its meaning.
All gate records and powered-stratum records must use an explicitly sorted
canonical order, and a write/read/re-summarize test must produce the same
content hash.

**C8 — derived-result verification.** A sealed result artifact currently has
its hash, manifest binding, provenance, and row IDs verified, but its metrics
and gate decisions are not recomputed from the sealed rows. Because SHA-256 is
a reproducibility seal rather than an authentication secret, someone can edit
metrics, reseal the artifact, and pass that validator. Validation must either
recompute the derived statistics/gates from rows or expose a separate strict
recompute validator that the pipeline and tests always call. A test must alter
a derived value, reseal, and prove rejection.

## 2026-07-28 scope correction: replace validation sprawl with direct metrology

The user correctly challenged the growing implementation surface. The frozen
control-gate branch above is preserved as an audit record, but it is no longer
the active implementation path. No more production integration will be added
to `strut_control_validation.py`. Its green synthetic tests do not resolve the
central physical uncertainty: whether the STL is independently aligned to CT
material closely enough to distinguish a true strut defect from registration
or surface-determination error.

The replacement is intentionally compact and will answer only the requested
binary question for each STL-expected strut: **does this strut have evidence of
an error?** It will not claim missing-versus-broken subtype.

### Minimal active pipeline

1. Use the existing JSON-derived transform only as an initialization, never as
   independent image-registration proof.
2. Estimate a global sub-voxel CT boundary level and refine a small rigid
   STL-to-CT correction directly against sampled TIFF intensities. The optimizer
   must report the before/after objective, correction magnitude, convergence,
   and held-out behavior. It must refuse a large or unsupported correction.
3. For each STL-expected strut, sample native-resolution CT cross-sections along
   its registered centerline. Estimate the local material boundary from
   interpolated intensity crossings rather than voxelizing the complete STL.
4. Retain only a few physically interpretable measurements: axial observed
   fraction, longest unsupported gap, endpoint-to-endpoint connected support,
   median radial signed deviation, P90 absolute radial deviation, and local
   centerline displacement.
5. Make a binary candidate decision only when the mismatch exceeds both a
   declared manufacturing tolerance and the measured registration uncertainty.
   Ambiguous cases remain `null`/review rather than being forced healthy/error.
6. Write one augmented JSON plus a compact registration/measurement report and
   at least ten deterministic inspection panels. The images must show CAD
   centerline/cross-sections and the actual CT evidence used for the decision.

### File-count constraint

This replacement may add at most four Python files: one CLI, two focused
components (registration/surface and per-strut measurement), and one test file.
It will reuse existing TIFF/STL/JSON I/O and reporting helpers. No new classes,
viewer, ML model, dashboard, control-manifest framework, or full-volume STL
voxel mask will be introduced.

### Memory checkpoint before implementation

The 16 GiB Mac reports 37% system-wide memory available, but only about 4,000
immediately free 16 KiB pages and substantial compressor/swap activity. Heavy
full-volume surface extraction or a second dense mask is therefore forbidden.
TIFF access must remain memory-mapped, registration must operate on bounded
point samples, per-strut work must use small local crops, and all heavy tests
must run sequentially under the existing 2.5 GiB process-RSS ceiling.

### Acceptance sequence

Implementation will stop at each failed stage: synthetic sub-voxel boundary
recovery tests → planted rigid-correction recovery tests → healthy/missing/
shifted/thin/low-contrast local strut tests → real registration diagnostic →
ten real inspection panels → only then the full strut run. A test count is not
physical validation; the report must separate synthetic correctness, internal
real-data controls, and unverified real defect claims.

### Simplified implementation log S1 — first gate stopped on import compatibility

The first new component and its initial 13 tests were written, then test
collection stopped before execution: `ct_surface_metrology.py` imported
`tif2stl` as a top-level package, which works when a CLI inserts
`Aman_Scripts/` into `sys.path` but fails when tests import
`Aman_Scripts.Components...`. This is a real packaging defect. The fix is a
dual package/CLI-compatible import of the existing STL streamer; numerical
tests remain unrun until collection succeeds.

The first compatibility attempt exposed a pre-existing limitation in
`Aman_Scripts/tif2stl/__init__.py`: importing it as
`Aman_Scripts.tif2stl` executes absolute `tif2stl.*` imports. Rather than
refactor that older package and expand scope, the new test harness will mirror
all repository CLIs by adding the single `Aman_Scripts/` root to `sys.path`
before importing components. The production component keeps the same
top-level import convention already used throughout `Components/`.

After that correction, the stage passes **13/13 tests in 0.35 s**. The tests
cover exact trilinear interpolation, strict out-of-bounds behavior, 0.25-voxel
surface-crossing recovery, reversed normals, contrast-free rejection, rigid
pivot arithmetic, deterministic area-uniform STL sampling, recovery of a
planted six-degree-of-freedom correction on a smooth rotated box, and failure
when parallel normals or absent CT contrast cannot constrain registration.
This establishes synthetic numerical behavior only; no real registration claim
has been made.

### Simplified implementation log S2 — per-strut component contract

The second component will receive one corrected CAD centerline and its actual
STL-derived radius profile. At one-voxel axial spacing it will construct a
small perpendicular grid, interpolate native TIFF intensities, estimate a
local material/air midpoint, find the observed intensity-weighted center, and
locate radial half-contrast crossings. It will return only:

- observed axial fraction;
- longest unsupported axial gap in voxels;
- continuous endpoint-to-endpoint support at the declared gap tolerance;
- median signed radial deviation and P90 absolute radial deviation;
- P90 centerline displacement;
- per-station evidence needed for ten audit images.

The decision function is separate so changing a tolerance cannot change the
measurement. Declared manufacturing tolerances are expanded by the measured
registration uncertainty. Strong structural/geometric failures become
`has_error=true`; clearly in-tolerance members become `false`; incomplete or
near-boundary evidence becomes `null`/review. The component does not infer
missing versus broken.

The first combined run stopped after 14 passes on the planted axial-gap case.
The measured longest unsupported interval was `3.069230769` voxels: correctly
above the declared 3-voxel error boundary, but below the test's unjustified
`>=4` expectation because station centers discretize the soft gap edges. The
algorithm is unchanged; the test is corrected to require `>3.0`, which is the
predeclared decision threshold it is intended to exercise.

The next run reached 18 passes, then showed that the intended out-of-bounds
fixture was geometrically wrong: an X-directed strut near the X endpoint still
has YZ cross-sections wholly inside the array after endpoint exclusion. The
fixture is moved near the Y boundary so its perpendicular sampling disk truly
leaves the volume. The prior supported result was correct and the production
code again remains unchanged.

At 23 passes, the uncertainty-band test landed exactly on the declared healthy
cutoff: `1.10 = 0.75 manufacturing + 0.60 registration - 0.25 review margin`,
so `false/healthy` was correct. The fixture is changed to `1.20`, strictly
inside the review band and below the `1.35` error limit. This makes the test
exercise ambiguity rather than equality semantics.

After those fixture corrections, the complete compact numerical suite passes
**26/26 tests in 0.45 s**. Source sizes remain bounded: 455 lines for surface/
registration, 414 lines for strut measurement, and 380 lines for the single
test file. `py_compile` and `git diff --check` also pass.

### Simplified implementation log S3 — sole CLI contract

The fourth and final permitted Python file will orchestrate existing helpers;
it will not add another numerical algorithm. Its order is:

TIFF header/memory gate → JSON-initialized transform → area-uniform specimen-STL
surface samples → independent held-out CT rigid refinement → atomic registration
report. A `--registration-only` run stops there. Only a passing registration may
continue to corrected graph stations, streamed `0.stl`/`0.5.stl` identity
mapping, local measurements, binary/review decisions, augmented JSON, and
orthogonal evidence panels. `--limit-struts 10` selects ten evenly spaced
CAD-expected members rather than a spatially biased prefix for the mandatory
real visual audit. A later unlimited run is not allowed until those panels are
manually inspected and logged.

The CLI now compiles, `--help` exits cleanly, `git diff --check` passes, and the
file is 572 lines. No real TIFF has yet been decoded. Lightweight orchestration
tests will be added to the existing single test file before the registration-
only gate.

The complete compact suite now passes **35/35 tests in 10.28 s**, including a
real PNG render from synthetic CT evidence. All four permitted Python files
compile and the focused diff check is clean. The next action is the first real-
asset operation: `--registration-only` with 30,000 area-uniform surface samples.
It may write only `registration_report.json`; a failure must leave zero strut
labels and zero real evidence panels.

### Real registration gate R1 — rejected before strut analysis

The first real registration-only run completed in 10.20 s at approximately
0.87 GiB RSS and wrote report SHA-256
`6076e418a5a257e02c590e58a4fb15e0aa5915cb27689bb7e829a3d00a031b53`.
It is **rejected**, and no strut was mapped or labeled.

Evidence:

- held-out valid local crossings increased from 76.58% to 82.35%;
- held-out P90 absolute offset improved slightly from 1.7873 to 1.7692 voxels;
- but the primary held-out median absolute offset worsened from 1.0162 to
  1.0309 voxels;
- the signed median moved farther from zero (`-0.5741` to `-0.6315`);
- iteration 6 still proposed a 0.196-voxel translation step, so the optimizer
  had not converged;
- the code nevertheless set `converged=true` merely because an iteration
  history existed. That flag is wrong.

The candidate correction (0.1344 degrees, 1.7098 voxels) therefore cannot be
used. The fix will split samples into train/validation/final-held-out groups,
select an iteration only on validation common-valid crossings, and preserve the
identity correction when no candidate improves typical absolute offset without
worsening its tail. The final held-out group will be consulted once after
selection. `converged` will mean the update actually reached the small-step
criterion; separate `correction_accepted` and `selection_reason` fields will
state whether any refinement beat the JSON-initialized frame. Keeping identity
is an acceptable outcome if independent TIFF surface evidence shows that the
initial frame is already as good as the optimizer can justify.

After implementing the three-way split, the first synthetic rerun stopped at
test 13 because contrast-free data now fails earlier at selection-set surface
coverage rather than inside the training update. Both are the required
fail-closed outcome; the assertion is generalized to the scientifically stable
"surface crossing coverage" condition instead of an internal stage message.

### Real registration gate R2 — accepted for ten-strut diagnostic only

After the correction, all **35/35** tests pass again. The identical real command
produced report SHA-256
`d70e9918636b57be4b0c76dc5ccaa054898f8d45ae7d7971144e4910d8ab4f93`.
Validation selected iteration 3; the final held-out set was never used to pick
that iteration.

- validation common-valid median absolute offset: 0.9978 → 0.9706 voxels;
- validation common-valid P90: 1.7695 → 1.6906 voxels;
- final held-out common-valid median: 1.0001 → 0.9683 voxels;
- final held-out common-valid P90: 1.7585 → 1.6977 voxels;
- final held-out overall valid fraction: 76.58% → 80.47%;
- accepted correction: 0.07846 degrees and 1.01137 voxels;
- conservative decision uncertainty: 1.18643 voxels.

`converged=false` remains explicit because the training optimizer did not reach
the tiny-step condition; the accepted object is the earlier validation-selected
iteration, not the final drifting iterate. This evidence permits only the next
gate: ten evenly spaced expected members plus ten panels. It does not yet
authorize the full 18,468-record analysis.

### Ten-strut visual gate V1 — rejected; full run remains blocked

The mandatory diagnostic processed ten evenly spaced CAD-expected members and
wrote ten orthogonal evidence panels. Its aggregate decisions were six errors,
two review cases, and two healthy cases. Manual inspection rejects that result:
the apparent 60% error rate is dominated by a systematic measurement failure,
not credible evidence of damaged struts.

Panel-by-panel findings:

- strut 4 is visibly continuous; its error is only a 2.71-voxel measured
  centerline displacement, with the cyan CAD axis riding near the bright member;
- struts 2300 and 4278 are visibly continuous and were conservatively sent to
  review because of similar, smaller center offsets;
- struts 6266 and 8251 show continuous bright diagonal members in the
  orthogonal projections, but the axial profiles report 33.35- and 13.14-voxel
  unsupported gaps;
- struts 10235 and 12212 are visibly continuous, while centerline displacement
  alone produced error decisions;
- struts 14189 and 16173 are visually consistent with their healthy decisions;
- strut 18467 is visibly continuous but was assigned a 16.17-voxel unsupported
  gap.

The common failure is now localized to the station estimator. It compares a
small intensity core centered on the CAD axis with an annulus just outside the
expected radius. In this dense lattice, a roughly two-voxel residual center
offset can move the real member out of that small core, while adjacent or
crossing members make the annulus brighter. The resulting zero or negative
"local contrast" creates false unsupported stations and very long artificial
gaps. Its intensity-weighted centroid also uses all bright pixels in the disk,
so neighboring members can pull the measured center away from the target.

The full run is therefore **not authorized**. The corrective implementation
will first be challenged by a synthetic target that is shifted from its CAD
axis and surrounded by bright neighboring members. The measurement will then
replace core-versus-annulus contrast with a local two-dimensional material
threshold and connected-component isolation at each perpendicular station.
Only the material component intersecting a small CAD-axis seed region may
contribute to target presence, centroid, area, or radial measurements. This
preserves native TIFF resolution, keeps the measurement local, and prevents
unrelated neighboring material from being counted as the target. A centerline
deviation by itself will remain measurable but will be review-only until a
local-registration baseline can distinguish manufacturing displacement from
systematic alignment residual. Structural absence or a validated radial
failure may still produce `has_error=true`.

The exact same ten real members and panels must be regenerated and reinspected
after the synthetic suite passes. No full-dataset result will be produced if
even one of those panels still exhibits an unexplained false gap.

### Corrective implementation log C1 — adversarial reproduction

A new synthetic test places a continuous radius-four target 1.8 voxels to one
side and 0.8 voxels vertically from its CAD axis, then adds four bright nearby
parallel members whose cross-sections occupy the old background annulus. The
contract is intentionally narrow: the target must remain measurable, exceed
90% axial support, remain connected, and acquire no gap longer than the
existing 1.5-voxel connection tolerance. This test is run against the existing
estimator before its implementation changes; an expected failure confirms the
mechanism found in the real panels.

The first focused pytest invocation did not reach the test: napari's
auto-loaded pytest fixture attempted to create theme icons under the protected
macOS user cache and raised `PermissionError`. This is a test-harness path
failure, not an algorithm result. Subsequent invocations set `XDG_CACHE_HOME`
to a writable temporary directory; production inputs and calculations are
unchanged.

The initial four-neighbor fixture unexpectedly passed. That is useful: it
shows ordinary sparse neighbors do not automatically break the old estimator,
but it does not reproduce the dense annular contamination visible in the real
panels. Before changing production code, the fixture is strengthened to twelve
small, spatially separate neighboring cross-sections distributed around the
target. Their combined intensity occupies most of the background annulus while
leaving the target itself continuous and geometrically distinct. The test's
contract is unchanged.

With a dense separated bright shell occupying the legacy annulus and a
400-intensity contrast requirement, the old implementation fails the contract:
`measurement_valid=false` for a fully continuous target. This is the intended
red test and reproduces the real failure mechanism without using a real defect
label. Production code is now permitted to change.

### Corrective implementation log C2 — component-isolated stations

Each station now uses a robust 10th-to-90th-percentile contrast check and a
local Otsu threshold over its bounded measurement disk. Eight-connected 2D
components are labeled, and only a component intersecting the small CAD-axis
seed is eligible. Its pixels alone determine area and intensity-weighted
centroid. Radial rays start from that observed centroid and use the same local
surface level, taking the first outward material-to-air crossing; a brighter
unrelated component farther along the ray can no longer redefine "air" or erase
the target. If no component reaches the seed, the station remains unsupported
rather than borrowing a nearby member.

The classification rule is also narrowed: axial loss, excessive gap, failed
continuity, or radial deviation may confirm `has_error=true`; centerline offset
alone yields `has_error=null` and mandatory review. The numeric offset is still
preserved. This prevents the systematic two-voxel residual seen across the ten
panels from being mislabeled as six independent physical defects before local
alignment bias has been validated.

The focused adversarial test now passes. The complete compact suite then passes
**36/36 tests in 10.68 s** with no test failure. The remaining warnings are
third-party Pydantic deprecation notices emitted by napari's pytest plugin;
they do not alter measurements. This clears the synthetic gate only. The next
allowed action is to regenerate the same ten real members and panels using the
already accepted registration report and visually inspect them again.

### Ten-strut visual gate V2 — rejected; association seed too narrow

The corrected rerun completed in 34.64 s at 1.00 GiB RSS. Centerline-only
findings were correctly reduced to review, changing the aggregate result from
six errors/two review/two healthy to three errors/five review/two healthy.
However, the same struts 6266, 8251, and 18467 still showed artificial gaps.
Their regenerated projections again contain visually continuous bright members,
while the station reasons contain 104 instances of
`no_material_component_at_cad_axis` (35, 37, and 32 respectively).

The component association seed was only 45% of expected radius, approximately
1.6 voxels, but the supported end stations measure local centers 3–4 voxels
from the corrected CAD axis. The seed is widened to exactly one expected
radius—not to the full crop. A paired negative control is added before another
real rerun: when the target is entirely absent and only a parallel member 7.5
voxels away exists, the estimator must return zero axial support and must not
borrow that neighbor. This explicitly brackets the association behavior from
both sides.

Both association controls pass: the offset target remains continuous in dense
nearby material, and the absent target receives exactly zero support when only
the 7.5-voxel-offset neighbor is present. The complete suite passes **37/37
tests in 3.01 s**. The same ten real members are now rerun for a third visual
gate; the full dataset remains blocked.

### Ten-strut visual gate V3 — rejected; presence and radius quality conflated

The third rerun completed in 44.39 s at 0.71 GiB RSS. Nine members became
continuous; only strut 18467 remained an error candidate, with 93.0% axial
support and a 3.0316-voxel boundary gap. Its first two target components have
strong local contrast but area fractions 0.312 and 0.299, just below the 0.35
threshold used for reliable radial measurement. The third component has ample
area but only 25% usable radial crossings. The panel still shows a continuous
member, and all subsequent 40 stations are supported.

This reveals a semantic bug: the same Boolean represented both material
presence and successful radius metrology. Those are not equivalent. The code
now records axial presence once the correct high-contrast component exceeds a
separate conservative 0.15 expected-area floor. The stricter 0.35 area and 50%
ray requirements remain unchanged for a valid radius estimate. A station may
therefore be `present_radial_area_uncertain` or
`present_radial_crossings_uncertain` without becoming an artificial physical
gap. A new synthetic thin-member test requires full axial continuity while
explicitly exercising unavailable radial quality.

The first full test run stopped at that new fixture: its continuity assertions
passed, but the soft radius-two component still exceeded the default 0.35
radial-quality area, so the expected uncertainty reason was absent. Production
logic is unchanged. The fixture now explicitly requests an 0.80 radial-quality
area while retaining the 0.15 presence floor, which cleanly exercises the
separation it is designed to verify.

After that fixture correction, the complete compact suite passes **38/38 tests
in 5.70 s**. The fourth ten-member rerun is allowed; the full dataset is still
blocked until its regenerated panels are checked.

### Ten-strut visual gate V4 — passed for full-run authorization

The fourth rerun completed in 36.87 s at 0.89 GiB RSS. Counts are zero error
candidates, eight review cases, and two clearly inside tolerance. All ten
members have connected axial support; strut 6266 has one isolated unavailable
station producing only a 1.01-voxel gap within tolerance, and strut 18467 now
correctly records two present-but-area-uncertain stations and one
present-but-ray-uncertain station without fabricating a gap.

Every regenerated panel was inspected at original resolution. All ten bright
members are visibly continuous in their informative projection(s), matching
the axial decision evidence. The healthy decisions for 14189 and 16173 are
visually consistent. The large local center offsets for 4, 6266, 8251, 10235,
12212, and 18467 remain review-only, as intended. This gate establishes
agreement on ten visible continuous members, not real-defect sensitivity; that
remains supported only by planted synthetic omissions until expert labels are
available.

The full 18,468-record execution is now authorized under the 2.5 GiB RSS guard.
Specimen-CAD omissions remain non-applicable, and the output will not assign a
missing-versus-broken subtype.

### Full execution F1 — completed, then decision audit rejected one overclaim

The first full execution measured all 17,729 applicable CAD-expected members
and wrote the complete 18,468-record artifact in 328.02 s. Peak observed RSS
was 1.10 GiB. JSON parsing, record counts, and summary arithmetic pass. The
artifact SHA-256 was
`4acbc2e20dcea8a6e4ed6d2579ed767df806c6418826ed8e2b8c83b681b9ea4f`.
Its initial counts were 375 error candidates, 3,157 healthy, 14,197 review, and
739 non-applicable.

The ranked ten panels and a failure-mode count exposed a remaining decision
problem. Of the 375 candidates, 128 have acceptable axial fraction, no gap over
3 voxels, and acceptable radial evidence; their sole structural failure is
that the first or last sampled body station is unavailable. Since the
measurement deliberately excludes 12% at each junction, one exact boundary
station cannot independently prove a physical disconnection. Several ranked
panels are also saturated or geometrically ambiguous near lattice/build
boundaries, although others (notably 10 and 214) show plausible real absence.

The measurement is retained, but endpoint-connectivity failure alone is now
review-only. Confirmed candidates still require low axial coverage, a gap over
3 voxels, or radial deviation beyond the uncertainty-expanded tolerance. A new
unit test fixes this policy. F1 remains on disk for audit history but will be
superseded by a rerun after the complete suite passes.

The endpoint-only review policy passes its focused test, and the complete suite
passes **39/39 tests in 1.77 s**. A deterministic F2 rerun is now authorized to
replace the full JSON and ranked panels; no measurement parameter has changed.

### Full execution F2 — final candidate artifact

F2 completed in 324.84 s with peak observed RSS 1.20 GiB. The final augmented
JSON parses, contains exactly 18,468 struts, has zero unprocessed records, and
its mutually exclusive summary counts sum to 18,468:

- 247 `has_error=true` candidates;
- 3,157 `has_error=false` members clearly inside tolerance;
- 14,325 `has_error=null` review-required members;
- 739 non-applicable design/skin members, including 94 deliberate omissions
  encoded by the specimen CAD.

The final artifact SHA-256 is
`c9950ea10d876a07706b5b3a3395e2aa0bf3a740934ba295415e7cfecbebdeab`.
Of the 247 candidates, 246 exceed the 3-voxel unsupported-gap threshold, 190
also fall below 80% axial support, and two exceed radial tolerance. Centerline
offset is never sufficient by itself to confirm an error.

All ten ranked F2 panels were inspected. Some, especially struts 10 and 214,
show a visually plausible absent target corridor between bright junctions.
Others lie in saturated/overlapping boundary geometry and cannot be confirmed
from maximum projections. Therefore **247 is a candidate count, not a validated
physical defect count**. Expert review or independently labeled CT evidence is
still required to measure sensitivity, precision, and false-positive rate. The
pipeline fulfills the requested first-stage contract—identify exact strut IDs
that may have an STL-to-TIFF error—without assigning missing versus broken.

Final verification passes: **39/39 tests in 1.69 s**, all four Python files
compile, and `git diff --check` reports no whitespace error. The only warnings
are third-party napari/Pydantic deprecations from pytest plugin discovery. No
full-run threshold was tuned against the final candidate count.

## 2026-07-28 visualization continuation — direct MeshLab defect output

The numerical JSON is useful to software but does not yet satisfy the practical
need to *see* where the candidate struts are. A small standalone exporter will
convert the final comparison into two binary MeshLab-compatible PLY files:

- a full-context lattice with thin blue STL-expected centerline tubes and
  thicker red candidate tubes;
- a candidate-only model containing the same red expected corridors without
  the surrounding lattice.

Red means "the TIFF evidence failed the conservative strut test at this STL
location." It does not mean the red tube was reconstructed from CT, and it is
not a missing-versus-broken subtype. A compact JSON manifest will retain exact
strut IDs, endpoints, axial coverage, gap, and failed checks. This deliberately
prioritizes an immediately inspectable artifact over another detector rewrite.
