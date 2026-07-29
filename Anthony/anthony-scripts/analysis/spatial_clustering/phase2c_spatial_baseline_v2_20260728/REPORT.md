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
- [3D scene handoff](cluster_scene.json)

