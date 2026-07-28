# Streamlit dashboard

The dashboard provides five views from the saved 60-strut sample:

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
defect-candidate overlays from a compressed scene artifact. Intact analyzed
overlays start hidden. It returns selected strut IDs to Streamlit without
sending the raw TIFF through the browser or agent boundary.

Primary navigation is displayed horizontally above the page content. Visual
Analysis owns the Plotly CT-backed view, the full-lattice Three.js inspector,
and exactly two fixed Three.js unit-cell examples:

- broken candidate: unit cell 521, strut 12958;
- missing candidate: unit cell 646, strut 16082.

Each fixed example contains 24 displayed struts, a derived CT surface, and a
three-plane contour PNG with segmentation, expected-strut, and deterministic
skeleton overlays. These layers are visual evidence, not validation.

The Strut Explorer excludes intact records and separates Missing, Broken, Thin,
and Uncertain into searchable, filterable, paginated tabs with CSV downloads.

System Design documents the deterministic core, the six-tool MCP boundary, the
Analysis Coordinator manager, and its two specialist sub-agents. All displayed
classifications remain exploratory candidates.
