# Task 1 verification results

Executed with the supplied `DSC` environment after fixing the Task 1 tool in
`src2/mcp_server.py`.

| Script | Purpose | Result |
| --- | --- | --- |
| `test_01_threshold_boundary_contract.py` | Attempts to disprove the documented `>=` threshold behavior, 0/1 output, suffix handling, and source preservation. | **7/7 passed** |
| `test_02_invalid_input_contract.py` | Attempts malformed paths, 2D/scalar arrays, NPZ, object data, NaN, and infinity. | **7/7 passed** |
| `test_03_mcp_real_volume_and_output_safety.py` | Starts the FastMCP server in-memory, calls the exposed MCP tool on `unitcell.npy`, compares every voxel with independent NumPy logic, and attempts source overwrite. | **8/8 passed** |

Real-data result at threshold `0.005813093855977058`:

- Input/output shape: `256 × 256 × 256`
- Output dtype: `uint8`
- Foreground voxels: `717,852 / 16,777,216` (4.28%)
- The saved mask exactly equals `(input >= threshold).astype(np.uint8)`.
- The input file's SHA-256 was unchanged after both a normal MCP call and the
  deliberate input-as-output overwrite attempt.

No Task 2 or Task 3 implementation was added or modified.
