# Streamlit dashboard

The dashboard provides five views from the saved 60-strut sample:

1. Overview
2. Strut Explorer
3. Visual Analysis
4. System Design
5. Three-agent Copilot

The dashboard uses a scientific-workstation layout with restrained Data Science
Challenge, UC Merced, UC Riverside, and LLNL identity. One shared palette spans
charts and 3D views:
blue nominal geometry, green intact,
magenta missing, yellow broken, purple thin, and orange uncertain candidates.

Plotly provides browser-native 3D registered centerlines. The full-lattice
Three.js inspector renders all 18,468 nominal struts in one blue buffer, 10,206
registered junction nodes, compact CT-derived context, and candidate overlays
from a compressed scene artifact. Intact analyzed overlays start hidden.
Selection by table row, candidate class, strut number, or 3D overlay focuses the
camera and opens dismissible linked CT evidence in a side panel. A strut-aligned
longitudinal view and three orthogonal orientations are available, with a
locally enhanced 9-voxel slab as the default and an exact-plane option.
Brightness, contrast, context zoom, five-position slice scrubbing, the material
boundary, endpoint/focus markers, expected centerline, and target-corridor
observed centerline are separate layers. The dashboard reads only a bounded crop
on demand and sends PNG layers, never the complete TIFF or CT volume, to the
browser. Agents and MCP remain raw-CT-free.

Primary navigation is displayed horizontally above the page content. Visual
Analysis owns the Plotly CT-backed view, the full-lattice Three.js inspector,
and four fixed Three.js unit-cell examples:

- broken candidate: unit cell 521, strut 12958;
- missing candidate: unit cell 646, strut 16082.
- thin candidate: unit cell 605, strut 15040;
- intact candidate: unit cell 362, strut 9000.

Each fixed example uses 24 solid cylinders for the canonical unit-cell struts.
Shared endpoints are deduplicated directly from those cylinders and rendered as
spheres, ensuring that nodes and struts use the same geometry. The selected
target and its two endpoints use the semantic class color; the other 23 struts
remain unclassified blue context. Linked CT slices remain supporting evidence,
not ground-truth validation.

Legends combine color, text, and symbols; controls have visible keyboard focus
and major 3D views expose loading states.

The table-only Strut Explorer excludes intact records and separates Missing,
Broken, Thin, and Uncertain into searchable, filterable, paginated tabs with CSV
downloads. Its inspection action opens the selected row in Visual Analysis.

System Design documents the deterministic core, the six-tool MCP boundary, the
Analysis Coordinator manager, and its two specialist sub-agents. All displayed
classifications remain exploratory candidates. The dedicated Copilot page
provides a prepared conversation shell and remains explicit when live API access
or future teammate outputs are unavailable.
