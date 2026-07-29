# Streamlit dashboard

The dashboard provides five views from the saved 60-strut sample:

1. Overview
2. Strut Explorer
3. Visual Analysis
4. System Design
5. Three-agent Copilot

The dashboard uses a scientific-workstation layout with restrained Data Science
Challenge and LLNL identity. One shared palette spans charts and 3D views:
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

Each fixed example contains the canonical 24 nominal struts, registered
junctions, one classified target overlay, a registered CT isosurface with
qualitative CT-intensity texture, camera and lighting presets, cutaway controls,
and the shared evidence side panel. Every canonical node remains visible while
only the selected strut's two true endpoints are enlarged. The other 23 struts
remain nominal context. These layers are visual evidence, not validation or a
calibrated roughness measurement.

The table-only Strut Explorer excludes intact records and separates Missing,
Broken, Thin, and Uncertain into searchable, filterable, paginated tabs with CSV
downloads. Its inspection action opens the selected row in Visual Analysis.

System Design documents the deterministic core, the six-tool MCP boundary, the
Analysis Coordinator manager, and its two specialist sub-agents. All displayed
classifications remain exploratory candidates. The dedicated Copilot page
provides a prepared conversation shell and remains explicit when live API access
or future teammate outputs are unavailable.
