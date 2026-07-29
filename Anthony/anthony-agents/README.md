# Anthony Spatial Defect Clustering Agents

This folder contains:

- `defect_workflow_coordinator`: sequences teammate-owned classification,
  CT/STL validation, clustering, visualization, and reporting stages.
- `spatial_clustering_agent`: analyzes saved classifications and graph geometry.
- A separate FastMCP server with four input-preserving clustering tools.
- A deterministic command-line runner and tests.

The clustering implementation never opens TIFF or STL data. It reads the saved
Phase 2C table and the registered/nominal JSON graphs.

## Start Codex

Start Codex with `Anthony` as the project directory:

```bash
cd "/Users/anthonyching/Desktop/Data Science Challenge/DSC Team Project/llnl_data_science_challenge_2026/Anthony"
codex
```

Restart Codex after changing `.codex/config.toml` or an agent TOML.

Example prompt:

```text
Use defect_workflow_coordinator to run the spatial clustering stage for the
current specimen. Use run ID first_clustering_run and keep uncertain records
separate from the main missing/broken/thin count.
```

## Deterministic command-line run

From `Anthony/`:

```bash
python3 anthony-agents/run_analysis.py \
  --config anthony-agents/configs/current_specimen.json \
  --run-id first_clustering_run
```

Outputs are written to:

```text
anthony-scripts/analysis/spatial_clustering/<run_id>/
```

An existing artifact is returned unchanged only when regenerated content is
identical. Otherwise the runner refuses to overwrite it and requires a new run
ID.

## MCP tools

- `analyze_spatial_clusters(config_path, run_id)`
- `compare_random_baseline(config_path, run_id)`
- `analyze_knn_association(config_path, run_id)`
- `summarize_boundary_distribution(config_path, run_id)`
- `prepare_cluster_scene(config_path, run_id, offset=0, limit=1000)`

These tools are input-preserving but write-capable. They can create new,
versioned files only under the configured Anthony output root.

## Current population policy

- Main: 215 possible missing + 13 possible disconnected = 228 candidates.
- Separate: 677 review-required.
- Separate: 2,654 low-priority uncertain.
- Separate reference: 89 intentionally removed.
- Thin is unavailable until an explicit thin label is supplied.

Human spot-check labels are attached as evidence. The automated Phase 2C class
is retained for the primary all-candidate analysis, and an adjudicated class is
also stored for later sensitivity analyses.

## KNN all-strut neighborhood composition

KNN is used as a neighborhood-composition test, not as another cluster
assignment. For every unintentional missing or broken source and
`k = 1, 3, 5, 10`, the analysis searches the complete 18,468-strut graph. Each
neighbor is categorized as:

- present;
- unintentional missing;
- unintentional broken;
- intentional missing.

Review-required and uncertain records remain eligible to be spatial neighbors,
but they are recorded only as unresolved coverage. They are not treated as
physical neighbor classifications, and they are never silently changed to
present.

Observed compositions are compared with 10,000 fixed-seed all-strut label
permutations. One null shuffles the four physical labels plus unresolved status
across all strut positions; the stricter null shuffles only within boundary-bin
× orientation strata. Source locations remain fixed. The output files are `knn_neighbors.csv`,
`knn_association.csv`, `knn_random_baseline.json`, and `knn_viewer_data.js`.

The interactive Phase 2C cluster explorer includes a `KNN target-neighbor
share` mode. Choose `k = 1, 3, 5, 10`, select any of the four physical target categories,
and click an unintentional missing or broken strut to display its all-strut
neighbors and distances.

## Tests

From `Anthony/`:

```bash
python3 -m unittest discover -s anthony-agents/tests -v
```
