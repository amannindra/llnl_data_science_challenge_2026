# Scripts Component Refactor Implementation Plan

## Scope

This document is the working source of truth for the current implementation pass.
The pass refactors the existing `Scripts` utilities into reusable components,
preserves their command-line behavior and artifacts, and adds fail-fast validation.

The separate TIFF strut-defect detector is deliberately **deferred**. Its design
will be saved in a second Markdown file only after this plan is complete. No
detector, classifier, registration optimizer, or defect-labeling pipeline is to be
implemented as part of this pass.

## Constraints

- All new or changed implementation code remains under `Scripts/`.
- Existing files in `src/`, `src2/`, and the MCP server are out of scope.
- Existing CLI entry points and established output filenames remain usable.
- Importing a script or component must not perform analysis or write files.
- Repeated logic belongs in `Scripts/Components/`, not in individual CLIs.
- Production modules should remain focused and preferably below 400 lines.
- Large TIFF files must be opened lazily or as memory maps where practical.
- Array coordinates are explicit: NumPy volumes use `[z, y, x]`; geometry and
  report coordinates use `(x, y, z)`.
- Validation is fail-fast. A failing stage is fixed and rerun before later stages.
- Each major public component receives at least 10 independent checks.

## Intended Component Layout

`Scripts/Components/` will contain the reusable implementation:

- `paths.py`: repository/data/output discovery and safe output-directory helpers.
- `asset_io.py`: JSON, NumPy, TIFF, STL, and LFS-pointer-aware input inspection.
- `coordinates.py`: explicit XYZ/ZYX conversion and homogeneous transforms.
- `lattice_graph.py`: lattice JSON parsing, strut normalization, and coincident-node welding.
- `segmentation.py`: reusable threshold and mask helpers already used by scripts.
- `reporting.py`: deterministic JSON/CSV writing and manifest helpers.
- `testing.py`: shared check collector, numerical assertions, and JSON summaries.

Only components justified by current scripts will be added. TIFF defect-specific
modules such as registration, strut extraction, feature calculation, and defect
classification remain part of the deferred plan.

## Implementation Stages and Gates

### Stage 1 — Inventory and baseline

1. Record all current Python entry points, their import behavior, CLI arguments,
   output filenames, and shared logic.
2. Run the existing Task 1, Task 2, and Task 3 adversarial scripts under the `DSC`
   environment.
3. Preserve baseline check totals and artifact contracts.

Gate: every existing adversarial script passes before refactoring begins.

### Stage 2 — Component foundation

1. Create an importable `Scripts.Components` package.
2. Implement paths, input inspection, coordinates, graph handling, reporting,
   segmentation helpers, and the shared test harness.
3. Define small dataclasses or typed records for returned metadata where useful.
4. Keep library functions free of CLI printing and filesystem writes unless the
   function is explicitly a writer.

Gate: component-level tests pass with at least 10 checks for every major public
component.

### Stage 3 — Existing-script refactor

Refactor all current Python files under `Scripts/` to use the components while
preserving their direct-execution interfaces:

- `analyze_json.py`
- `analyze_npy.py`
- `analyze_project_assets.py`
- `analyze_tiff_stl.py`
- `create_pdf_contacts.py`
- `find_missing_points.py`
- `view_tif_napari.py`
- Task 1, Task 2, and Task 3 test harnesses where shared test code is duplicated

The current JSON occupancy detector remains a clearly marked legacy diagnostic;
it must not be presented as a validated physical TIFF defect detector.

Gate: imports are side-effect free, `--help` works where applicable, and legacy
output filenames remain unchanged.

### Stage 4 — Refactor validation

Add independent executable tests under `Scripts/ComponentTests/`:

1. paths and repository discovery: at least 10 checks
2. asset I/O and LFS-pointer handling: at least 12 checks
3. coordinate conversion and transforms: at least 12 checks
4. lattice parsing and node welding: at least 12 checks
5. segmentation helpers: at least 12 checks
6. deterministic reporting/writers: at least 10 checks
7. import safety and CLI compatibility across existing scripts: at least 10 checks

Synthetic fixtures must be deterministic and small. Tests must not load an entire
1 GB volume into RAM unless explicitly exercising a full-data smoke test.

Gate: each test executable exits nonzero on failure and writes an inspectable JSON
summary; the suite runner stops at the first failed stage.

### Stage 5 — Regression and artifact QA

1. Rerun all legacy Task 1–3 checks.
2. Run the component suite twice to verify deterministic normalized output.
3. Smoke-test representative existing CLIs against real project assets.
4. Inspect generated JSON/CSV/image artifacts for schema, non-emptiness, and paths.
5. Document dependency and runtime assumptions for the `DSC` environment.

Gate: legacy and new tests pass, no unexpected source-tree writes occur on import,
and generated validation summaries agree across repeated runs.

### Stage 6 — Documentation handoff

1. Update the completion log below with concrete files, check counts, commands,
   results, deviations, and known limitations.
2. Add a concise component README and test-running instructions.
3. Save the separate TIFF defect-detection design in its own Markdown file,
   explicitly marked deferred and not implemented.

## Completion Log

This section is append-only during implementation.

- 2026-07-24 — Plan saved before implementation. Scope fixed to the component
  refactor and validation foundation; TIFF defect detection is deferred.
- 2026-07-24 — Baseline gate passed in conda environment `DSC`: all 17 existing
  Task 1–3 adversarial executables passed, totaling 128/128 checks (Task 1: 34,
  Task 2: 45, Task 3: 49). Refactoring may proceed from a known-good baseline.
- 2026-07-24 — Inventory confirmed 27 Python files / 3,586 lines: seven root
  utilities, three duplicated Task harnesses, and 17 adversarial tests. Import
  side effects are present in `analyze_json.py` and `analyze_npy.py`; repeated
  path discovery, LFS parsing, JSON/NumPy loading, hashing, coordinate handling,
  graph welding, and PASS/FAIL reporting are the primary refactor targets.
- 2026-07-24 — First component gate passed independently in `DSC`: paths 22/22,
  asset I/O 33/33, coordinates 31/31, lattice graph 36/36, and segmentation
  33/33 (155/155 total). Real-data checks confirm both TIFF stacks are readable,
  the raw 1 GB TIFF is memory-mappable, registered JSON contains 18,468 struts,
  raw repeated-node IDs weld to a single physical component, and `unitcell.npy`
  can be inspected without eager loading.
- 2026-07-24 — Component refactor implemented across all seven root utilities
  and the three Task harnesses. Imports are side-effect free; shared modules now
  own paths, LFS-aware JSON/NPY/TIFF/STL I/O, XYZ/ZYX conversions, lattice graph
  parsing and welding, segmentation helpers, deterministic reporting, and test
  collection. The historical JSON-guided occupancy method remains opt-in under
  `legacy_occupancy.py`, keeps its CSV/PNG names, and is labeled unvalidated; no
  new TIFF defect detector was started.
- 2026-07-24 — Independent adversarial review found and drove fixes for mapping
  key collisions, CSV schema drift, non-ZYX TIFF slicing, dangling-strut
  provenance, string endpoint parsing, negative-intensity occupancy, fractional
  sample arguments, STL centralization, LFS error consistency, isosurface
  ZYX-to-XYZ conversion, runner fail-fast semantics, and structured summaries.
- 2026-07-24 — Aggregate component gate passed twice in `DSC`: 307/307 checks
  across nine suites. Normalized JSON and Markdown summaries were byte-identical
  across both runs; final SHA-256 values are `b8951a9f53617fb32a7bf13e49c052b814344dafe07db126d8c1b62f2178030d`
  (JSON) and `847621d74a2e48dac5e19ca1cb175c3265d9ec53a04f3798d9e38393e3602bc2`
  (Markdown).
- 2026-07-24 — Added a 25-check real-asset gate covering both restored TIFFs,
  their exact shapes/axes/dtypes/pages, lazy page access, the duplicate raw
  volume, `{0,255}` segmented encoding, the registered 18,468-strut graph,
  3,430-node one-component weld, and a restored binary STL. Peak RSS growth was
  85.3 MiB, below the 512 MiB gate.
- 2026-07-24 — Final legacy regression passed: all 17 Task 1–3 executables and
  128/128 original checks. `find_missing_points.py --no-figure` independently
  passed 11/11 checks and produced valid `defect_report.json` plus both CSVs;
  the report contains two missing physical JSON points and 74 deleted strut
  records with precision/recall 1.0 against its deliberately damaged JSON.
- 2026-07-24 — Documentation completed in `Components/README.md` and
  `requirements.txt`. The separate future detector design was archived as
  `TIFF_DEFECT_DETECTION_DEFERRED_PLAN.md`; every detector implementation box
  remains unchecked and no full TIFF defect inspection was run.
- 2026-07-24 — FINAL GATE: 334/334 component checks passed across ten suites on
  two consecutive runs. Normalized outputs were byte-identical. Final SHA-256:
  `c27be7f88de99fc956f86df65a56434c436ab43a3aff0208fc6eeeed858e4de6`
  for the JSON summary and
  `e50bcad4bd0236f714e7a9dcbaf079b66c49ff0916245f2d3925a5793b3d4416`
  for the Markdown summary. Known limitation: the opt-in legacy occupancy
  heuristic remains scientifically unvalidated and is not a defect verdict.
