# Compact STL-to-TIFF strut metrology

## Result scope

`0.5.stl` is the specimen CAD used for printing. Its deliberate omissions are
reported as non-applicable design absences; only additional TIFF mismatches are
candidate errors. Missing-versus-broken subtype is not assigned.

## Registration

- Independent rigid correction: 0.078459 degrees, 1.011370 voxels.
- Held-out median absolute local ISO-50 offset: 1.015674995008835 voxels.
- Conservative registration uncertainty used by decisions: 1.1864282941080195 voxels.

## Counts

- Processed: 10
- Error candidates: 0
- Clearly inside tolerance: 2
- Review-required: 8
- Non-applicable design/skin members: 0

## Evidence panels

Max projections can visually hide a gap; the axial support/radius plots below
each projection are the actual decision evidence.

![strut_00004](panels_diagnostic_10/strut_00004.png)

![strut_02300](panels_diagnostic_10/strut_02300.png)

![strut_04278](panels_diagnostic_10/strut_04278.png)

![strut_06266](panels_diagnostic_10/strut_06266.png)

![strut_08251](panels_diagnostic_10/strut_08251.png)

![strut_10235](panels_diagnostic_10/strut_10235.png)

![strut_12212](panels_diagnostic_10/strut_12212.png)

![strut_18467](panels_diagnostic_10/strut_18467.png)

![strut_14189](panels_diagnostic_10/strut_14189.png)

![strut_16173](panels_diagnostic_10/strut_16173.png)

## Limitations

- Synthetic tests establish numerical behavior, not real defect accuracy.
- Registration uncertainty includes CT noise and manufacturing surface variation.
- Candidate errors require scientific/manual review; no subtype is claimed.
- The segmented TIFF is not used as ground truth.
