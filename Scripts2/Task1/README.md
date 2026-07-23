# Task 1 adversarial verification

These scripts deliberately try to prove that `src2/mcp_server.py`'s
`segment_ct_dataset` tool is wrong. They test only Task 1; Tasks 2 and 3 remain
unimplemented.

## Initial failures found and fixed

1. A 2D array was segmented successfully despite the task defining the input as
   a 3D CT volume.
2. Passing `None` as `output_filepath` raised `AttributeError` instead of
   returning the documented error-status string.
3. Passing the raw input path as the output path could overwrite the original
   CT data.

The implementation now rejects all three cases before a source asset can be
changed.

## Tests

Run from the repository root with the supplied environment:

```bash
conda run -n DSC python Scripts2/Task1/test_01_threshold_boundary_contract.py
conda run -n DSC python Scripts2/Task1/test_02_invalid_input_contract.py
conda run -n DSC python Scripts2/Task1/test_03_mcp_real_volume_and_output_safety.py
```

- `test_01...` tests equality at the threshold, NaN/Inf behavior, `uint8`
  output, suffix handling, and source-array preservation using a synthetic 3D
  volume.
- `test_02...` tests malformed paths, non-3D arrays, archives, object arrays,
  and invalid thresholds. Every case must return `Error:` rather than raise.
- `test_03...` starts the FastMCP server in-memory via `fastmcp.Client`, calls
  the exposed MCP tool on the real `unitcell.npy` volume, compares every output
  voxel with an independent NumPy reference, and verifies overwrite protection.
