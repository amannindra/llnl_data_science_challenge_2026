# Task 1 — `segment_ct_dataset` adversarial test suite

Task 1 implements the `segment_ct_dataset(input_filepath, output_filepath, threshold)`
MCP tool in `src/mcp_server.py`. Spec: **voxels `>= threshold` → 1, everything else → 0**,
save as `.npy`, return a status/error string.

These scripts exist to **try to prove that implementation wrong**. Run them with the
`DSC` env:

```bash
cd Scripts/Task1
for t in test_0*.py; do /Users/amannindra/miniconda3/envs/DSC/bin/python "$t"; done
```

| Script | Attack angle | What it tries to break |
| --- | --- | --- |
| `test_01_threshold_semantics.py` | **Semantics** | `>` vs `>=` boundary, exactness vs numpy ground truth on synthetic + real `unitcell.npy`, binary-only output, input not mutated |
| `test_02_io_persistence.py` | **I/O / persistence** | reported path vs real file (the `np.save` `.npy` append), dtype/shape, auto-created dirs, stale data on overwrite, input bytes unchanged |
| `test_03_edge_and_error_cases.py` | **Edge / errors** | missing file, out-of-range thresholds (the `unitcell.npy` value trap), NaN/inf voxels, empty & 2D & int arrays, string/NaN thresholds, non-numeric & pickled arrays |
| `test_04_mcp_end_to_end.py` | **Live MCP server** | tool registration + input schema + real `call_tool` over the FastMCP in-memory `Client`, error propagation through the protocol |

`_harness.py` loads the tool from `src/mcp_server.py` and provides the PASS/FAIL checker.
Every test uses throwaway temp dirs — nothing is written into the repo.

## Result

**34/34 checks pass — the implementation could not be disproven, so no fix was applied.**

Notes surfaced (correct behavior, not bugs):
- On the real `data/unitcell/unitcell.npy` (values ~[-0.003, 0.015]), `threshold=0.5`
  correctly yields an **all-zero** mask — that's the spec working, not a bug; it just
  means 0.5 is the wrong threshold for that raw-intensity volume (normalize first or
  use ~0.002–0.005).
- Output is `uint8` (literal 0/1), compatible with `skeletonize_mask` downstream.
- `np.save` appends `.npy`; the tool reports the **actual** saved path.
