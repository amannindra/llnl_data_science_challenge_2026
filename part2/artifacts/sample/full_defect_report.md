# Full-lattice CT defect classification

The dashboard displays all **18,468** registered expected struts.

## Alignment evidence

The registered JSON geometry is mapped into CT array coordinates using the saved alignment artifact. Nominal centerlines and the native-TIFF measurement joins retain the specimen tilt.

## How the prototype detects defect candidates

This dashboard consumes deterministic saved measurements from the automated native-TIFF metrology pipeline; it does not re-threshold the raw TIFF in the browser.

### Feature definitions

Occupancy is observed axial support. The gap fraction is the longest unsupported centerline gap divided by expected length. Diameter and radial deviation come from valid cross-section measurements.

### Provisional classification rules

Missing indicates low axial support with a large unsupported gap. Broken indicates a disconnected internal gap with more remaining support. Thin and thick are signed radial deviations beyond the effective tolerance. Bent-or-misaligned and uncertain remain review states. Healthy means all available checks were within declared tolerances.

### What “confidence” means here

Displayed confidence is an uncalibrated rule-strength/status score, not a probability.

## Thickness

Thickness statistics are reported only for rows with valid measurements and are not ground truth.

## Limitations and next decision

The labels are automated evidence classifications, not validated manufacturing defects. Independent validation is recommended for ambiguous missing-versus-broken and bent-versus-registration decisions.
