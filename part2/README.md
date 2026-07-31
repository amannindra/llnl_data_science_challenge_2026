# Part 2: Lattice CT Explorer

This directory contains the main-branch deterministic scientific core, read-only
agent/MCP boundary, and your current browser-native dashboard for Part 2. The
dashboard reads the saved full 18,468-strut agent result when it is available,
while retaining a compatible 60-strut baseline fallback. It preserves source
labels in `raw_prediction` and applies conservative UI aliases only at the
presentation boundary. The current dashboard groups all results other than
missing, broken, and healthy/intact under uncertain. Aman's recorded review
labels override automated labels by strut ID when the full-run review CSV is
available; both labels remain visible for traceability.

The classifications are exploratory candidates, not validated defect labels.
The registered JSON specifies where complete nominal struts are expected; it
does not provide defect ground truth.

## Environment and core commands

Create the declared environment once, then run commands from the repository
root:

```bash
conda env create -f part2/environment.yml
conda activate defect-cartographer

PYTHONPATH=part2 python -m defect_cartographer.core.pipeline all
PYTHONPATH=part2 python -m pytest part2/tests -q
```

Generated experimental runs belong in `artifacts/runs/` and are ignored by
Git. The full-lattice reference artifacts are stored in `artifacts/sample/`.

The dashboard artifact adapter resolves its run directory in this order:

1. an explicit `load_dashboard_artifacts(path)` call;
2. `LATTICE_CT_ARTIFACT_DIR`;
3. `part2/artifacts/sample`.

It prefers `full_strut_classification.csv` and the companion `full_*` JSON,
Markdown, and scene artifacts, then falls back to the original baseline names.
Set `LATTICE_CT_RESULTS_CSV` to select one specific result CSV.

## Read-only MCP and agent interfaces

The formal FastMCP entry point combines the dashboard evidence tools with the
existing Aman CT tools. It exposes these native read-only dashboard tools:

- `get_pipeline_summary`
- `get_strut_details`
- `filter_defect_candidates`
- `compare_defect_groups`
- `get_methodology`
- `prepare_threejs_scene`
- `get_strut_ct_evidence`

The Aman CT tools are mounted under the `raw_ct_` namespace in the same server,
so registration, TIFF, skeleton, metrology, and full-workflow tools remain
available without maintaining a second MCP entry point. The selected-strut CT
tool returns a bounded PNG with Otsu material overlays and never returns raw
voxel arrays.

Start the stdio server from the repository root:

```bash
PYTHONPATH=part2 python -m defect_cartographer.mcp_server
```

The two-agent copilot consists of a user-facing Analysis Coordinator and a
Visualization and Reporting Sub-agent. The coordinator queries bounded
measurement and methodology evidence directly, and delegates display/reporting
tasks to the specialist. Both use the same FastMCP boundary available to
external clients. No API call is made when `OPENAI_API_KEY` is absent; the
copilot reports disabled status while deterministic MCP tools remain usable.

Anthony's future clustering specialist has an inactive, validated CSV contract
joined by `strut_id`. It is not counted as an active agent until its versioned
artifact and implementation are supplied.

Checkpoint 2 is read-only:

- agents receive saved CSV/JSON/Markdown evidence, not raw CT voxels;
- results are capped and validated by schemas;
- agents cannot write artifacts or modify candidate labels;
- no sampled percentage is presented as full-part prevalence;
- uncalibrated rule strength is not presented as probability.

## Dashboard

Launch the five-view Streamlit dashboard from the repository root:

```bash
PYTHONPATH=part2 streamlit run part2/app.py
```

To review another saved run without changing agent code:

```bash
export LATTICE_CT_ARTIFACT_DIR="$PWD/part2/artifacts/sample"
# Optional when the checkout does not have Git LFS materialized:
export LATTICE_CT_RAW_PATH="/absolute/path/to/registered_scan.tif"
PYTHONPATH=part2 streamlit run part2/app.py
```

The dashboard provides top navigation for Overview, Strut Explorer, Visual
Analysis, System Design, and Copilot. The header uses the challenge, UC, and LLNL
logos, while charts and controls use the supplied poster palette. The Strut
Explorer presents the current four UI classes; source states such as
`bent_or_misaligned`, `thick`, and `not_applicable` remain available in
`raw_prediction` and are conservatively grouped as uncertain in the current
presentation.

## Three.js visualization

The compiled Three.js component loads the adapter-selected compact scene through
the Python dashboard boundary. It is the only full-lattice 3D view and renders
all 18,468 registered struts in four GPU screen-space line buffers on a black
canvas: yellow intact/nominal, red missing, blue broken, and green uncertain.
The three non-intact buffers are wider for visibility. Only the selected strut
becomes a cylinder with a selection halo. A virtualized class-filtered list,
numeric search, and direct 3D selection return only a strut ID to Streamlit,
which then loads bounded CT evidence lazily when the raw TIFF is available.

The raw TIFF and raw CT voxel arrays are never sent to the browser or to an
agent.

## Codex integration

The repository-local `lattice-ct-analysis` skill documents the Part 2 workflow.
The global `lattice-ct-evidence` MCP entry launches this unified server
with the configured Python environment. Restart Codex CLI only after adding or
changing that global MCP entry.
