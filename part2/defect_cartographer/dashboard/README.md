# Streamlit dashboard

The dashboard provides five views from the adapter-selected saved run:

1. Overview
2. Strut Explorer
3. Visual Analysis
4. System Design
5. Two-agent Copilot

The dashboard uses a scientific-workstation layout with restrained Data Science
Challenge, UC Merced, UC Riverside, and LLNL identity. One shared palette spans
charts and 3D views: yellow nominal geometry and intact results, red missing,
blue broken, and green uncertain results. Three.js canvases use a black
background for contrast.

The full-lattice Three.js inspector is the dashboard's only 3D lattice view. It
renders all 18,468 registered struts in four efficient screen-space GPU line
buffers on a black canvas: yellow intact/nominal, red missing, blue broken, and
green uncertain. Missing, broken, and uncertain lines are thicker than intact
context. The compact CT-derived context remains optional. Selection by table
row, virtualized class-filtered strut list, numeric strut search, or direct 3D
click focuses the camera and opens dismissible linked CT evidence in a side
panel. Only the selected strut is rendered as a cylinder with a halo. A strut-aligned
longitudinal view and three orthogonal orientations are available, with a
locally enhanced 9-voxel slab as the default and an exact-plane option.
Brightness, contrast, context zoom, five-position slice scrubbing, the material
boundary, endpoint/focus markers, expected centerline, and target-corridor
observed centerline are separate layers. The dashboard reads only a bounded crop
on demand and sends PNG layers, never the complete TIFF or CT volume, to the
browser. Agents and MCP remain raw-CT-free.

Primary navigation is displayed horizontally above the page content. Visual
Analysis owns the full-lattice Three.js inspector, thickness distribution,
spatial distribution, and classification counts. Black is reserved for the
Three.js canvas; controls, tables, cards, and Plotly charts use the light theme.

Legends combine color, text, and symbols; controls have visible keyboard focus
and major 3D views expose loading states.

The Strut Explorer separates Missing, Broken, Uncertain, and Intact into
searchable, filterable, paginated tabs with CSV downloads. Its inspection action
opens the selected row in Visual Analysis.

By default, the loader selects main's `full_strut_classification.csv` and
companion `full_*` artifacts in `part2/artifacts/sample`. Set
`LATTICE_CT_ARTIFACT_DIR` for another saved run or `LATTICE_CT_RESULTS_CSV` for
a specific result file. Source labels remain in `raw_prediction`; thin, thick,
bent/misaligned, not-applicable, and unresolved source states are grouped as
`uncertain` only for this four-class presentation. Aman’s detailed automated
source label remains traceable in `raw_prediction`.

System Design documents the deterministic core, the six-tool MCP boundary, the
Analysis Coordinator manager, and the Visualization and Reporting sub-agent.
The scientific scripts generate classifications; the agents only read and
present saved evidence. All displayed
classifications remain exploratory candidates. The dedicated Copilot page
provides a prepared conversation shell and remains explicit when live API access
or future teammate outputs are unavailable.

Anthony's clustering agent is not connected yet. The adapter recognizes a
versioned, read-only strut assignment contract in `strut_clusters.csv`,
`clustering_results.csv`, or `cluster_assignments.csv`. Required fields are
`strut_id`, `cluster_id`, `cluster_description`, `clustering_source`, and
`clustering_version`; optional cluster size, spatial metric, and supporting
evidence fields are preserved. Existing MCP summary and per-strut responses
report the artifact as unavailable until one of these validated files exists.
