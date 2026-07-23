# Task 3 — `skeletonize` adversarial test suite

Task 3 implements the `skeletonize(input_filepath, output_filepath)` MCP tool in
`src/mcp_server.py`. Unlike Tasks 1 & 2, this one is an **API wrapper**: it must
expose the *existing* `skeletonize_mask()` from `src/skeletonization.py`, not
reimplement skeletonization. Spec: load a 3D mask `.npy`, thin it to a 1-voxel
centerline via `skimage.morphology.skeletonize`, save `.npy`, return a status/error string.

These 10 scripts exist to **try to prove that implementation wrong**. Run them with the
`DSC` env:

```bash
cd Scripts/Task3
for t in test_*.py; do /Users/amannindra/miniconda3/envs/DSC/bin/python "$t"; done
```

| # | Script | What it tries to break |
| --- | --- | --- |
| 1 | `test_01_wraps_skeletonize_mask.py` | that it's a **real wrapper** — spies on `skeletonize_mask` to prove it's actually called (once, right args) and delegates, not reimplemented |
| 2 | `test_02_correctness_vs_skimage.py` | output must equal `skimage.skeletonize(mask>0)` exactly, on synthetic data + a real thresholded `unitcell.npy` crop |
| 3 | `test_03_return_contract.py` | MCP tools must return a **string** — `skeletonize_mask` returns an ndarray/None, so the wrapper must convert both |
| 4 | `test_04_paths_missing_bad.py` | missing/empty/directory inputs → `Error:` strings, no raise, no bogus output |
| 5 | `test_05_output_npy_and_dirs.py` | **path honesty** (`np.save` `.npy` append) + auto-creating missing output dirs (`skeletonize_mask` doesn't) |
| 6 | `test_06_no_stdout_pollution.py` | `skeletonize_mask`'s `print()`s must not leak to stdout (would corrupt the stdio JSON-RPC stream) |
| 7 | `test_07_skeleton_properties.py` | skeleton ⊆ mask, thinner than mask, boolean dtype, shape preserved |
| 8 | `test_08_edge_masks.py` | degenerate-but-valid masks (empty/solid/single-voxel/float/bool) — match skimage, never crash |
| 9 | `test_09_bad_arrays.py` | hostile payloads (string/object/corrupt/1D/4D arrays) → `Error:`; NaN/inf float mask still succeeds |
| 10 | `test_10_mcp_end_to_end.py` | live FastMCP `Client`: registration, 2-param schema, real `call_tool`, error propagation, full segment→skeletonize pipeline |

`_harness.py` loads the tool from `src/mcp_server.py` and provides the PASS/FAIL checker
plus a `cross_mask()` helper. Every test uses throwaway temp dirs — nothing is written
into the repo.

## Result

**49/49 checks pass.** The suite found **one real bug** (fixed) and **one bad test
assumption** (corrected):

- **Bug (found by `test_05`):** the wrapper first used `os.path.splitext` to decide
  whether to append `.npy`. But `np.save` appends `.npy` unless the path already ends
  in `.npy` — so `np.save("skel.dat")` writes `skel.dat.npy`. The tool reported
  `skel.dat` (a nonexistent path). **Fix:** switch to `endswith(".npy")`, matching
  numpy's real rule (and `segment_ct_dataset`), so the reported path is always the file
  on disk.
- **Not a bug (corrected in `test_08`):** a solid cube skeletonizes to **0 voxels** under
  skimage's 3D thinning (verified). The wrapper faithfully returns that, so the original
  "solid cube → non-empty" assertion was wrong; the test now asserts an exact match to
  skimage instead.

Design notes (why the wrapper is more than one line):
- **Returns a string** — converts `skeletonize_mask`'s ndarray/None into a status/error string.
- **Suppresses stdout** — wraps the call in `contextlib.redirect_stdout` so the library's
  `print()`s can't corrupt the MCP stdio protocol.
- **Creates the output directory** and reports the true `.npy` save path.
- **Validates paths up front** so a missing file (which `skeletonize_mask` only prints
  about, returning `None`) surfaces as a proper `Error:` string.
- Everything else — the actual thinning — is delegated to the existing API, unchanged.
