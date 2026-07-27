# Label Definitions

This file defines the terms used in the Phase 2C review tables.

## Main Physical Idea

The design tells us what should exist. The CT scan tells us what was actually
printed and scanned.

```text
possible unintended defect = design says present, CT looks missing or broken
designed removed = design intentionally removed it, so it is not an unintended defect
```

## Current Labels

`phase2c_auto_supported_present_like`

- Count: `14,820`
- Meaning: CT evidence looks like a continuous present strut.
- Action: no immediate human review needed.

`phase2c_auto_supported_designed_removed_absent_or_disconnected`

- Count: `89`
- Meaning: design says this strut was intentionally removed, and CT absence or breakage is consistent with that design intent.
- Action: do not count as unintended defects.

`phase2c_auto_supported_possible_unintended_missing`

- Count: `215`
- Meaning: design expected the strut, but CT evidence along the strut body is strongly empty.
- Action: candidate unintended missing strut; verify before stronger publication claims.

`phase2c_auto_supported_possible_unintended_disconnected`

- Count: `13`
- Meaning: design expected the strut, but CT evidence shows a strong gap or broken bridge.
- Action: candidate unintended disconnected strut; verify before stronger publication claims.

`newly_promoted_14`

- Count: `14`
- Meaning: these rows were blocked in Phase 2B.4 but promoted by Phase 2C because the sampled strut body was essentially empty or clearly broken under bounded instability.
- Action: review first. These rows are why Phase 2C gives `228` instead of the conservative `214`.

`phase2c_still_review_required`

- Count: `672`
- Meaning: evidence is still too mixed, threshold-sensitive, registration-sensitive, or incomplete for automatic support.
- Action: review if a stronger final result is needed.

`phase2c_still_review_required_design_intent_conflict`

- Count: `5`
- Meaning: design intent and CT evidence conflict or remain unclear.
- Action: review carefully; do not count automatically.

`still_review_required_677`

- Count: `677`
- Meaning: combined still-review-required set: `672` normal review rows plus `5` design-intent conflict rows.
- Action: second review priority after the 14 newly promoted rows.

`phase2c_low_priority_uncertain_not_defect_like`

- Count: `2,654`
- Meaning: automatic evidence is uncertain but weak. These rows are not counted as defects.
- Action: audit-sample later; do not treat as missing/disconnected unless review finds strong evidence.

## Evidence Fields

`ct_missing_material_anomaly_score`

- Higher means the strut looks more abnormal compared with similar struts.

`phase2b3_missing_evidence_count`

- Number of independent missing-material signals that agree.

`occupied_axial_fraction`

- Fraction of strut-length bins that contain material.
- Low value means much of the expected strut path is empty.

`longest_low_area_gap_fraction`

- Longest empty or low-material stretch as a fraction of the strut body.
- High value means a long missing/broken region.

`area_mean_voxels2`

- Mean segmented material area in the sampled cross sections.
- Very low value means little material along the strut body.

`bridge_connected_26`

- Whether the segmented material forms a 26-neighbor connected path through the strut body.
- `False` supports disconnected or missing evidence.

`threshold_stability_occupied_fraction_range`

- How much the occupied-fraction result changes when the threshold is perturbed.

`local_registration_stability_voxels`

- How much the local registration/centerline estimate changes in voxels.

