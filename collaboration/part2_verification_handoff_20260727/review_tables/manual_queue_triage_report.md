# Phase 2C Manual-Queue Triage

## Status

```text
PHASE2C_TRIAGE_COMPLETE_REVIEW_STILL_REQUIRED_FOR_REMAINING_UNRESOLVED_ROWS
```

## Simple Meaning

Phase 2B.4 checked every expected strut and left `920` rows blocked for manual
review. Phase 2C does not pretend those rows were unscanned. It asks a narrower
question:

```text
Can any blocked rows be safely promoted or demoted using the existing CT features?
```

Only very clear cases are promoted. Mixed or unstable rows stay review-required.

## Input

```text
outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv
```

## Main Counts

```json
{
  "total_edge_count": 18468,
  "by_phase2c_label": {
    "phase2c_auto_supported_designed_removed_absent_or_disconnected": 89,
    "phase2c_auto_supported_possible_unintended_missing": 215,
    "phase2c_auto_supported_possible_unintended_disconnected": 13,
    "phase2c_still_review_required": 672,
    "phase2c_low_priority_uncertain_not_defect_like": 2654,
    "phase2c_still_review_required_design_intent_conflict": 5,
    "phase2c_auto_supported_present_like": 14820
  },
  "by_phase2c_status": {
    "auto_supported": 14909,
    "auto_supported_spotcheck_recommended": 228,
    "still_review_required": 677,
    "low_priority_not_reported_as_defect": 2654
  },
  "by_phase2c_triage_bucket": {
    "not_blocked_or_other": 14903,
    "uncertain_registration_unstable": 1457,
    "possible_missing_boundary": 418,
    "possible_missing_instability_or_evidence_shortfall": 2,
    "possible_disconnected_instability_or_evidence_shortfall": 58,
    "uncertain_mixed_evidence": 555,
    "uncertain_threshold_sensitive": 1070,
    "design_removed_uncertain": 1,
    "design_removed_present_like_conflict": 4
  },
  "phase2c_auto_supported_possible_unintended_missing_count": 215,
  "phase2c_auto_supported_possible_unintended_disconnected_count": 13,
  "phase2c_auto_supported_possible_unintended_combined_count": 228,
  "phase2c_auto_supported_possible_unintended_combined_fraction": 0.012345679012345678,
  "phase2c_newly_promoted_from_blocked_count": 14,
  "phase2c_remaining_review_required_count": 677,
  "phase2c_low_priority_not_reported_as_defect_count": 2654,
  "publication_status": "PHASE2C_TRIAGE_COMPLETE_REVIEW_STILL_REQUIRED_FOR_REMAINING_UNRESOLVED_ROWS"
}
```

The Phase 2C auto-supported possible-unintended fraction is:

```text
228 / 18468 = 1.23%
```

## Interpretation

- `phase2c_auto_supported_possible_unintended_missing` means the design did not mark the strut removed and CT evidence is strongly empty.
- `phase2c_auto_supported_possible_unintended_disconnected` means the design did not mark the strut removed and CT evidence shows a strong gap or broken bridge.
- `phase2c_still_review_required` means the row remains too mixed or unstable for automatic reporting.
- `phase2c_low_priority_uncertain_not_defect_like` means weak evidence, not counted as a defect.

## Outputs

```text
outputs/part2/phase2c/20260727_132248/phase2c_labels.csv
outputs/part2/phase2c/20260727_132248/phase2c_summary.json
outputs/part2/phase2c/20260727_132248/phase2c_auto_supported_unintended_candidates.csv
outputs/part2/phase2c/20260727_132248/phase2c_remaining_review_queue.csv
outputs/part2/phase2c/20260727_132248/review_packet
```

## Caveat

Phase 2C is still an automated triage layer. It can reduce review load, but it
does not turn every ambiguous CT region into ground truth.
