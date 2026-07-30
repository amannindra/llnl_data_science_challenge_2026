# Part 2: Lattice CT Explorer

This directory contains the deterministic scientific core, read-only copilot
boundary, and browser-native dashboard for the Part 2 lattice CT analysis.
The workflow verifies registered CT/JSON alignment, measures a reproducible
full 18,468-strut classification results, applies provisional candidate rules, and exposes saved
evidence through FastMCP, Plotly, and Three.js.

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
Git. The verified full-lattice reference artifacts are stored in
`artifacts/sample/`.

## Read-only MCP and agent interfaces

The FastMCP server exposes six read-only tools:

- `get_pipeline_summary`
- `get_strut_details`
- `filter_defect_candidates`
- `compare_defect_groups`
- `get_methodology`
- `prepare_threejs_scene`

Start the stdio server from the repository root:

```bash
PYTHONPATH=part2 python -m defect_cartographer.mcp_server
```

The three-agent copilot consists of a user-facing Analysis Coordinator manager,
Measurement and QA Sub-agent, and Visualization and Reporting Sub-agent. Each
agent is defined in a separate module under `defect_cartographer/agents/`.
Specialists query the same FastMCP tools used by external clients. No API call
is made when `OPENAI_API_KEY` is absent; the copilot reports disabled status
while deterministic MCP tools remain usable.

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

The dashboard provides top navigation for Overview, Strut Explorer, Visual
Analysis, System Design, and Copilot. The header uses the challenge and LLNL
logos, while charts and controls use the supplied poster palette. The Strut
Explorer separates missing, broken, thin, thick, bent/misaligned, and uncertain
records into filterable, paginated tabs and includes healthy and review-state
rows.

## Three.js visualization

The compiled Three.js component loads `artifacts/sample/full_lattice_scene.npz`
through the Python dashboard boundary. It renders all 18,468 nominal struts as
one efficient steel-gray line buffer, a compact CT-derived context mesh, and
thicker classification overlays. Healthy and design-excluded overlays are hidden
by default. Selecting an
analyzed strut returns only its ID to Streamlit, which then displays the saved
deterministic measurements.

The raw TIFF and raw CT voxel arrays are never sent to the browser or to an
agent. The legacy unit-cell builder remains available for historical examples,
but is no longer used by the dashboard.

## Codex integration

The repository-local `lattice-ct-analysis` skill documents the Part 2 workflow.
The global `lattice-ct-evidence` MCP entry launches the six-tool read-only server
with the configured Python environment. Restart Codex CLI only after adding or
changing that global MCP entry.
