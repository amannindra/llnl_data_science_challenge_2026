# Part 2 read-only agents

The Copilot uses two agents:

- **Analysis Coordinator:** the user-facing manager. It queries bounded
  measurement, comparison, and methodology evidence directly through five
  read-only MCP tools.
- **Visualization and Reporting Sub-agent:** prepares chart guidance, bounded
  Three.js filters, selected-strut views, and reporting explanations.

The coordinator can delegate display and reporting work to the specialist. Both
agents read Aman’s saved deterministic results through the same in-process
FastMCP server used by external MCP clients. The six Part 2 MCP tools are
read-only.

Aman’s deterministic TIFF/JSON/STL registration, metrology, and classification
scripts—not these agents—generate the scientific results. Neither agent
receives raw CT arrays, writes artifacts, validates candidate labels, or changes
classifications. Large Three.js geometry stays outside model context; agents
receive only bounded filters, counts, artifact references, and strut IDs.

## Future clustering specialist

Anthony's clustering agent is an inactive third-agent slot, not a fabricated
implementation. A compatible saved artifact joins by `strut_id` and must include
cluster ID, description, source, and version; optional cluster size, spatial
metrics, and supporting evidence are retained. The existing pipeline-summary
and per-strut MCP responses expose readiness and assignments when the artifact
exists. Until then, both active agents report clustering as unavailable and do
not infer cluster membership.

With no `OPENAI_API_KEY`, `run_copilot` returns a clear disabled response and
makes no network call. The deterministic MCP evidence service remains
available.
