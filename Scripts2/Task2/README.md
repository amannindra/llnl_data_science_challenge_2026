# Task 2 adversarial verification

This directory tests only the Task 2 `visualize_slice` tool in
`src2/mcp_server.py`. Task 1 is not changed, and Task 3 remains unimplemented.

```bash
conda run -n DSC python Scripts2/Task2/test_01_axis_slice_pixel_contract.py
conda run -n DSC python Scripts2/Task2/test_02_invalid_input_contract.py
conda run -n DSC python Scripts2/Task2/test_03_mcp_real_volume.py
```

1. The first script attempts to disprove the axis/index contract by checking
   all three axes against exact rendered grayscale values from a known 3D
   synthetic volume.
2. The second attempts malformed files, non-3D/complex data, invalid selectors,
   nonfinite values, and unsafe output paths; every one must return `Error:`
   rather than raise.
3. The third starts the registered server in-memory through `fastmcp.Client`,
   renders the real 256×256 central unit-cell plane, validates every PNG pixel
   against an independent normalization calculation, and checks source safety.
