# Task 2 verification results

Executed with the supplied `DSC` environment against only the Task 2 tool in
`src2/mcp_server.py`.

| Script | Attempt to disprove | Result |
| --- | --- | --- |
| `test_01_axis_slice_pixel_contract.py` | Wrong axis, wrong index, transposed output, incorrect pixel scaling, non-PNG output, or source mutation. | **16/16 passed** |
| `test_02_invalid_input_contract.py` | Missing files, 2D/complex/archive data, nonfinite volume, invalid axes/indices, and unsafe output paths. | **13/13 passed** |
| `test_03_mcp_real_volume.py` | Broken MCP registration/call, wrong real-volume plane, incorrect output image, or source overwrite. | **9/9 passed** |

## Failure found and corrected during verification

The first real-data run showed a maximum two-level grayscale mismatch. The
underlying plane was correct, but Matplotlib's implicit 256-color grayscale
lookup table introduced small rounding differences. Task 2 now explicitly
normalizes to an 8-bit RGBA grayscale array before saving. The final real MCP
test has a maximum pixel error of **0** against the independent reference.

Real-data MCP result:

- Input: `data/unitcell/unitcell.npy`, shape `256 × 256 × 256`
- Selection: axis `0`, index `128`
- Output: an opaque `256 × 256 × 4` PNG
- Shared display range: `[-0.003128750016912818, 0.015257691964507103]`
- Raw source SHA-256 unchanged after normal rendering and a deliberate
  overwrite attempt.

No Task 1 behavior was changed and no Task 3 implementation was added.
