# Task 2 — `visualize_slice` adversarial test suite

Task 2 implements the `visualize_slice(input_filepath, output_filepath, slice_index, axis=0)`
MCP tool in `src/mcp_server.py`. Spec: **load a 3D CT `.npy`, take the 2D slice at
`slice_index` along `axis`, and save it as an image** (e.g. `.png`); return a
status/error string.

These scripts exist to **try to prove that implementation wrong**. Run them with the
`DSC` env:

```bash
cd Scripts/Task2
for t in test_0*.py; do /Users/amannindra/miniconda3/envs/DSC/bin/python "$t"; done
```

| Script | Attack angle | What it tries to break |
| --- | --- | --- |
| `test_01_slice_semantics.py` | **Semantics** | wrong slice/axis, wrong default axis, flipped/transposed image, broken negative indexing — verified against a numpy ground truth by reading the saved PNG back to luminance (a **non-cubic** volume makes every axis a different shape) |
| `test_02_io_persistence.py` | **I/O / persistence** | reported path vs real file (the missing-extension `.png` append), other formats (`.jpg`/`.tif`/`.bmp`), auto-created dirs, stale image on overwrite, input `.npy` bytes unchanged, round-trip resolution |
| `test_03_edge_and_mcp.py` | **Edge / errors + live MCP** | missing/empty paths, non-3D arrays, out-of-range axis/index, bad types, non-numeric & pickled arrays, NaN/inf/constant slices — **plus** a real FastMCP `Client`: registration, 4-param schema, live `call_tool`, error propagation |

`_harness.py` loads the tool from `src/mcp_server.py`, provides the PASS/FAIL checker,
and a `read_luminance()` helper (via Pillow) so content checks don't depend on how the
tool encoded the image. Every test uses throwaway temp dirs — nothing is written into
the repo.

## Result

**45/45 checks pass (9 + 11 + 25).** The suite found **one real bug**, which was fixed:

- **Bug (found by `test_02`, `.tif` case):** the first implementation saved via
  `matplotlib.pyplot.imsave`, which derives the image format from the extension and
  passed `'TIF'` to Pillow. Pillow only registers TIFF under `TIFF`/`.tiff`, so `.tif`
  output raised `KeyError: 'TIF'` and returned an `Error:` string instead of an image.
  This matters here because the challenge stores CT data as `.tif` and Task 6 asks for
  masks saved as `.tif`.
- **Fix:** render the grayscale slice to an 8-bit array in NumPy and save it with
  `PIL.Image.fromarray(...).save(path)`, letting Pillow infer the format from the
  filename. Every extension (`.png`, `.tif`, `.jpg`, `.bmp`, ...) now works, and the
  matplotlib dependency was dropped from this path.

Notes surfaced (correct behavior, not bugs):
- Grayscale autoscaling is **per-slice** (finite min→black, max→white), so the raw
  `unitcell.npy` values (~[-0.003, 0.015]) still render with full contrast.
- `+inf`→white, `-inf`→black, `NaN`→black; a constant slice renders without a
  zero-range divide.
- `slice_index` accepts int-valued strings/floats and numpy-style negative indices;
  `axis` is strictly `0`/`1`/`2`.
- Non-3D arrays are rejected (a 2D slice of a 2D array isn't an image), matching the
  "3D CT dataset" contract.
