# Reusable Scripts Components

`Aman_Scripts/Components` contains the side-effect-free implementation shared by the
project's analysis commands and adversarial tests. Importing these modules does
not create directories, write artifacts, launch a UI, or load a full TIFF.

## Coordinate convention

- Geometry, JSON junctions, STL vertices, and transforms use `(x, y, z)`.
- NumPy and TIFF volumes are indexed `[z, y, x]`.
- Convert explicitly with `xyz_to_zyx` or `zyx_to_xyz`.
- `read_tiff_slice` accepts only a `ZYX` series; multidimensional series must be
  handled explicitly with `read_tiff`.

## Modules

- `paths.py` — safe repository, data, Scripts, and output paths.
- `asset_io.py` — Git-LFS-aware JSON/NPY/TIFF/STL inspection and lazy readers.
- `coordinates.py` — XYZ/ZYX conversion and homogeneous transforms.
- `lattice_graph.py` — validated graph parsing, tolerant damaged-JSON recovery,
  deterministic coincident-node welding, provenance, and connectivity.
- `segmentation.py` — pure thresholding, mask normalization, and validation.
- `legacy_occupancy.py` — preserved historical centerline heuristic. It is
  unvalidated, over-called real defects, and must not be treated as ground truth.
- `reporting.py` — strict deterministic JSON/JSONL/CSV, atomic writes, SHA-256,
  and file manifests.
- `testing.py` — named check collection, minimum-count enforcement, structured
  summaries, and safe module loading.
- `tiff_mesh.py` — streaming raw-TIFF profiling, slabbed isosurface extraction,
  seam stitching, and binary PLY validation for MeshLab.

## Validation

Run the complete fail-fast suite in the prepared environment:

```bash
conda run -n DSC python Aman_Scripts/ComponentTests/run_all.py
```

Persistent results are written to:

- `Aman_Scripts/outputs/component_validation/component_test_summary.json`
- `Aman_Scripts/outputs/component_validation/component_test_summary.md`

The suite includes synthetic edge cases, import/CLI compatibility, both restored
TIFF stacks, the registered graph, and a restored STL. Each public component has
at least ten independent checks. The aggregate summaries are normalized so two
identical runs are byte-for-byte reproducible.

Run the original MCP Task regressions separately:

```bash
for test_file in Aman_Scripts/Task1/test_*.py Aman_Scripts/Task2/test_*.py Aman_Scripts/Task3/test_*.py; do
  conda run -n DSC python "$test_file" || exit 1
done
```

## Dependencies

The prepared `DSC` conda environment is the reference environment. Core package
requirements are listed in `Aman_Scripts/requirements.txt`. Napari is optional and
needed only by `view_tif_napari.py`; it is deliberately not required by the
headless validation suite.

## Scope boundary

No new TIFF defect detector is implemented here. The future registration,
strut-ROI, feature, and five-state classification design is documented in
`Aman_Scripts/TIFF_DEFECT_DETECTION_DEFERRED_PLAN.md` and remains deferred.
