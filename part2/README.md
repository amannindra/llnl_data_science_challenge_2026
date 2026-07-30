# Part 2: Lattice CT Explorer

This directory contains the deterministic scientific core, read-only copilot
boundary, and browser-native dashboard for the Part 2 lattice CT analysis.
The workflow verifies registered CT/JSON alignment, measures a reproducible
60-strut sample, applies provisional candidate rules, and exposes saved
evidence through FastMCP, Plotly, and Three.js.

The classifications are exploratory candidates, not validated defect labels.
The registered JSON specifies where complete nominal struts are expected; it
does not provide defect ground truth.

Baseline rule version `rules-v2-missing-0.10` calls a strut missing only when
material coverage is at most 10% at 97%, 100%, and 103% of the saved Otsu
threshold. Partial support with a substantial internal unsupported run is
broken; unstable or poorly aligned evidence is uncertain. Thin remains an
exploratory lower-tail measurement. Detector and validator outputs can replace
the baseline through `strut_id`, `label`, `label_source`, `label_version`, and
`evidence_focus_zyx`.

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
Git. The verified 60-strut reference artifacts are stored in
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
Analysis, System Design, and Copilot. Its visual system combines a compact
scientific workstation layout with restrained Challenge, UC Merced, UC
Riverside, and LLNL identity.
The Strut
Explorer separates missing, broken, thin, and uncertain candidates into
filterable, paginated tabs and excludes intact rows. It is the table and export
workspace; selected rows open in Visual Analysis for 3D inspection.

## Three.js visualization

The compiled Three.js component loads `artifacts/sample/lattice_scene.npz`
through the Python dashboard boundary. It renders all 18,468 nominal struts as
one efficient blue line buffer, 10,206 registered junction nodes, a compact
CT-derived context mesh, and thicker candidate overlays. Intact overlays are
hidden by default. Users can filter the analyzed 60 by candidate class, search
by strut number, click an overlay, focus the camera, and open the model
full-screen.

Selecting an analyzed strut reads one bounded CT crop on demand and displays
a strut-aligned longitudinal view or one enlarged axial, coronal, or sagittal
view beside the model. The default is a locally enhanced 9-voxel maximum
projection; an exact single-voxel plane remains available. Brightness, contrast,
context zoom, five-position slice scrubbing, material boundaries, endpoint/focus
markers, the expected centerline, and a target-corridor observed material
centerline can be controlled independently. The dashboard caches this derived
evidence in memory; it does not write slice files or send the complete TIFF/CT
volume to the browser. The agent and MCP interfaces remain restricted to saved
evidence and never receive raw CT voxels.

Visual Analysis also exposes four fixed exploratory unit-cell scenes under
`artifacts/sample/unit_cells/`: broken cell 521 / strut 12958, missing cell
646 / strut 16082, thin cell 605 / strut 15040, and intact cell 362 / strut
9000. Each scene renders its 24 canonical struts as solid cylinders. Shared
endpoints are deduplicated directly from those strut segments and shown as
spheres, while the selected target and its two endpoints use the semantic class
color. The other 23 struts remain unclassified context.

Text labels and symbols accompany the semantic colors, keyboard focus is
visible, and unavailable evidence is stated rather than left blank. The raw
TIFF and raw CT voxel arrays are never sent to the browser or an agent.

Rebuild the four derived examples from the repository root with:

```bash
PYTHONPATH=part2 python -m defect_cartographer.core.unit_cell
```

## Codex integration

The repository-local `lattice-ct-analysis` skill documents the Part 2 workflow.
The global `lattice-ct-evidence` MCP entry launches the six-tool read-only server
with the configured Python environment. Restart Codex CLI only after adding or
changing that global MCP entry.
