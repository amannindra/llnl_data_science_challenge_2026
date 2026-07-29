# Checkpoint 2 agent boundary

The copilot uses a manager pattern with one user-facing Analysis Coordinator
and two specialist sub-agents:

- **Analysis Coordinator (manager):** delegates user questions and combines evidence.
- **Measurement and QA Sub-agent:** queries saved measurements, compares
  groups, explains rule precedence, and checks claims for scientific overreach.
- **Visualization and Reporting Sub-agent:** explains saved reports and prepares
  bounded Three.js scene filters, spatial bounds, and selected-strut
  specifications.

Both specialists access evidence through OpenAI Agents SDK function tools that
invoke the same in-process FastMCP server exposed to external clients. The
agents never receive raw CT voxel data and cannot write artifacts or change
candidate labels. The deterministic Python core remains the source of every
measurement and classification.

The coordinator uses the specialists as tools, so the dashboard will receive
one consistent response. With no `OPENAI_API_KEY`, `run_copilot` returns a
clear disabled response and makes no network call. MCP queries continue to
work in that mode.

Large Three.js geometry stays outside model context. The dashboard loads the
compact scene artifact directly; agents receive only filters, counts, bounds,
artifact references, and selected strut IDs.
