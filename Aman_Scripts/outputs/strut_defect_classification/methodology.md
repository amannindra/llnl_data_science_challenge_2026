# Automated strut defect classification

The classifier joins each expected STL/JSON strut to the existing raw-TIFF metrology record by `strut_id`. It preserves non-applicable CAD omissions and invalid measurements as exclusions or review cases. A confirmed subtype requires a declared metrology tolerance failure; ambiguous centerline offsets are reported as `bent_or_misaligned` review cases, not confirmed bends.

The 35% axial-support boundary is a screening policy for separating a mostly absent strut from a broken one. It must be checked against human anchor labels before being treated as a validated scientific rule.
