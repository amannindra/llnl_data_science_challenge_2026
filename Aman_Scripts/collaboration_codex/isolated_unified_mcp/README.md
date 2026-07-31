# Isolated Aman Agentic MCP

This directory contains the experimental Aman-only unified MCP entrypoint. It
does not replace the current server and does not import the external defect
agent repository.

## Start the server

From the experimental checkout root:

```bash
PYTHONPATH=part2:. conda run -n DSC python \
  Aman_Scripts/collaboration_codex/isolated_unified_mcp/mcp_server.py
```

The entrypoint exposes dashboard/query tools, mounts the Aman CT tools once
under `raw_ct_*`, and exposes the `agentic_*` run lifecycle tools.

## Run lifecycle

Create a run with a TIFF and registered JSON configuration:

```json
{
  "tiff_filepath": "/absolute/path/to/scan.tif",
  "registered_json_filepath": "/absolute/path/to/registered.json",
  "voxel_pitch_um": 58.1,
  "expected_radius_voxels": 3.65
}
```

The persistent SQLite state and generated artifacts live under:

```text
part2/artifacts/runs/agentic/
```

The deterministic Aman stages validate inputs, record registration provenance,
segment the TIFF, skeletonize the mask, measure struts, reconcile the expected
18,468 identities, write QA metrics, and produce a short report. Full TIFF
execution is intentionally not run during import or server startup.

Candidate labels remain evidence classifications rather than validated ground
truth.
