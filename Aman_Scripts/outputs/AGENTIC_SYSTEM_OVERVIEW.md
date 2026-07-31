# How the Agentic Lattice-CT Defect System Works
### End-to-end walkthrough: CT scan → 336 confirmed missing/broken struts

This document explains, in full technical detail, how the `-agentic` unified
system takes a raw industrial CT scan of a 3D-printed octet-truss lattice and
arrives at a final, reproducible count of **246 missing struts + 90 broken
struts = 336 confirmed defects** out of **18,468 total expected struts**
(1.82%), plus 3,816 struts flagged `bent_or_misaligned` and 6,973 flagged
`uncertain` for human review. It covers the math, the code, the MCP tool
surface, and the agent/dashboard architecture — everything needed to explain
the system on a poster.

---

## 1. The physical problem

The specimen is a **9×9×9 octet-truss lattice** (a repeating unit cell of
diagonal struts) that was **3D-printed** and then **CT-scanned**. The as-designed
CAD model says there should be a specific strut connecting every pair of
lattice junctions. Manufacturing defects — powder that never fused, print
failures, broken/thin struts — mean some of those CAD-expected struts are not
actually present, or are present but malformed, in the physical part.

The question the pipeline answers, per strut, is:

> "Does the observed CT material at this CAD-expected strut location match
> what the design says should be there?"

There are **18,468 CAD-expected struts** total. Of those, some are
*intentionally* absent from the physical specimen (the specimen STL,
`0.5.stl`, is a partial/damaged reference model — not every strut in the full
design, `0.stl`, was meant to be printed) or are embedded in a solid skin
layer where CT can't independently resolve them. Those are marked
`not_applicable` (739 struts) and are excluded from defect scoring entirely.
That leaves **17,729 struts that are actually compared against the CT
volume.**

---

## 2. High-level pipeline (5 stages)

```
┌──────────────────┐   ┌───────────────────┐   ┌────────────────────┐   ┌──────────────────────┐   ┌───────────────────────┐
│ 1. Registration   │──▶│ 2. Per-strut       │──▶│ 3. Tolerance-based  │──▶│ 4. Defect subtype     │──▶│ 5. Dashboard / MCP /   │
│    (STL → CT)     │   │    metrology       │   │    classification   │   │    labeling            │   │    Agent surface        │
│ ct_surface_       │   │    strut_metrology │   │    strut_metrology  │   │    defect_classifi-    │   │    ArtifactService,    │
│ metrology.py      │   │    .py             │   │    .py              │   │    cation.py           │   │    mcp_server.py,      │
│                   │   │                    │   │                     │   │                        │   │    Streamlit app.py    │
└──────────────────┘   └───────────────────┘   └────────────────────┘   └──────────────────────────┘   └───────────────────────┘
```

Each stage is a **deterministic, from-scratch numerical/geometric algorithm**
run against the native-resolution CT TIFF and the STL/JSON CAD geometry.
Nothing in this pipeline is a trained ML model — it's classical registration,
signal processing (ISO-50 edge crossing detection), and rule-based
tolerance classification. Confidence values are **uncalibrated rule-strength
scores**, not probabilities, and this is stated explicitly everywhere the
pipeline surfaces results (dashboard, MCP tool docstrings, CSV headers).

---

## 3. Stage 1 — Registration: aligning CAD to the CT volume

This is the most mathematically involved stage, and the one that was just
reworked (Phase 1 of the "registration-similarity-fit" change, explained in
§7) to fix a systematic bias that was previously causing massive
over-flagging.

### 3.1 Initial registration (closed-form, Umeyama similarity fit)

File: `Aman_Scripts/tif2stl/registration.py::similarity_transform`

The pipeline has two independent CAD representations of the same lattice
junctions:
- The **design JSON** (`octet_truss_9x9x9.json`) — junction positions in
  dimensionless design/lattice units.
- The **registered JSON** — the same junction IDs, already roughly aligned
  into native CT voxel coordinates (an existing partner-provided
  registration).

Because both files carry **identical junction IDs** (10,206 of them), the
pipeline can fit a closed-form similarity transform (rotation + isotropic
scale + translation) mapping design-space points onto CT-space points,
using the classic **Umeyama closed-form least-squares similarity fit**:

Given paired point sets `{sᵢ}` (source/design) and `{tᵢ}` (target/CT), `i = 1..N`:

```
s̄ = mean(sᵢ)                          t̄ = mean(tᵢ)
S  = Σᵢ (sᵢ - s̄)(sᵢ - s̄)ᵀ / N          (source variance, scalar trace)
Σ  = Σᵢ (tᵢ - t̄)(sᵢ - s̄)ᵀ / N          (cross-covariance matrix)

Σ = U Σ_diag Vᵀ                        (SVD)
C = diag(1, 1, det(U Vᵀ) < 0 ? -1 : 1)  (reflection correction)
R = U C Vᵀ                             (rotation)
c = trace(Σ_diag · C) / trace(S)       (isotropic scale)
d = t̄ - c·R·s̄                          (translation)

target ≈ c·R·source + d
```

This is implemented exactly as written in `similarity_transform()`
(`Aman_Scripts/tif2stl/registration.py:46-103`) — SVD of the cross-covariance,
reflection-corrected rotation, scale as the ratio of singular-value trace to
source variance, translation from the centroids.

Live measured result for this dataset: **10,206 paired junctions**, fit
RMS = **3.3×10⁻¹² voxels** (essentially exact — this fit is between two CAD
files, not an independent image-registration measurement), scale =
**39.4888 voxels per design unit**, rotation = **0.335°**.

An STL→design-unit matrix is composed on top of this (`stl_to_design_matrix`),
using the paper's specified **4.56 mm unit-cell edge** (2.28 mm per design
unit, since the graph advances 2 coordinate units per cell) and a
**0.424 mm nominal strut diameter**. The two matrices are chained
(`compose_transforms`) to get one STL-millimeters → native-CT-voxel matrix.

A **physical sanity gate** cross-checks the STL's own bounding-box extent
against `design_span (18 units) × 2.28 mm/unit + 0.424 mm strut diameter`,
rejecting the whole run if the physical STL doesn't match the claimed design
scale to within 0.10 mm.

### 3.2 Independent refinement: 7-DOF similarity ICP against real CT intensities

**This initial fit is not evidence that the CAD surface coincides with real
CT material** — it's just JSON-to-JSON. Stage 1's second half
(`refine_rigid_registration`, `Aman_Scripts/Components/ct_surface_metrology.py:356-627`)
independently verifies and corrects that alignment directly against the raw
CT voxel intensities, with **no dependency on the JSON-to-JSON fit's own
error metric**.

**Surface sampling.** 30,000 points are sampled from the STL surface,
area-uniformly (via cumulative-triangle-area binning + a low-discrepancy
golden-ratio/silver-ratio jitter inside each triangle — `sample_stl_surface_by_area`),
each carrying an outward surface normal.

**Local ISO-50 edge detection.** For every sample point, the pipeline walks a
short 1-D intensity profile along the surface normal (±3 voxels, 0.5-voxel
steps, trilinear-interpolated from the raw TIFF) and finds the sub-voxel
offset where intensity crosses the **local air/material midpoint**:

```
level = 0.5 × (median(profile_near_end) + median(profile_far_end))
```

This "local ISO-50" (as opposed to one global threshold) makes the crossing
robust to CT beam-hardening, which shifts absolute intensity across the
volume. The crossing offset is found by linear interpolation between the two
profile samples that bracket the sign change of `profile - level`
(`local_iso50_crossings`, lines 84-168).

**Point-to-plane weighted least squares, 7 degrees of freedom.** Each
iteration solves for a small rotation, translation, and (as of the Phase 1
fix) **isotropic scale** correction that minimizes the surface-normal
component of the residual, i.e. classic point-to-plane ICP extended with a
scale term:

```
relative = point - pivot
system_row = [ relative × normal  |  normal  |  (relative · normal) ]     (1×7)
target_row = local_iso50_crossing_offset                                    (scalar)
```

The 7th column, `relative · normal`, is the **scale-sensitivity term**: it's
the projection of a point's offset from the pivot onto its own surface
normal, which is exactly how a uniform scale change (points moving radially
away from/toward the pivot) shows up in a point-to-plane linear system. This
column was **added in the Phase 1 fix** — previously the system only had 6
columns (rotation + translation), so it was structurally incapable of
representing a scale error.

Solved with `numpy.linalg.lstsq` after **robust re-weighting**
(`weights = 1 / max(1, |offset| / (1.5σ))`, with σ the robust MAD-based scale
of the offsets) to down-weight outlier crossings. Each iteration's step is
capped (rotation ≤ 0.10°, translation ≤ 0.35 voxel, scale ≤ 0.5%) so the
optimizer can't take one big unstable jump — it converges gradually over up
to 12 iterations.

**Validation-gated selection — not "run N iterations and stop."** Every
iteration's candidate correction is scored against a held-out **selection
set** (a fixed 20% slice of surface points, `index % 5 == 1`, never used to
fit the correction) — a candidate is only "eligible" if it doesn't lose
coverage and both its median and P90 absolute crossing offset are no worse
than the pre-correction baseline on that selection set. The **iteration with
the best score across all 12 is kept**, not necessarily the last one. On
this run, **iteration 7 of 12** was selected.

**Independent held-out audit — the final gate.** A *third*, completely
separate 20% of points (`index % 5 == 0`, never touched by fitting or
selection) is used for one last audit: if the accepted correction doesn't
actually improve the held-out median/P90 offset, or the accepted rotation/
translation/scale magnitude exceeds hard caps (0.5°, 2.0 voxels, 2% scale),
**the whole correction is rejected and identity is used instead.** This is a
genuine train/validate/test split over surface points, not just internal
iteration bookkeeping.

**Result on the live dataset** (`Aman_Scripts/outputs/simple_strut_metrology/registration_report.json`):

| Quantity | Value |
|---|---|
| Correction accepted | `True` (iteration 7 of 12) |
| Rotation | 0.1695° |
| Translation | 2.374 voxels |
| **Scale factor** (new in Phase 1) | **0.992487** (≈ 0.75% shrink) |
| Registration uncertainty (`robust_sigma_voxels` on held-out) | **0.6296 voxels** |
| Held-out median absolute offset, before → after | 1.016 → 0.840 voxels |
| Held-out valid crossing fraction, before → after | 76.6% → 91.0% |
| Method string | `"local-ISO50 robust point-to-plane rigid refinement + isotropic scale"` |

The `registration_uncertainty_voxels` value (0.6296) is the single most
important number this stage produces — it flows directly into Stage 3's
per-strut tolerance and Stage 4's stability gate.

---

## 4. Stage 2 — Per-strut metrology (native-resolution cross-section measurement)

File: `Aman_Scripts/Components/strut_metrology.py::measure_strut_cross_sections`

For every one of the 17,729 CT-comparable struts, using the corrected
transform from Stage 1:

1. Build a local 2-D coordinate frame (`u, v`) perpendicular to the strut's
   nominal axis at each of several axial "stations" along its length
   (10% trimmed off each end to avoid junction-blob artifacts —
   `endpoint_exclusion_fraction=0.12`).
2. At each station, trilinearly sample a small square grid of intensities
   in that cross-sectional plane.
3. **Segment the local material component** with a per-station **Otsu
   threshold** computed only from the small local crop (not a global
   threshold — beam-hardening varies spatially):

   ```
   Otsu score(t) = [ (Σμ·Nₜ) − (Σᵢ≤ₜ Nᵢμᵢ)·N ]² / [ Nₜ·(N − Nₜ) ]
   ```
   (implemented in `_otsu_level`, maximizing between-class variance over
   128 histogram bins clipped to the 1st–99th percentile of local intensities.)

4. Connected-component label the thresholded material (`scipy.ndimage.label`)
   and select the component actually touching the CAD centerline (a seed
   disk), rejecting unrelated nearby material.
5. From the selected component: compute its **centroid displacement** from
   the CAD-nominal centerline, its **area fraction** relative to the
   CAD-expected cross-sectional area, and cast **16 rays** radially outward
   to find sub-voxel **ISO-50 radius crossings** (same local-midpoint edge
   detection as Stage 1, now used radially instead of along a surface
   normal) to get an **observed radius** at that station.

Per-strut, these per-station numbers are aggregated into the headline
measurement fields used downstream:

- `observed_axial_fraction` — fraction of stations with *any* supported
  material.
- `longest_unsupported_gap_voxels` — longest contiguous run of unsupported
  stations, in voxels.
- `connected_support` — `True` only if the first and last stations are both
  supported *and* the longest gap ≤ 3.0 voxels.
- `median_signed_radial_deviation_voxels`, `p90_absolute_radial_deviation_voxels`
  — observed radius minus expected (CAD) radius, at valid stations.
- `p90_centerline_displacement_voxels` — 90th percentile of the per-station
  centroid displacement from the nominal centerline.

This stage produces **raw geometric evidence only** — no pass/fail decision
yet.

---

## 5. Stage 3 — Tolerance-based classification

File: `Aman_Scripts/Components/strut_metrology.py::classify_strut_measurement`

Explicit, fixed tolerances are applied to Stage 2's measurements:

```
manufacturing_radial_tolerance_voxels      = 0.75   (fixed manufacturing spec)
manufacturing_centerline_tolerance_voxels  = 0.75   (fixed manufacturing spec)
registration_uncertainty_voxels            = 0.6296 (from Stage 1, per-run global constant)

radial_limit  = manufacturing_radial_tolerance_voxels     + registration_uncertainty_voxels  = 1.3796
center_limit  = manufacturing_centerline_tolerance_voxels + registration_uncertainty_voxels  = 1.3796
```

The registration uncertainty is **added to the fixed manufacturing tolerance
before comparison** — the logic being that any given strut's apparent
deviation is a mixture of *real* manufacturing deviation and *unavoidable*
residual registration error, and the pipeline can't tell them apart per-strut,
so it charitably assumes the whole registration uncertainty budget could be
consumed before calling something a real deviation.

A strut fails one or more named checks:

| Check | Condition |
|---|---|
| `axial_coverage` | `observed_axial_fraction < 0.80` |
| `unsupported_gap` | `longest_unsupported_gap_voxels > 3.0` |
| `continuous_support` | `connected_support is not True` |
| `radial_deviation` | `\|median_signed_radial_dev\| > radial_limit` **or** `p90_radial_dev > radial_limit` |
| `centerline_displacement` | `p90_centerline_displacement > center_limit` |

`axial_coverage`, `unsupported_gap`, and `radial_deviation` failures are
**"confirmed"** (`has_error: True`) — direct, unambiguous tolerance breaches.
A **centerline_displacement-only** failure is treated more cautiously
(`has_error: None`, `decision_reason:
"centerline_offset_requires_local_alignment_review"`) — precisely *because*
a centerline offset is the signal most easily confused with residual
registration error, not a real bend. This ambiguity is exactly what Stage 4's
new stability gate (§7.2) is designed to resolve.

A strut is `clearly_healthy` (and gets `has_error: False`) only if it clears
*every* check with margin to spare (`review_margin_voxels = 0.25` below the
limit) — this asymmetric "must clear with margin to count as healthy, but
any excess at all fails a check" design deliberately biases toward flagging
for review rather than silently passing borderline cases.

---

## 6. Stage 4 — Defect subtype labeling

File: `Aman_Scripts/Components/defect_classification.py::classify_defect_subtype`

Stage 3 only says *pass/fail per check*. Stage 4 turns that into one of eight
final labels, in this priority order:

```
1. not_applicable         if comparison_applicable is False (CAD-absent or skin-embedded)
2. uncertain               if measurement_valid is not True (couldn't measure at all)
3. missing / broken        if {axial_coverage, unsupported_gap} both failed:
                              missing  if observed_axial_fraction < 0.35
                              broken   otherwise
4. broken                  if continuous_support failed, or gap > 3.0 (any other path to disconnection)
5. thin / thick             if radial_p90 > radial_limit:
                              thin   if signed deviation < 0  (narrower than CAD)
                              thick  if signed deviation > 0  (wider than CAD)
6. uncertain / bent_or_misaligned   if only centerline_displacement failed — see §7.2 stability gate
7. healthy                  if has_error is False (cleared every check with margin)
8. uncertain                 otherwise (near-threshold / conflicting evidence, review required)
```

The **missing vs. broken boundary at 35% axial coverage** (step 3) is called
out explicitly in the code and docs as **"a deliberately reviewable policy
threshold, not a claim of physical ground truth"** — a strut with almost no
supported material along its length is called `missing`; one with some
supported material remaining, but still disconnected, is called `broken`.

---

## 7. Why the numbers changed: the registration-similarity-fit

### 7.1 The problem this session found and fixed

Before this fix, **`bent_or_misaligned` accounted for 12,723 of 18,468
struts (69%)** — an implausibly large fraction for a real print. Diagnosis
(carried out this session by analyzing the live classification CSV against
`registration_report.json`) found the excess was **not random noise**: the
median strut already exceeded the centerline tolerance, 72–80% of struts
exceeded it in *every* orientation group, and there was a clear gradient by
distance from the registration pivot (exterior struts worse than interior)
and by height band. That specific signature — a bias proportional to
distance from a pivot that *survives* a rigid correction — is the textbook
fingerprint of an **uncorrected isotropic scale error**, which the old
**6-DOF rigid-only** fit (rotation + translation, no scale) was structurally
incapable of representing or removing.

### 7.2 Phase 1 (registration) + Phase 2 (classification stability gate)

**Phase 1** (§3.2 above) extended the 6-DOF rigid ICP to the current 7-DOF
similarity ICP, adding the scale column to the point-to-plane linear system,
scale extraction (`det(correction[:3,:3])^(1/3)`), and a `maximum_scale_fraction`
safety gate. This alone reduces the *systematic* component of centerline
error across the whole lattice (the fitted scale factor, 0.992487, i.e. a
0.75% shrink, was previously baked into every strut's apparent centerline
displacement as spurious signal).

**Phase 2**, in `classify_defect_subtype` (`Aman_Scripts/Components/defect_classification.py:97-115`),
adds a symmetric **registration-stability gate** for the one check that's
structurally ambiguous between "real bend" and "residual registration
noise":

```python
if "centerline_displacement" in failed:
    excess = center_p90 - center_limit
    if excess <= registration_uncertainty_voxels:
        → "uncertain"  (reason: centerline_offset_within_registration_stability_band)
    else:
        → "bent_or_misaligned"  (reason: centerline_offset_cannot_separate_bend_from_registration)
```

In words: a strut only keeps the `bent_or_misaligned` label if its centerline
offset exceeds the declared tolerance by **more than a full extra
registration-uncertainty unit** — i.e., the failure is stable even under a
plausible doubling of the registration's own residual scatter. Struts that
clear the base tolerance only marginally fall back to `uncertain` for human
review instead of a confirmed-sounding label. This idea (gate a borderline
label behind the estimator's own uncertainty) was independently converged on
by a concurrent comparison against a collaborator's separate pipeline (see
§10) and was implemented here from scratch, natively, against this repo's
own `registration_uncertainty_voxels` field — no code was copied.

### 7.3 Measured effect (before → after, full 18,468-strut regeneration)

| Label | Before fix | After fix |
|---|---|---|
| `bent_or_misaligned` | 12,723 (68.9%) | **3,816 (20.7%)** |
| `healthy` | 3,162 | **6,598** |
| `uncertain` | 1,467 | **6,973** |
| `missing` | 120 | **246** |
| `broken` | 256 | **90** |
| `thin` | 1 | 6 |
| `thick` | 0 | 0 |
| `not_applicable` | 739 | 739 (unchanged — excluded from CT comparison entirely) |
| **missing + broken (headline)** | **376** | **336** |

Interpretation of each shift:

- **`bent_or_misaligned` 12,723 → 3,816**: the combined effect of (a) Stage 1
  actually being more accurate now (fewer struts exceed `center_limit` at
  all), and (b) Stage 4's stability gate routing marginal remaining failures
  to `uncertain` for review instead of confirming a bend.
- **`healthy` 3,162 → 6,598** and **`uncertain` 1,467 → 6,973**: mass freed
  from the shrunken `bent_or_misaligned` bucket redistributes into both —
  struts that are now genuinely inside tolerance become `healthy`; struts
  whose centerline failure is now ambiguous-by-design become `uncertain`.
- **`missing` 120 → 246, `broken` 256 → 90**: this is a **real, data-driven
  side effect**, not something second-guessed or overridden. The corrected
  (now properly scaled) registration shifts *measured axial-coverage values*
  for many struts — struts previously measured just above the missing/broken
  boundary (`observed_axial_fraction = 0.35`, see §6 step 3) can shift below
  it once the geometry is more accurately registered, and vice versa. Per
  [CLAUDE.md's standing rule](#), this was **not tuned to hit a target
  count** — the boundary constant (0.35) itself was never touched; only the
  upstream registration accuracy changed, and the boundary crossing is a
  consequence of that, reported as-is.

All of this was validated by re-running:
1. `Aman_Scripts/run_simple_strut_metrology.py` — Stage 1 + 2 (607.4 s for
   all 17,729 comparable struts).
2. `Aman_Scripts/classify_strut_defects.py` — Stage 3 + 4 (rule-based, fast).
3. `python -m defect_cartographer.core.full_results` — merges the
   classification onto the registered lattice geometry and rebuilds every
   dashboard/MCP artifact (§9).
4. Full test suite: **46/46** `Aman_Scripts` unit tests (unchanged, confirm
   the algorithm code itself is still correct) + **45/45** `part2` tests
   (5 files' hardcoded expected counts updated to match the new,
   scientifically-justified numbers — nothing in the *logic* changed to
   make tests pass, only the literal expected-count assertions).

---

## 8. Where "human review" fits: `human_review_labels.csv`

`part2/defect_cartographer/core/full_results.py::_apply_human_review_overrides`
is the one place a human can override an automated label. It reads
`human_review_labels.csv` (columns: `strut_id`, `human_label`, `review_note`),
left-joins it onto the automated table, and for any reviewed strut:
overwrites `defect_type`/`prediction` with the human label, sets
`classification_confidence = "human_reviewed"`, and records the reviewer's
note as the new `prediction_reason`. This runs **after** every automated
regeneration, so re-running Stages 1–4 never silently discards a human
correction — it's always re-applied on top. (Confirmed live: raw Stage 3/4
output was `healthy: 6,595 / broken: 90 / missing: 246`; final output after
overrides was `healthy: 6,598 / broken: 90 / missing: 246` — a few
healthy-direction corrections from human review, broken/missing untouched.)

---

## 9. Stage 5 — Artifact assembly, the read-only service boundary, and MCP

### 9.1 `full_results.py` — building the final artifacts

`build_full_dashboard_artifacts()` (`part2/defect_cartographer/core/full_results.py:179-246`)
is the single function that turns the raw classification CSV into everything
the dashboard/agents/MCP actually read:

- **`full_strut_classification.csv`** — one row per strut (18,468 rows,
  strictly enforced — `EXPECTED_STRUTS = 18_468`), joining: the classification
  label, registered 3-D geometry (start/end/mid XYZ, region, height band,
  orientation), measurement evidence (occupancy, gap fraction, alignment
  error, diameter), and confidence.
- **`full_pipeline_metrics.json`** — aggregate counts (`prediction_counts`
  keyed by all 8 labels), `classification_coverage`, `uncertain_fraction`,
  thickness statistics.
- **`full_lattice_scene.npz`** — a compact NumPy array bundle for the
  Three.js browser viewer (strut endpoint coordinates, IDs — **never raw CT
  voxels**).
- **`full_defect_report.md`** — the generated methodology document
  (`get_methodology` below serves bounded excerpts of exactly this file).

### 9.2 `ArtifactService` — the one read-only boundary

`part2/defect_cartographer/service.py::ArtifactService` is a **single
bounded, read-only** class that both the MCP server and the Streamlit
dashboard's data adapter go through — there is no second code path that
reads the classification CSV directly. It never reads raw CT voxels, never
changes labels, never writes files. Its six methods:

| Method | Purpose |
|---|---|
| `get_pipeline_summary()` | Aggregate candidate counts, alignment reliability, thickness stats, clustering status, standing warnings. |
| `get_strut_details(strut_id)` | Every saved field for exactly one strut. |
| `filter_defect_candidates(filters)` | Filter by label / region / height band / orientation / numeric ranges; capped at 200 records per call. |
| `compare_defect_groups(group_by, metric)` | Aggregate one allow-listed metric (`count`, `occupancy`, `gap_fraction`, `alignment_error_vox`, `diameter_median_um`, `confidence_percent_uncalibrated`, `threshold_stability`) across an allow-listed group axis (`prediction`, `region`, `height_band`, `orientation`). |
| `get_methodology(section)` | Bounded excerpt of the generated methodology report. |
| `prepare_threejs_scene(request)` | Bounded scene *spec* (strut IDs + flags) for the browser viewer — **never geometry arrays or raw CT**, by design (`geometry_included_in_response: False` is asserted in tests). |

Every query result carries an explicit machine-readable warning field
reiterating that labels are unvalidated automated evidence, not ground
truth, and that confidence is uncalibrated rule strength, not a probability
— this is enforced at the data layer, not left to prose.

**The exact query that produced this session's 336-record list**:
```python
service.filter_defect_candidates(
    ArtifactFilter(classes=["missing", "broken"], limit=500)
)
# → matching_count: 336, returned_count: 336
```

### 9.3 The unified MCP server

File: `part2/defect_cartographer/mcp_server.py` — built on **FastMCP**.

This server is the "merged agent" referenced earlier in this project: it
**mounts** the original raw-CT tool server (`Aman_src/mcp_server.py`,
pre-existing, independently built) under a `raw_ct` namespace
(`mcp.mount(module.mcp, namespace="raw_ct")`), so **one MCP server exposes
both toolsets** to any connected agent, side by side:

**Native dashboard-evidence tools** (read-only, deterministic saved
artifacts, defined directly in `mcp_server.py`):
- `get_pipeline_summary`
- `get_strut_details`
- `filter_defect_candidates`
- `compare_defect_groups`
- `get_methodology`
- `prepare_threejs_scene`
- `get_strut_ct_evidence` — renders a bounded orthogonal CT image crop
  around one strut (the one native tool that *does* touch raw CT, but only
  to render a fixed-size image, never to return raw voxel arrays).

**Mounted `raw_ct.*` tools** (the original raw-CT toolkit, prefixed under the
`raw_ct` namespace — 17 tools total):
`raw_ct_register_json_to_tiff`, `raw_ct_read_json`, `raw_ct_read_npy`,
`raw_ct_segment_tiff_otsu`, `raw_ct_skeleton_to_json`,
`raw_ct_compare_octet_json`, `raw_ct_read_tiff`, `raw_ct_segment_ct_dataset`,
`raw_ct_visualize_slice`, `raw_ct_skeletonize`, `raw_ct_measure_tiff_struts`,
`raw_ct_run_full_defect_workflow`, `raw_ct_get_full_defect_summary`,
`raw_ct_get_full_strut_details`, `raw_ct_filter_full_struts`,
`raw_ct_get_human_review_anchors`, `raw_ct_compare_human_anchors_to_full_lattice`.

This is *literally* "merging my own CT tools with the dashboard tools into
one server" — any agent connected to this single MCP endpoint can call
either toolset, and reverting to only the original raw-CT agent is as simple
as pointing a client at `Aman_src/mcp_server.py` directly instead of the
unified server, since the mount is additive and doesn't modify the original
module.

### 9.4 The Streamlit dashboard

`part2/app.py` + `part2/defect_cartographer/dashboard/*` — a **separate
presentation layer** on top of the same `ArtifactService`/artifact files.
`dashboard/data.py::load_dashboard_artifacts` reads the same
`full_strut_classification.csv`, then **collapses the 8 detailed labels down
to 4 canonical dashboard labels** for a simpler visual legend:

```python
CANONICAL_LABELS = ("intact", "missing", "broken", "uncertain")
LABEL_MAP = {
    "healthy": "intact", "intact": "intact",
    "missing": "missing",
    "broken":  "broken",
    # everything else (bent_or_misaligned, thin, thick, not_applicable, uncertain) → "uncertain"
}
```

The original detailed label is preserved alongside the collapsed one as
`raw_prediction`/`automated_prediction`, so no information is lost — the
dashboard just chooses a coarser legend for the "Strut Explorer" / "Visual
Analysis" views, while `raw_prediction` remains queryable. Live collapsed
counts: `intact: 6,598`, `missing: 246`, `broken: 90`,
`uncertain: 11,534` (= 3,816 bent_or_misaligned + 6,973 uncertain + 739
not_applicable + 6 thin).

The dashboard has four pages (`Strut Explorer`, `Visual Analysis`,
`System Design`, `Copilot`/Analysis Copilot) and renders the full lattice as
an interactive Three.js scene sourced from `full_lattice_scene.npz` via the
bounded scene-spec MCP tool.

---

## 10. How this relates to the collaborator's independent pipeline

A teammate built a **completely separate, independently engineered**
GPT-based multi-phase pipeline (in a different repo,
`llnl_data_science_challenge_2026_GPT_30july`) that reaches its own defect
counts (headline: 202 auto-supported missing + 12 disconnected = 214
combined, out of the same 18,468 struts). It has its own multi-stage
architecture (STL/design-intent ranking, VTK occupancy components, a
CT-only robust-template anomaly atlas, late-fusion transform ranking,
symmetry audits, bootstrap-separated transform verification, and a very
conservative auto-confirmation gate before anything counts as "supported").

Critically, an 81-check cross-validation
(`Aman_Scripts/outputs/collaboration/verify_handoff_report.md`, 78 pass / 3
cosmetic-only fail) confirmed both pipelines are scoring **the exact same
18,468-strut, 3,430-welded-node graph topology** — zero edge mismatches. So
the two pipelines' different final counts (336 here vs. 214 there) are a
difference in **methodology and confirmation strictness**, not a
disagreement about the underlying CT data or lattice structure. This
project's pipeline confirms more liberally at the raw-tolerance level (§5)
but adds an explicit `uncertain` review bucket for anything ambiguous (§7.2)
rather than silently either confirming or discarding it — the two systems
sit at different points on the same precision/recall trade-off, and both
report their uncertainty explicitly rather than hiding it in a single number.

---

## 11. Summary numbers for the poster

```
Total CAD-expected struts:                18,468
  ├─ Not comparable to CT (design-absent or skin-embedded):   739  (not_applicable)
  └─ Independently measured against native CT:              17,729

Of the 17,729 measured struts:
  ├─ healthy (all checks clear, with margin):                6,598
  ├─ uncertain (ambiguous / near-threshold, review-required): 6,973
  ├─ bent_or_misaligned (centerline offset, review-required): 3,816
  ├─ thin (radial deviation, narrower than CAD):                  6
  ├─ thick (radial deviation, wider than CAD):                    0
  ├─ MISSING (axial coverage < 35%, low support + large gap): 246
  └─ BROKEN  (disconnected but with more support remaining):   90
                                                              ─────
  Confirmed missing + broken defects:                         336  (1.82% of 18,468)
```

**Registration accuracy achieved** (the number that made this trustworthy):
held-out median absolute surface-crossing offset improved from **1.02
voxels to 0.84 voxels** after the 7-DOF similarity correction, with
registration uncertainty (used as every strut's tolerance safety margin) at
**0.6296 voxels**.
