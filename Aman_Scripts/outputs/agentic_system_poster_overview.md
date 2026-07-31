# Agentic CT-Lattice Defect System

## Technical poster overview

**Current checkout:** `/Users/amannindra/Projects/llnl_DSC/llnl_data_science_challenge_2026-agentic`  
**Current branch:** `agent/defect-agent-experiment`  
**Analysis scope:** 18,468 expected struts from the registered lattice graph  
**Current result:** 246 missing + 90 broken = **336 automated evidence classifications**

This document describes the implemented system, the evidence path from the raw CT TIFF to the dashboard, the formulas used by the measurement code, the MCP tools, the agentic orchestration layer, and the limitations that must appear on a scientific poster.

## 1. Main result

The current post-registration artifact contains one row for every one of the 18,468 expected lattice struts:

| Classification | Count | Fraction of 18,468 |
|---|---:|---:|
| Missing | 246 | 1.33% |
| Broken | 90 | 0.49% |
| Missing + broken | **336** | **1.82%** |
| Thin | 6 | 0.03% |
| Healthy | 6,598 | 35.73% |
| Bent or misaligned | 3,816 | 20.66% |
| Uncertain / review | 6,973 | 37.76% |
| Not applicable | 739 | 4.00% |
| **Total** | **18,468** | **100.00%** |

The 336 value is a screening result from automated TIFF/geometry evidence. It is not a validated ground-truth defect prevalence. The dashboard and report preserve `uncertain`, `review`, and `not_applicable` states instead of forcing every strut into healthy or defective.

The classification table reports 17,995 valid localized thickness measurements. The median measured diameter is approximately 356.8 micrometres. The voxel pitch used by the dashboard configuration is approximately 58.09 micrometres.

## 2. What “agentic” means in this implementation

The system has two different layers:

1. **Deterministic scientific workers.** Existing Python components perform TIFF reading, Otsu segmentation, skeletonization, registration, cross-section measurement, classification, artifact writing, and dashboard loading. These workers produce reproducible files and rows.
2. **Agentic control and tool layer.** MCP tools expose the workers and saved evidence. The persistent orchestration layer creates a run, records stage state in SQLite, resumes successful stages, records artifacts and hashes, handles cancellation, and can ask the copilot layer for a bounded explanation.

The model is therefore not silently inventing a defect label for each row. It invokes a controlled tool surface, while the numerical labels come from declared measurements and decision rules. The system is agentic because the run is inspectable, resumable, and tool-driven; it is not agentic because 18,468 independent language-model conversations are launched.

## 3. Repository and rollback boundary

All migration and experimental orchestration work is isolated in:

`/Users/amannindra/Projects/llnl_DSC/llnl_data_science_challenge_2026-agentic`

The original working checkout is not the landing target for this experiment. The isolated checkout is intentionally dirty and uncommitted, so rollback is available by preserving the worktree and comparing it with `HEAD` or creating a clean worktree from the pre-experiment commit. Do not use a destructive clean/reset operation without first archiving the current changes.

Important implementation files:

- `part2/defect_cartographer/mcp_server.py` — unified dashboard/evidence MCP server; mounts Aman’s raw CT MCP tools under the `raw_ct` namespace.
- `Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py` — experimental unified MCP entrypoint that adds lifecycle/orchestration tools to the native dashboard and raw-CT tools.
- `part2/defect_cartographer/agentic_orchestration/models.py` — run and stage data types.
- `part2/defect_cartographer/agentic_orchestration/persistence.py` — SQLite WAL run store, state transitions, events, artifact registration, and SHA-256 records.
- `part2/defect_cartographer/agentic_orchestration/runtime.py` — resume-aware Aman-only stage runner.
- `part2/defect_cartographer/agentic_orchestration/pipeline.py` — deterministic callbacks for validation, registration, segmentation, skeletonization, measurement, reconciliation, QA, and reporting.
- `part2/app.py` — Streamlit dashboard entrypoint.
- `part2/defect_cartographer/dashboard/` — artifact adapter, pages, figures, CT evidence panels, and Three.js scene integration.

## 4. Input data and coordinate conventions

The workflow uses two complementary sources:

- **Raw TIFF:** supplies measured CT intensity, segmentation evidence, skeleton evidence, local axial support, gaps, radius/diameter, and centerline displacement.
- **Registered lattice identity:** supplies expected junctions, strut IDs, endpoint coordinates, and topology. This is necessary to say which expected member is missing; a TIFF alone cannot identify an absent expected strut.

Coordinate conventions are explicit:

- TIFF/NumPy volume indexing is `[z, y, x]` or ZYX.
- Lattice geometry and endpoint coordinates are `(x, y, z)` or XYZ.
- Conversion between the two orders is performed before array indexing.
- The voxel pitch is approximately 58.1 micrometres per voxel.

The registered graph contains 10,206 junction records, welded into 3,430 graph nodes and 18,468 expected strut edges. The reconciliation stage requires exactly 18,468 unique strut IDs.

## 5. End-to-end workflow

### Stage A — validate inputs

The run records the TIFF and registered-identity paths, their SHA-256 hashes, coordinate convention, voxel pitch, and expected radius. A configured executable run refuses missing paths rather than silently producing an empty result.

The validation artifact records:

- raw TIFF hash;
- registered identity hash;
- TIFF shape and ZYX convention;
- voxel pitch;
- expected radius;
- the fact that identity comes from the registered graph while measurement comes from the TIFF.

### Stage B — registration and audit

The registered JSON-to-TIFF transform is the geometric initialization. The post-fix metrology run then applies an independent small similarity refinement:

- local ISO-50 CT surface crossings;
- robust point-to-plane fit;
- rotation, translation, and isotropic scale parameters;
- separate training, selection, and held-out samples;
- robust outlier rejection;
- held-out acceptance gate.

The current saved registration report records approximately:

- scale factor: `0.99248695`;
- rotation magnitude: `0.16951042` degrees;
- translation magnitude: `2.37392650` voxels;
- uncertainty: `0.62961264` voxels;
- selected iteration: `7`;
- correction accepted: `true`.

These values are audit metadata, not defect labels. The held-out gate prevents an apparent training improvement from being accepted if it damages independent crossings.

### Stage C — Otsu segmentation

The raw 3D TIFF is processed as a streamed ZYX volume. A global Otsu threshold is estimated from finite voxel intensities. The foreground rule is:

```text
foreground voxel = 1 if intensity > Otsu threshold
foreground voxel = 0 otherwise
```

The saved TIFF mask uses `uint8` values `{0, 255}`. Otsu is a **voxel-level segmentation operation**. It is not a strut classifier and does not label a complete strut by itself. Later stages use the mask and localized geometry to derive evidence for each expected strut.

The implementation computes Otsu from a histogram. For threshold `t`, with class weights `w0(t)` and `w1(t)`, class means `mu0(t)` and `mu1(t)`, and global mean `mu`, the between-class variance is:

```text
sigma_between^2(t) = w0(t) * w1(t) * (mu0(t) - mu1(t))^2
```

The selected threshold maximizes this between-class variance. The code uses a streamed histogram so it does not need to hold the entire TIFF and a second full-size mask in ordinary Python memory at once.

### Stage D — skeletonization

The binary mask is converted to a skeleton using the existing Aman skeletonization implementation. The skeleton is a one-voxel-wide centerline representation of connected foreground material. It is used for endpoint proximity and connectivity evidence; it is not itself the thickness measurement.

Saved supporting artifacts include:

- Otsu mask TIFF;
- Otsu mask NumPy array;
- skeleton NumPy array;
- sparse centerline-label NPZ for the all-strut measurement tool.

### Stage E — per-strut localization

For every registered strut, the endpoint pair is read from the identity graph. The endpoint vector is:

```text
v = p1 - p0
```

The geometric length in voxels is:

```text
L = ||v||_2
```

The centerline is sampled at:

```text
N = max(2, ceil(L) + 1)
```

equally spaced XYZ points between the endpoints. Each point is rounded into ZYX for volume indexing. The saved per-strut row retains the endpoint coordinates, junction IDs, length, support counts, thickness statistics, and failure evidence.

### Stage F — centerline labels and ownership

The measurement MCP tool writes a sparse `centerline_labels.npz` containing ZYX coordinates and a corresponding `strut_id` value. A rounded centerline sample is assigned to the current strut. If two struts claim the same rounded voxel, the value is set to `-1`, indicating an ambiguous shared junction rather than pretending that the voxel belongs exclusively to one member.

This creates traceability from a measured row to a set of voxels, while preserving the important topology fact that junction voxels are shared. It is not a full material-component label volume: the labels represent sampled expected centerlines and ambiguous overlaps, not every foreground voxel in the lattice.

### Stage G — cross-section thickness measurement

For each strut, local cross-sections are sampled along the expected endpoint axis. At each station, the code searches the raw TIFF along the local normal directions for an ISO-50-style material boundary. Valid observed radii are collected across stations.

For a station radius `r_i` in voxels:

```text
d_i = 2 * r_i
```

The row-level diameter is the median of valid station diameters:

```text
diameter_median_voxels = median(d_i)
```

Thickness conversion uses the voxel pitch `s` in micrometres:

```text
thickness_median_um = diameter_median_voxels * s
thickness_median_mm = thickness_median_um / 1000
```

The output also stores the 10th and 90th percentiles of the station diameters. These are localized measurements; they are not the same as a volume-wide area fraction.

### Stage H — axial support and gap evidence

The rounded centerline samples are tested against the Otsu foreground mask. If `H` sampled in-bounds centerline positions hit foreground and `M` positions are in bounds, the observed axial support fraction is:

```text
observed_axial_fraction = H / max(1, M)
```

The metrology record also stores whether support is continuous and the longest unsupported axial run in voxels. These quantities provide the evidence used to distinguish a mostly absent member from a member with a localized break.

### Stage I — classify evidence conservatively

The classifier applies the following ordered logic:

1. Intentionally absent or skin-embedded design members become `not_applicable`.
2. Invalid or incomplete measurements become `uncertain` and `review`.
3. If axial coverage and unsupported-gap checks both fail, coverage below `0.35` becomes `missing`; coverage at or above `0.35` becomes `broken`.
4. A failed continuous-support check or unsupported gap larger than 3 voxels becomes `broken`.
5. If the 90th-percentile radial deviation exceeds the effective radial tolerance, negative signed deviation becomes `thin`, positive signed deviation becomes `thick`.
6. Centerline displacement beyond tolerance is kept as a review-level `bent_or_misaligned` signal unless the excess is within the registration-uncertainty band, in which case it becomes `uncertain`.
7. A valid row inside all declared tolerances becomes `healthy`.

The important missing/broken policy is:

```text
missing = axial and gap failures AND observed_axial_fraction < 0.35
broken  = axial and gap failures AND observed_axial_fraction >= 0.35
```

The `0.35` boundary is a screening policy, not a physical law or manually validated ground truth.

For centerline displacement, the stability rule is conceptually:

```text
excess = p90_centerline_displacement - effective_centerline_tolerance
if excess <= registration_uncertainty:
    uncertain / review
else:
    bent_or_misaligned / review
```

This prevents registration error from being reported as a confirmed bend.

## 6. Why the current answer is 336

The current post-fix CSV contains 18,468 rows and the following exact class counts:

```text
missing = 246
broken  = 90
total   = 246 + 90 = 336
rate    = 336 / 18,468 = 0.0181936 = 1.82%
```

The result changed after the scale-aware registration/stability fix. The corrected geometry changes which centerline samples intersect material and which stations meet support/gap criteria. Therefore, the mix can change even when the identity graph is unchanged. The current result is not obtained by simply counting dark pixels or by thresholding a whole-volume area fraction.

## 7. Comparison with the friend pipeline

The friend’s notes describe a stricter promotion system with threshold perturbation checks, registration-transform separation, design-intent checks, and human spot checks. Its reported headline comparison was approximately:

| Evidence policy | Missing | Broken/disconnected | Combined |
|---|---:|---:|---:|
| Current Aman post-fix classifier | 246 | 90 | **336** |
| Friend’s strict auto-supported queue | 202 | 12 | **214** |

These numbers are not necessarily contradictory measurements of the same label definition. The current classifier promotes a row when the declared axial/gap evidence crosses its screening rule. The friend pipeline keeps more borderline candidates in review and only promotes candidates after additional stability and spot-check gates. A fair comparison requires running both systems on the same registered graph, the same TIFF, the same transform, and a documented shared label contract.

The friend checkout at `/Users/amannindra/Projects/llnl_DSC/llnl_data_science_challenge_2026_GPT_30july` is an extracted snapshot without a Git repository or inspectable `dashboard` branch. It should not be wholesale copied into this checkout. Its phase-specific backend code uses a different `src.part2.*` namespace and different artifact contracts. The current isolated dashboard is already present and tested; selective backend adapters are safer than replacing the dashboard tree.

## 8. MCP server surface

### Unified dashboard/evidence MCP

`part2/defect_cartographer/mcp_server.py` exposes:

- `get_pipeline_summary` — aggregate counts, reliability, thickness, and coverage metadata.
- `get_strut_details` — one saved strut row by ID.
- `filter_defect_candidates` — filter rows by class, region, height, orientation, and feature ranges.
- `compare_defect_groups` — compare allow-listed metrics by prediction, region, height band, or orientation.
- `get_methodology` — return a bounded method/report section.
- `prepare_threejs_scene` — prepare a bounded scene specification for the viewer.
- `get_strut_ct_evidence` — render bounded orthogonal raw-CT evidence for one strut.

The native server mounts Aman’s original CT tools once under `raw_ct`, preventing duplicate nested tool names.

### Aman raw CT MCP tools used by the measurement workflow

The relevant raw tools in `Aman_src/mcp_server.py` are:

- `register_json_to_tiff` — establish/record JSON-to-TIFF geometry and coordinate provenance.
- `segment_tiff_otsu` — compute the global voxel threshold and write a streamed mask.
- `read_tiff` — convert the TIFF mask into a NumPy array artifact.
- `skeletonize` — call the existing skeletonization implementation.
- `measure_tiff_struts` — measure all registered struts, write CSV, write centerline labels, and report aggregate measurement counts.
- `run_full_defect_workflow` — rebuild the full dashboard classification artifacts from the metrology/classification inputs.
- `get_full_defect_summary`, `get_full_strut_details`, and `filter_full_struts` — query the complete classified table.
- `get_human_review_anchors` and `compare_human_anchors_to_full_lattice` — preserve and compare human-review evidence.

The raw server also contains lower-level utilities for reading NPY/TIFF data, visualizing slices, comparing lattice JSON, and saving skeleton outputs.

### Persistent agentic lifecycle MCP

`Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py` adds:

- `agentic_create_run`
- `agentic_start_run`
- `agentic_get_run_status`
- `agentic_resume_run`
- `agentic_cancel_run`
- `agentic_list_run_artifacts`
- `agentic_ask`

The lifecycle layer delegates numerical work to the existing Aman MCP module. It does not create one LLM agent per class or per strut. It creates one durable run with named stages and records their outputs.

## 9. Persistent orchestration model

The durable run store uses SQLite with WAL mode. A run has ordered stages:

```text
validated
registered
segmented
skeletonized
measured
reconciled
qa
reported
```

Each stage can be `pending`, `running`, `succeeded`, `failed`, or `cancelled`. A resumed run skips verified successful stages and retries unfinished stages. Each registered artifact is constrained to the run artifact root and receives a SHA-256 digest, size, stage name, and path. This gives the frontend and a reviewer a durable record of what was produced and which stage produced it.

The current deterministic callbacks write run-local manifests and reports. They can execute a configured TIFF/registered-identity run, but the existing dashboard artifacts remain available independently so the UI can be opened without rerunning the large TIFF computation.

## 10. Frontend architecture

The Streamlit entrypoint is `part2/app.py`. It loads the saved full-lattice artifacts and exposes:

- **Overview** — aggregate classification and reliability summary.
- **Strut Explorer** — row-level lookup/filtering.
- **Visual Analysis** — figures and spatial/CT evidence.
- **System Design** — pipeline and architecture explanation.
- **Copilot** — bounded agent-facing explanations and queries.

The Three.js viewer consumes a bounded scene specification and saved lattice data. It does not require the browser to receive the entire raw TIFF. CT evidence is rendered for selected struts and displayed as bounded orthogonal crops.

The local frontend is started with:

```bash
cd /Users/amannindra/Projects/llnl_DSC/llnl_data_science_challenge_2026-agentic
PYTHONPATH=part2:. conda run -n DSC streamlit run part2/app.py \
  --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

## 11. Output artifacts

The current important artifacts are:

- `part2/artifacts/sample/full_strut_classification.csv` — 18,468 row dashboard table.
- `part2/artifacts/sample/full_pipeline_metrics.json` — aggregate counts, hashes, and warning metadata.
- `part2/artifacts/sample/full_lattice_scene.npz` — bounded 3D viewer data.
- `Aman_Scripts/outputs/simple_strut_metrology/strut_metrology.json` — detailed per-strut TIFF/STL metrology evidence.
- `Aman_Scripts/outputs/simple_strut_metrology/registration_report.json` — registration and held-out audit metadata.
- `Aman_Scripts/outputs/missing_broken_struts.csv` — standalone removable/exportable 336-row subset.
- `Aman_Scripts/outputs/mcp_tiff_strut_measurements/otsu_mask.tif` — saved Otsu voxel mask.
- `Aman_Scripts/outputs/mcp_tiff_strut_measurements/skeleton.npy` — saved skeleton.
- `Aman_Scripts/outputs/mcp_tiff_strut_measurements/centerline_labels.npz` — sparse strut-to-centerline voxel labels.

The missing/broken CSV is deliberately standalone. It can be removed without changing the dashboard’s main table, or it can be copied into a frontend-specific artifact directory after an explicit adapter change.

## 12. Verification performed

The current checkout passed:

```text
part2/tests: 45 passed
full classification table: 18,468 rows
missing rows: 246
broken rows: 90
standalone missing/broken rows: 336
```

The table and metrics were inspected directly rather than inferred from a chart. The current Streamlit processes report healthy endpoints on the local ports, including the isolated checkout process on port 8501. Because multiple historical Streamlit processes exist, use the process command line and checkout path when diagnosing port confusion.

## 13. Limitations and poster wording

Use the following wording on the poster:

> “The pipeline identified 336 missing/broken evidence classifications among 18,468 expected struts using registered geometry, Otsu voxel segmentation, skeleton support, local CT cross-section measurements, and conservative axial-gap rules. These are automated screening labels, not independently validated defect ground truth.”

Do not claim:

- that Otsu directly classifies struts;
- that a volume-wide area fraction proves a local defect;
- that all centerline displacement is a physical bend;
- that the 35% boundary is a material-science law;
- that the model launched 18,468 separate language-model agents;
- that `336 / 18,468` is validated manufacturing defect prevalence.

The largest open validation need is a shared adjudicated set of struts reviewed against the raw CT and registered design, followed by a comparison of both pipelines under the same label contract. The `uncertain` pool is intentionally large because it contains cases where the evidence does not support a safe automatic subtype.

## 14. Reproduction checklist

1. Activate the `DSC` conda environment.
2. Confirm the raw TIFF and registered identity files exist.
3. Run registration/metrology and inspect the held-out registration report.
4. Run Otsu segmentation and skeletonization.
5. Measure all expected struts and write the CSV plus centerline-label NPZ.
6. Reconcile that the output contains exactly 18,468 unique strut IDs.
7. Apply the conservative classifier and preserve review/excluded states.
8. Rebuild the dashboard artifacts.
9. Query `get_pipeline_summary` and filter `missing`/`broken` through the MCP service.
10. Run `PYTHONPATH=part2 conda run -n DSC python -m pytest part2/tests -q`.
11. Start Streamlit and inspect the actual rendered dashboard.

The experiment remains isolated and uncommitted so the current implementation can be reviewed, compared with the friend’s stricter pipeline, or discarded without changing the original working checkout.
