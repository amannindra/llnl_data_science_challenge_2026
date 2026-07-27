# Manual Strut and Junction Integrity Report

## Inputs and calibration

- TIFF: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif`
- Registered graph: `/Users/anthonyching/Desktop/DSC Team Project/llnl_data_science_challenge_2026/data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json`
- CT material threshold: 39986.000
- Estimated voxel size: 57.740 µm/voxel
- Design diameter reference: 6.062 voxels (350 µm)
- Micron values are design-derived estimates, not independently calibrated TIFF metadata.

## Requested structures

- Strut IDs: [6830, 6855, 7072]
- Junction IDs, including automatic endpoints: [3852, 3859, 3867, 3873, 3990, 3999, 4102, 5107]

## Provisional strut states

- `good`: 2
- `likely_discontinuous`: 1

## Provisional junction states

- `good`: 3
- `junction_under_fused`: 5

## Evidence

- [Strut measurements](strut_integrity.csv)
- [Junction measurements](junction_integrity.csv)
- [Run configuration](run_config.json)
- Diagnostic panels are under [`evidence/`](evidence/).

## Interpretation limits

- States are provisional descriptions of CT integrity, not validated defect labels.
- This workflow cannot distinguish intentional removal from a printing defect.
- Thickness depends on segmentation threshold, partial-volume effects, and registration.
- Junction morphology is compared only among selected junctions of equal expected degree.
- Fewer than three equal-degree selected junctions prevents relative malformed-size assessment.
