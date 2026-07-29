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

## KNN all-strut neighborhood composition

For each unintended missing or broken source strut, KNN finds the nearest
struts from the complete 18,468-strut graph and summarizes their saved labels.

| k | Source | Present | Unintentional missing | Unintentional broken | Intentional missing | Review required | Uncertain |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | unintentional missing | 84.19% | 1.40% | 1.40% | 0.47% | 0.93% | 11.63% |
| 1 | unintentional broken | 69.23% | 0.00% | 7.69% | 0.00% | 7.69% | 15.38% |
| 3 | unintentional missing | 87.44% | 1.24% | 0.62% | 0.47% | 1.71% | 8.53% |
| 3 | unintentional broken | 71.79% | 7.69% | 2.56% | 0.00% | 2.56% | 15.38% |
| 5 | unintentional missing | 69.58% | 18.88% | 0.56% | 0.56% | 2.98% | 7.44% |
| 5 | unintentional broken | 70.77% | 4.62% | 4.62% | 0.00% | 1.54% | 18.46% |
| 10 | unintentional missing | 54.65% | 34.51% | 0.33% | 0.42% | 3.91% | 6.19% |
| 10 | unintentional broken | 71.54% | 5.38% | 3.85% | 0.00% | 3.08% | 16.15% |

Detailed observed-versus-null comparisons, attraction q-values, and avoidance
q-values for every source/target/k combination are in `knn_association.csv`.
Present struts dominate the lattice, so raw percentages must be interpreted
relative to the all-strut and boundary×orientation-stratified null models.

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
- [KNN viewer data](knn_viewer_data.js)
- [3D scene handoff](cluster_scene.json)

