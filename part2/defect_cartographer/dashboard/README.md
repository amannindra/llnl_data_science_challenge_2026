# Streamlit dashboard

The dashboard provides five views from the saved full-lattice classification:

1. Overview
2. Strut Explorer
3. Visual Analysis
4. System Design
5. Three-agent Copilot

The dashboard uses the Data Science Challenge and LLNL logos plus the challenge
poster palette for charts and controls. Semantic 3D defect colors remain
separate from that chart palette.

The Streamlit process never opens the raw TIFF. Plotly provides browser-native
3D registered centerlines. The full-lattice Three.js inspector renders all
18,468 nominal struts in one steel-gray buffer, compact CT-derived context, and
classification overlays from a compressed scene artifact. Healthy and
design-excluded overlays start hidden. It returns selected strut IDs to
Streamlit without sending the raw TIFF through the browser or agent boundary.

Visual Analysis owns the Plotly CT-backed view and the full-lattice Three.js
inspector. Any strut in the saved classification can be selected for inspection;
there are no hardcoded broken or missing examples in the page.

The Strut Explorer uses the full CSV and separates Missing, Broken, Thin, Thick,
Bent or misaligned, and Uncertain into searchable, filterable, paginated tabs
with CSV downloads.

System Design documents the deterministic core, the six-tool MCP boundary, the
Analysis Coordinator manager, and its two specialist sub-agents. All displayed
classifications remain exploratory candidates.
