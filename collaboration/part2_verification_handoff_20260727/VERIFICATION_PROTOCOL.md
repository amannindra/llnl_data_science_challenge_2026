# Verification Protocol

Use this protocol to verify Phase 2C review cases.

## Review Order

1. Review `review_tables/newly_promoted_14_to_verify.csv`.
2. Review high-priority rows in `review_tables/remaining_review_required_677_to_verify.csv`.
3. Audit-sample `review_tables/low_priority_uncertain_2654_audit_table.csv`.
4. Fill labels in `review_tables/human_verification_template.csv`.

Do not edit the source Phase 2C CSVs. Use the template for human labels.

## Allowed Human CT Labels

Use only these values in `human_ct_label`:

```text
material_absent
material_continuous
material_disconnected
unexpected_material
ambiguous
```

Definitions:

- `material_absent`: the expected strut body is mostly dark/empty.
- `material_continuous`: material appears to form a continuous strut body.
- `material_disconnected`: material exists but has a clear break/gap.
- `unexpected_material`: material appears where design expected removal or where the automatic state did not expect it.
- `ambiguous`: the panel or evidence is not clear enough.

## Allowed Design Labels

Use only these values in `human_design_label_if_relevant`:

```text
designed_present
intentionally_removed
ambiguous
not_reviewed
```

## Allowed Confidence Values

Use only these values in `reviewer_confidence`:

```text
high
medium
low
```

## Recommended Action Values

Use only these values in `recommended_action`:

```text
accept_as_defect_candidate
reject_as_present_like
keep_review_required
needs_raw_tiff_review
needs_regeneration_of_panel
```

## How To Judge A Panel

For a likely missing strut:

- centerline/expected strut path crosses mostly dark material;
- material blobs appear only near nodes/endpoints;
- longest gap is large;
- bridge connectivity is broken.

For a likely disconnected strut:

- there is material on part of the path;
- a visible dark gap interrupts the strut body;
- the bridge does not look continuous.

For a likely present strut:

- bright material follows the expected strut path;
- material is continuous through the body, not only at endpoints.

For ambiguous:

- nearby struts overlap visually;
- the centerline may be slightly off;
- threshold/registration warnings are high;
- the panel cannot separate target strut from neighbors.

## Agent Rules

- An AI agent may sort tables, summarize evidence, and prepare review batches.
- An AI agent must not invent human labels from images.
- Human label fields stay blank until a reviewer fills them.
- The `677` review-required rows stay unresolved unless reviewed.
- The `2,654` low-priority rows stay out of defect counts unless reviewed evidence changes status.

