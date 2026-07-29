# Spatial Clustering Methods

This ledger covers the deterministic methods used by Anthony's clustering
specialist. These are analysis methods for saved candidate labels, not a new CT
defect classifier.

| Method ID | Method | Status | Reference or definition |
|---|---|---|---|
| `SPATIAL-GRAPH-CC-001` | Shared-junction connected components | Project-defined | Two candidate struts are adjacent only when they share a canonical physical node. |
| `SPATIAL-DBSCAN-001` | DBSCAN with `min_samples=2` | Published method, fixed project parameters | Ester et al. (1996), with radii 2.28, 4.56, and 6.84 mm. At `min_samples=2`, clusters are connected components of the radius-neighbour graph after isolated points are marked noise. |
| `SPATIAL-PERMUTATION-001` | Label-permutation null models | Project-defined application of permutation testing | 10,000 fixed-seed permutations. Opportunity and boundary×orientation-stratified models sample existing design-present struts; uniform-3D is sensitivity-only. |
| `SPATIAL-BOUNDARY-001` | Face/edge/corner/interior midpoint zones | Project-defined | A strut is assigned by the number of coordinate axes within one unit-cell length of a specimen face. Sensitivity widths are 0.5 and 1.5 cells. |
| `SPATIAL-BH-001` | Benjamini-Hochberg false-discovery-rate correction | Published method | Benjamini and Hochberg (1995). |
| `SPATIAL-KNN-ASSOC-001` | All-strut K-nearest-neighbor composition | Project-defined application of KNN | For k=1,3,5,10, find neighbors of each unintentional missing/broken source in the complete graph and summarize present, unintentional missing/broken, and intentional missing physical states. Review-required and uncertain records are reported only as unresolved coverage. Exact distance ties are resolved by edge ID. |
| `SPATIAL-KNN-PERM-001` | All-strut KNN label-permutation nulls | Project-defined application of permutation testing | Keep unintentional missing/broken source locations fixed. Permute the four physical neighborhood labels plus unresolved status across all strut positions, either unrestricted or within boundary-bin × orientation strata. Unresolved status is not tested as a target classification. |

## Units and coordinate frames

- Registered JSON coordinates are CT `XYZ` voxels.
- Nominal graph coordinates are `XYZ` graph units.
- One graph unit is treated as 2.28 mm and one unit cell as 4.56 mm.
- The corresponding 57.7379 µm/voxel value is design-derived and is not an
  independently calibrated CT voxel pitch.

## Interpretation rules

- `missing`, `broken`, and explicitly provided `thin` labels form the main
  candidate population.
- Review-required and low-priority uncertain records are analyzed separately.
- Intentionally removed struts are a design reference, not manufacturing
  defects.
- Uniform random points in the specimen box are not a physical opportunity
  model because defects can only occur on struts.
- KNN describes saved-label composition around unintentional missing/broken
  sources. It neither creates clusters nor confirms physical defects.
- Present struts dominate the complete graph, so raw neighborhood percentages
  must be interpreted relative to the permutation nulls.
- Report `candidate-label concentration`; do not infer manufacturing causation
  from a single specimen.
