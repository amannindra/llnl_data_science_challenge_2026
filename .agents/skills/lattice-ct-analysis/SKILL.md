---
name: lattice-ct-analysis
description: Run, inspect, explain, or validate the repository's Part 2 registered lattice CT workflow. Use for the 60-strut analysis, candidate classifications, thickness or spatial plots, Plotly or Three.js 3D views, Streamlit dashboard, Part 2 FastMCP tools, or coordinator/sub-agent architecture.
---

# Lattice CT Analysis

Work from the repository root on `ulices-test`. Preserve existing Git changes and
treat the registered TIFF and saved evidence as read-only unless the user explicitly
requests regeneration.

## Select the operation

- Inspect saved evidence: read `part2/artifacts/sample/` through the service or MCP.
- Run tests: activate the environment declared in `part2/environment.yml` and
  set `PYTHONPATH=part2`.
- Open the dashboard: run Streamlit against `part2/app.py`.
- Inspect registered geometry: use the Plotly and Three.js views under Visual
  Analysis.
- Use agents: route factual claims through the six read-only MCP tools.

## Commands

```bash
conda run -n defect-cartographer env PYTHONPATH=part2 \
  python -m pytest part2/tests -q

conda run -n defect-cartographer env PYTHONPATH=part2 \
  streamlit run part2/app.py

conda run -n defect-cartographer env PYTHONPATH=part2 \
  python -m defect_cartographer.mcp_server
```

## Evidence boundaries

- Use the registered mapping `JSON (x,y,z) -> CT array (z,y,x)` and retain tilt.
- Treat missing, broken, thin, uncertain, and intact as deterministic candidate
  classifications from the fixed 60-strut run.
- Explain uncertain as unstable alignment or threshold evidence.
- Do not report accuracy, precision, recall, or full-part prevalence without labeled
  ground truth.
- Treat rule strength as a heuristic, not a probability.
- Do not give agents raw CT arrays or artifact write access.

## Agent and MCP topology

The Analysis Coordinator is the manager. It delegates measurement questions to the
Measurement and QA Sub-agent and display/report questions to the Visualization and
Reporting Sub-agent. Both specialists obtain facts from the Part 2 FastMCP boundary;
they do not calculate or revise classifications.
