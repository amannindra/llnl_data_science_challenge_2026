# Aman MCP server

This directory contains the original CT utilities plus the full lattice defect
workflow. The formal combined entry point is now the Part 2 server, which mounts
these tools under the `raw_ct_` namespace alongside the dashboard evidence tools:

```bash
PYTHONPATH=part2 conda run -n DSC python -m defect_cartographer.mcp_server
```

For backwards compatibility, the original server can still be run directly from
the repository root with the DSC environment:

```bash
PYTHONPATH=. conda run -n DSC python Aman_src/mcp_server.py
```

## Full-lattice defect tools

- `run_full_defect_workflow` — inspect or rebuild the saved full workflow and optionally run anchor similarity.
- `get_full_defect_summary` — return counts and provenance for all 18,468 struts.
- `get_full_strut_details` — return measurements, classification, and human-review metadata for one strut.
- `filter_full_struts` — bounded filtering over classification, occupancy, and gap fraction.
- `get_human_review_anchors` — return explicit human labels and notes.
- `compare_human_anchors_to_full_lattice` — compare human anchors with all 18,468 struts using measured geometry and TIFF evidence.

The full workflow reads these saved inputs:

- `Aman_Scripts/outputs/strut_defect_classification/strut_defect_classification.csv`
- `Aman_Scripts/outputs/mcp_tiff_strut_measurements/strut_measurements.csv`
- `Aman_Scripts/outputs/simple_strut_metrology/strut_metrology.json`
- `data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json`
- `Aman_Scripts/outputs/strut_defect_classification/human_review_labels.csv`

The generated dashboard artifacts are under `part2/artifacts/sample/`. The
MCP workflow does not send raw TIFF voxels in responses, and it does not
automatically propagate human labels to other struts. Similarity results are
review-prioritization evidence only.

The existing `measure_tiff_struts` tool remains available for a raw-TIFF
measurement run. The authoritative dashboard classification is the saved
full-results workflow above, which joins the native-TIFF metrology and
classification artifacts with registered geometry.
