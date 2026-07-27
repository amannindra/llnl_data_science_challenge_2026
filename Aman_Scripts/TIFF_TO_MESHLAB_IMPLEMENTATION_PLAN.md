# TIFF-to-MeshLab implementation record

## Goal

Convert the original 16-bit raw CT TIFF into a validated, native-resolution,
MeshLab-compatible binary PLY. This work is visualization infrastructure only;
TIFF defect detection remains deferred.

## Approved design

- Stream the exact uint16 histogram and choose global Otsu unless overridden.
- Validate foreground occupancy, spatial bounds, RAM, and free disk first.
- Extract marching cubes in overlapping Z slabs at full voxel resolution.
- Stitch shared slab-plane vertices and convert coordinates from ZYX to XYZ.
- Save an indexed binary PLY plus preflight and final JSON manifests.
- Run at least ten synthetic/adversarial checks before converting the real TIFF.

## Completion log

- Added reusable streaming histogram, Otsu, occupancy profiling, resource
  estimation, slabbed marching cubes, seam stitching, binary PLY writing, and
  bounded-memory PLY validation in `Scripts/Components/tiff_mesh.py`.
- Added the reproducible `Scripts/export_tiff_mesh.py` command and five-slice
  threshold-overlay evidence.
- Added 51 dedicated adversarial checks; all 51 passed. The complete component
  regression suite passed 385/385 checks.
- Real raw TIFF preflight passed at exact global Otsu threshold 40,054. It
  selected 58,649,111/519,119,955 voxels (11.2978%).
- Saved the native-resolution binary PLY with 23,499,938 vertices and 47,042,088
  triangular faces. Its payload was streamed back, and header counts, face
  indices, finite coordinates, bounds, exact byte length, and SHA-256 passed.
- Confirmed the installed `/Applications/MeshLab2025.07.app` declares PLY as a
  supported 3D document type.
- No smoothing, decimation, component filtering, tilt correction, registration,
  or TIFF defect-classification algorithm was implemented.
