# Spatial Defect Clustering Report: 210127_Brian_Tran_strut_lattices_0point5dash1_1

## Status

This report describes **candidate-label concentration**. It does not establish
manufacturing causation or convert unresolved records into confirmed defects.

## Inputs and units

- Classification table: `/Users/anthonyching/Desktop/Data Science Challenge/DSC Team Project/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_labels.csv`
- Registered graph: `/Users/anthonyching/Desktop/Data Science Challenge/DSC Team Project/llnl_data_science_challenge_2026/data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json`
- Nominal graph: `/Users/anthonyching/Desktop/Data Science Challenge/DSC Team Project/llnl_data_science_challenge_2026/data/missing_struts/octet_truss_9x9x9.json`
- Registered coordinates: CT XYZ voxels
- Lattice-aligned coordinates: XYZ millimetres
- Design-derived voxel estimate: 57.7379 µm/voxel

The clustering code did not read the TIFF or STL.

## Candidate populations

- Main candidate count: 228
  - Missing: 215
  - Broken/disconnected: 13
  - Thin: 0
- Review-required records analyzed separately: 677
- Low-priority uncertain records analyzed separately: 2654
- Intentionally removed reference struts: 89

## Main clustering measurements

- Shared-junction components: 15
- Largest shared-junction component: 207
- Adjacent candidate pairs: 563
- DBSCAN clusters at 4.56 mm: 4
- Largest DBSCAN cluster: 207

## Random baselines

- Permutations: 10000
- Graph-opportunity largest-component concentration p-value: 9.999000099990002e-05
- Boundary×orientation-stratified p-value: 9.999000099990002e-05

Candidate-label concentration persists after preserving the observed boundary and orientation strata. This is spatial evidence about the saved candidate labels, not proof of a manufacturing mechanism.

The uniform-3D model is a sensitivity comparison only because physical defects
can occur on lattice struts rather than arbitrary empty-space points.

## KNN defect-type association

KNN does not assign clusters. It tests whether one candidate type appears
unusually often in the local neighborhoods of another candidate type.

| k | Direction | Observed target-neighbor % | Stratified-null mean % | Attraction p | Attraction q |
|---:|---|---:|---:|---:|---:|
| 1 | broken → missing | 38.46 | 74.43 | 0.9991 | 1 |
| 1 | missing → broken | 2.79 | 4.38 | 0.951005 | 1 |
| 3 | broken → missing | 48.72 | 73.85 | 0.9996 | 1 |
| 3 | missing → broken | 1.86 | 3.86 | 0.9993 | 1 |
| 5 | broken → missing | 52.31 | 77.82 | 0.9999 | 1 |
| 5 | missing → broken | 2.98 | 3.91 | 0.962304 | 1 |
| 10 | broken → missing | 55.38 | 79.50 | 0.9997 | 1 |
| 10 | missing → broken | 3.49 | 3.95 | 0.828017 | 1 |

Because missing and broken class counts are highly imbalanced, compare observed
neighbor percentages with the null distribution rather than interpreting raw
percentages alone.

## Interpretation guardrails

- Missing, broken, and thin labels form the main candidate population.
- Review-required and low-priority uncertain labels are never added to that count.
- Intentionally removed struts are a separate design reference.
- Boundary and orientation imbalance can create apparent clustering.
- If concentration weakens under the stratified baseline, it should not be
  presented as independent spatial evidence.
- Thin-strut conclusions are unavailable when no explicit thin labels exist.

## Output files

- [Cluster membership](cluster_membership.csv)
- [Cluster summary](cluster_summary.csv)
- [Boundary and orientation summary](boundary_orientation_summary.csv)
- [Random baseline](random_baseline.json)
- [KNN neighbor records](knn_neighbors.csv)
- [KNN association summary](knn_association.csv)
- [KNN random baseline](knn_random_baseline.json)
- [3D scene handoff](cluster_scene.json)

