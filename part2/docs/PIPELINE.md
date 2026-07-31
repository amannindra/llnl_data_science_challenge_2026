# Lattice CT Defect-Detection Pipeline — Architecture Reference

Repo: `llnl_data_science_challenge_2026-agentic` · branch `agent/defect-agent-experiment` · as of 2026-07-30.
Diagram: [`agentic_pipeline_diagram.svg`](./agentic_pipeline_diagram.svg) in this same directory.

This document replaces an earlier, stale 6-step flowchart (92 deleted struts / 228 candidates / 677 ambiguous /
207 clustered / 21 clear) that no longer matches the code. The system described here classifies the **full
18,468-strut lattice**, not a small sample, and the numbers below are read directly from the current pipeline
outputs, not estimated.

## 0. The one thing to understand before anything else

This is **not** a single linear pipeline. There are two independent paths that both start from the same raw CT
toolbox and end at separate artifact stores:

- **Path A — deterministic metrology + classification.** Plain Python scripts, no LLM, no agent framework. This
  is mature and is what the Streamlit dashboard and the LLM copilot both actually read from today.
- **Path B — the agentic orchestration runtime.** A deterministic (also non-LLM) 8-stage state machine with
  SQLite-backed run tracking, built to be resumable and auditable. It has been built and lightly exercised but
  **has never completed a real end-to-end run** — as of this writing its database holds exactly 2 dev/test run
  rows (one stalled in `active`, one `cancelled`) and 0 registered artifacts.

A third layer, the **LLM agentic copilot** (OpenAI Agents SDK), sits on top of Path A only — it has no
connection to Path B. Do not confuse "agentic orchestration runtime" (Path B, deterministic) with "agentic
copilot" (the actual LLM-driven layer) — the codebase itself uses "agentic" for both, which is the most common
source of confusion when reading it.

## 1. Raw inputs

| Input | Location | Notes |
|---|---|---|
| CT volume | `data/missing_struts/tif_stacks/*.tif` | 761×815×837 uint16, native (uncropped) grayscale |
| Registered design graph | `data/missing_struts/registered_jsons/*.json` | `[x,y,z]` strut endpoints; 3,430 physical nodes, 18,468 unique expected edges after welding aliased junction IDs across unit-cell boundaries |
| CAD/STL surface model | referenced by `ct_surface_metrology.py` | nominal Ti-5553 octet lattice, 424 µm design strut diameter, 58.1 µm/voxel |

Coordinate convention: registered/graph coordinates are `[x,y,z]`; NumPy/TIFF volumes are indexed `[z,y,x]`.
Sampling an expected edge means converting through the registration transform and indexing `volume[z,y,x]`.

## 2. Raw CT toolbox — `Aman_src/mcp_server.py`

`FastMCP("CT Segmentation")`, 17 tools. This is the shared low-level primitive layer — both Path A and Path B
call these Python functions directly (in-process), not through the MCP wire protocol:

`register_json_to_tiff`, `read_json`, `read_npy`, `segment_tiff_otsu`, `skeleton_to_json`, `compare_octet_json`,
`read_tiff`, `segment_ct_dataset`, `visualize_slice`, `skeletonize`, `measure_tiff_struts`,
`run_full_defect_workflow`, `get_full_defect_summary`, `get_full_strut_details`, `filter_full_struts`,
`get_human_review_anchors`, `compare_human_anchors_to_full_lattice`.

## 3. Path A — deterministic metrology & classification (production)

Two scripts, run as a standalone Python workflow (`Aman_Scripts/run_simple_strut_metrology.py`), no agent
framework involved:

1. **`Aman_Scripts/Components/ct_surface_metrology.py`** — 7-DOF similarity registration (rigid + uniform scale)
   fitting the STL surface model directly against native TIFF intensities, plus a registration-stability gate.
   This is the fix that replaced an earlier rigid-only registration which was systematically overcounting
   `bent_or_misaligned`.
2. **`Aman_Scripts/Components/defect_classification.py`** — labels each of the 18,468 struts into one of 8
   classes: `healthy`, `missing`, `broken`, `thin`, `thick`, `bent_or_misaligned`, `uncertain`,
   `not_applicable`.

Outputs land in `Aman_Scripts/outputs/`:
- `strut_defect_classification/strut_defect_classification.csv` — per-strut automated classification
- `strut_defect_classification/human_review_labels.csv` — human-in-the-loop overrides (see §5)
- `mcp_tiff_strut_measurements/strut_measurements.csv` — native-TIFF thickness/diameter measurements
- `simple_strut_metrology/strut_metrology.json` — per-strut length, gap, and displacement metrology

### 3.1 Core results builder

**`part2/defect_cartographer/core/full_results.py`** (`build_full_results_table` /
`build_full_dashboard_artifacts`) is the join point. It:

1. Loads the classification CSV, hard-validates it has exactly 18,468 rows with unique `strut_id`s and only the
   8 known labels.
2. Loads the registered graph and the saved alignment artifact, rebuilds per-strut geometry
   (`build_strut_table`).
3. Merges geometry + classification (`validate="one_to_one"` — every registered strut must have a
   classification, no silent drops).
4. Applies human-review overrides on top (`_apply_human_review_overrides`, §5).
5. Left-joins native-TIFF thickness measurements and metrology (gap fraction, alignment error, occupancy).
6. Writes the dashboard artifact set to `part2/artifacts/sample/`:
   - `full_strut_classification.csv` — the full per-strut table
   - `full_pipeline_metrics.json` — aggregate counts and coverage
   - `full_alignment.json`, `full_thickness_reference.json`
   - `full_lattice_scene.npz` — compact Three.js scene for the 3D viewer
   - `full_defect_report.md` — narrative report

This artifact directory (`part2/artifacts/sample/*`) is the **single source of truth** — everything downstream
(dashboard, both MCP servers, the LLM copilot) ultimately reads from it, either directly off disk or through
`service.py`.

### 3.2 Current real numbers (of 18,468 struts)

From the registration-similarity-fit branch's regenerated `full_pipeline_metrics.json` — the current best
validated science:

| Class | Count |
|---|---|
| `bent_or_misaligned` | 3,816 |
| `uncertain` | 6,973 |
| `healthy` | 6,598 |
| `missing` | 246 |
| `broken` | 90 |
| `thin` | 6 |
| `thick` | 0 |
| `not_applicable` | 739 |

`valid_thickness_measurement_count`: 17,995. `median_diameter_um`: ≈356.8. `ground_truth_available`: `false` —
every artifact and report explicitly states these are automated evidence classifications, not validated
manufacturing defects.

**Known state as of this writing:** this `-agentic` repo's own copy of `part2/artifacts/sample/*` still reflects
the *pre-fix* registration (`bent_or_misaligned: 12,723`), because the registration-fix scripts were ported into
`Aman_Scripts/Components/` but `core/full_results.py` has not yet been re-run here to regenerate the dashboard
artifacts. The science is correct and merged; the artifact regeneration step is the one remaining action, not
covered by this documentation pass.

## 4. Path B — agentic orchestration runtime (experimental)

`part2/defect_cartographer/agentic_orchestration/` — explicitly **not** an LLM tool-calling loop. It's a
deterministic, durable, resumable pipeline runner:

- **`models.py`** — `StageStatus` enum (`PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED`), exceptions
  (`TransitionError`, `PathContainmentError`, `RunCancelled`), frozen dataclasses (`ArtifactRecord`, `RunRecord`,
  `StageResult`, `StageContext`).
- **`runtime.py`** — `AmanOrchestratorRuntime.run(run_id)` iterates a fixed, ordered stage list, skipping any
  already `SUCCEEDED` (resume-safe). For each stage: transitions to `RUNNING`, emits a `stage_started` event,
  invokes the injected callback, registers returned artifacts and transitions `SUCCEEDED` on success, or
  transitions `FAILED`/`CANCELLED` and re-raises on error/cancellation.
- **`pipeline.py`** — `build_callbacks(config, raw_module)` builds the 8 named stage callbacks, each wrapping
  functions from the raw CT toolbox (§2) directly:

  | Stage | What it does |
  |---|---|
  | `validated` | writes `input_manifest.json` (sha256 of tiff/registered_json, coordinate convention, voxel pitch) |
  | `registered` | writes `registration_manifest.json` — **trusts** the supplied registered JSON (`"registration_validation": "not_recomputed_by_agentic_wrapper"`) rather than recomputing it |
  | `segmented` | `raw_module.segment_tiff_otsu` |
  | `skeletonized` | `raw_module.read_tiff` → `raw_module.skeletonize` |
  | `measured` | `raw_module.measure_tiff_struts` |
  | `reconciled` | hard-asserts exactly 18,468 unique `strut_id` rows in the measurement output, else raises |
  | `qa` | computes valid-measurement count/average thickness, writes `qa_metrics.json` with `ground_truth_available: false` |
  | `reported` | writes a minimal `agentic_report.md` |

- **`persistence.py`** — `RunStore(database, artifact_root)`: SQLite in WAL mode, 4 tables (`runs`, `stages`,
  `artifacts` content-addressed by sha256, `events` append-only log), a strict `_ALLOWED` stage-transition
  dict, and path-containment enforcement (`PathContainmentError` if an artifact write would escape
  `artifact_root`).

Runs live under `part2/artifacts/runs/agentic/<run_id>/`, entirely separate from Path A's
`part2/artifacts/sample/`. **Nothing reads Path B's output today** — not the dashboard, not the LLM copilot.

### 4.1 Control surface

Path B is only reachable through the **experimental** MCP server (§6.2)'s `agentic_*` tools:
`agentic_create_run`, `agentic_start`, `agentic_resume`, `agentic_cancel`, `agentic_get_run_status`,
`agentic_list_run_artifacts`, `agentic_ask`. That server is not imported anywhere in `part2/app.py` — it's a
separate standalone entrypoint (`Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py`).

## 5. Human-in-the-loop

`Aman_Scripts/outputs/strut_defect_classification/human_review_labels.csv` — analyst-confirmed labels. When
present, `_apply_human_review_overrides` (`core/full_results.py`) overlays them on top of the automated
classification for the matching `strut_id`: the label, confidence (`"high"`), and status (`"accepted"`) are
overwritten, and `human_review_note`/`human_reviewer` columns are attached. Overrides are validated against the
same 8-label vocabulary as the automated classifier.

**This overlay only reaches Path A.** A direct grep of `agentic_orchestration/` and `agents/` for
`human_review` returns zero matches — Path B's stage callbacks and the LLM copilot layer have no human-review
hook. If a strut's label is corrected by a human reviewer, that correction is visible in the dashboard (because
the dashboard reads Path A's artifacts) but would not affect anything computed by Path B or referenced by the
copilot's own reasoning about raw tool output.

## 6. MCP server layer

Three separate FastMCP servers exist in this repo. Only one is wired into the live dashboard.

### 6.1 Canonical server — `part2/defect_cartographer/mcp_server.py` (LIVE)

`FastMCP("Unified Lattice CT Evidence")`. At import time it dynamically loads and mounts `Aman_src/mcp_server.py`
under the `raw_ct` namespace (via `importlib.util.spec_from_file_location` + `exec_module`, not a normal
`import`, for isolation). Exposes 7 dashboard-facing tools that read Path A's artifacts through
`service.py`/`DEFAULT_SERVICE` (which wraps `DEFAULT_CONFIG.output_dir`, i.e. `part2/artifacts/sample/`).
System instructions explicitly state candidate labels are not validated defects.

This is the server both the Streamlit dashboard's MCP tools **and** the LLM copilot layer (§7) talk to — same
live process/instance.

### 6.2 Experimental server — `isolated_unified_mcp/mcp_server.py` (EXPERIMENTAL)

`Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py`. An additive superset: the same 7
dashboard tools + mounts `raw_ct` + the 7 `agentic_*` run-lifecycle tools that control Path B. Its own README
states it "does not replace the current server." `_run_dir()` validates run IDs against a strict regex and
enforces path containment; `_load_orchestration()` restricts loadable modules to paths resolving under this
repo's root ("never an external repository"). `agentic_ask()` lazily imports
`defect_cartographer.agents.run_copilot` with a graceful fallback if unavailable.

Not imported by `part2/app.py` — must be run as its own process (`PYTHONPATH=part2:. conda run -n DSC python
Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py`).

### 6.3 What the dashboard tools actually return

`service.py`'s `DefectAnalysisService.get_pipeline_summary()` reads `full_pipeline_metrics.json` +
`full_alignment.json` + the classification table and returns aggregate evidence (scope, sample size, per-class
counts, coverage, uncertain fraction, thickness stats, alignment reliability) without exposing raw CT voxels or
local filesystem paths — the same guarantee is echoed in the copilot's safety instructions (§7).

## 7. LLM agentic copilot — `part2/defect_cartographer/agents/`

The one genuinely LLM-driven layer, built on the **OpenAI Agents SDK** (`Agent`, `Runner`, `RunConfig`,
`function_tool`).

- **`coordinator.py`** — `build_analysis_coordinator(model, measurement_subagent, visualization_subagent)`: a
  manager agent with the two specialists below wired in via `.as_tool(...)`, `output_type=CopilotResponse`.
- **`measurement_qa.py`** — `build_measurement_qa_subagent(model)`, 5 tools (`ANALYSIS_MCP_TOOLS`).
- **`visualization_reporting.py`** — `build_visualization_reporting_subagent(model)`, 5 tools
  (`VISUALIZATION_MCP_TOOLS`, overlapping with the QA set); instructions explicitly forbid placing raw
  geometry/CT voxel data into the model's context.
- **`mcp_tools.py`** — `call_readonly_mcp(name, arguments)` uses `fastmcp.Client(mcp)`, importing `mcp` from
  `..mcp_server` — i.e. the **canonical** server (§6.1), not the experimental one. All tool calls are
  in-process.
- **`shared.py`** — `GLOBAL_SAFETY_INSTRUCTIONS`, embedded in every agent's instructions: use
  exploratory-candidate-not-validated-defect language, never claim ground-truth performance, only state facts
  grounded in actual tool output (not model memory), never leak raw CT voxel context.
- **`copilot.py`** — `DEFAULT_AGENT_MODEL = "gpt-5.6-terra"` (override via `OPENAI_MODEL`). `copilot_status()`
  checks whether `OPENAI_API_KEY` is set. `run_copilot(prompt, page_context=None, model=None)` bounds the prompt
  to 8,000 characters and page context to 4,000 characters of JSON, then calls `Runner.run_sync(...,
  max_turns=8, run_config=RunConfig(workflow_name="Lattice CT Analysis Copilot", tracing_disabled=True,
  trace_include_sensitive_data=False))`.

If `OPENAI_API_KEY` is unset, the whole layer disables gracefully with **no external API call**, returning a
deterministic `CopilotResponse(status="disabled_no_api_key")`.

`CopilotResponse` schema (`schemas.py`): `answer: str`, `evidence: list[str]`, `filter_updates: dict`,
`selected_strut_id: int | None`, `warnings: list[str]`, `status: str = "ok"`.

## 8. Frontend — `part2/app.py`

Streamlit dashboard. Two independent data paths feed it:

1. **Direct file read** — `dashboard/data.py`'s `load_dashboard_artifacts()` reads
   `full_strut_classification.csv` + `full_defect_report.md` (required) plus `full_pipeline_metrics.json` /
   `full_alignment.json` / `full_thickness_reference.json` straight off disk. This is what renders the main
   strut table and the 3D lattice scene — it bypasses MCP entirely for the bulk data load.
2. **Copilot chat** — `dashboard/pages.py`'s `render_copilot()` calls `copilot_status()` and, on submit,
   `run_copilot(prompt, page_context={"page": "copilot"})`, i.e. the LLM layer in §7.

Path B (the orchestration runtime) is not referenced anywhere in `app.py` or `dashboard/pages.py` — it has no
UI surface today.

## 9. End-to-end summary (mapped to the diagram's numbered steps)

1. **Raw inputs** — CT volume, registered design graph, CAD/STL model.
2. **① Raw CT toolbox** (`Aman_src/mcp_server.py`) — shared primitives, called in-process by both paths below.
3. **②a Path A** (production) — 7-DOF registration + 8-class defect classification, standalone script, no
   agent framework.
   **②b Path B** (experimental) — 8-stage deterministic orchestration state machine, SQLite-tracked, never
   completed a real run.
4. **Human review overlay** feeds into Path A only.
5. **③a Artifact Store A** (`part2/artifacts/sample/*`) — the single source of truth for the dashboard.
   **③b Artifact Store B** (`part2/artifacts/runs/agentic/*`) — isolated, currently empty of real runs.
6. **④a Canonical MCP server** (LIVE, serves both the dashboard's tools and the LLM copilot).
   **④b Experimental MCP server** (adds the `agentic_*` control tools for Path B; standalone process).
7. **⑤ LLM agentic copilot** (OpenAI Agents SDK; live only with an API key; talks only to the canonical MCP
   server, i.e. only ever sees Path A's data).
8. **⑥ Streamlit dashboard** — direct-reads Artifact Store A for the table/3D scene, embeds the copilot chat.

## 10. What is genuinely production vs. experimental (honesty check)

| Component | Status | Evidence |
|---|---|---|
| Registration + classification (Path A) | **Live, validated** | Regenerated artifacts, 469/469 tests passing on the registration-fix branch |
| Human review overlay | **Live** | Wired into `full_results.py`, feeds the dashboard |
| Canonical MCP server | **Live** | Imported by both dashboard tool paths and the LLM copilot |
| Streamlit dashboard | **Live** | Reads Path A artifacts directly |
| LLM agentic copilot | **Live, conditional** | Fully implemented; requires `OPENAI_API_KEY`, disables gracefully otherwise |
| Agentic orchestration runtime (Path B) | **Built, unproven** | 0 completed runs, 0 registered artifacts in its own SQLite ledger as of this writing |
| Experimental/isolated MCP server | **Built, not wired in** | Not imported by `app.py`; separate process only |

No numbers in this document were fabricated for the agentic orchestration layer specifically — where no real
run exists, that is stated explicitly rather than inferred from the (unrelated) core-pipeline numbers.
