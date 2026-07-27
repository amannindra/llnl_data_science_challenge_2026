# Copy-Paste Prompt For The Next Verification Agent

Use this prompt with a collaborator's AI agent or a fresh Codex session.

```text
You are working on the LLNL DSC Part 2 CT defect-analysis verification handoff.

Start in the repository root if available. Then read this handoff folder:

collaboration/part2_verification_handoff_20260727/

Read these files first:

1. README_START_HERE.md
2. LABEL_DEFINITIONS.md
3. DEFECT_FINDING_PROCESS.md
4. VERIFICATION_PROTOCOL.md
5. AGENT_INVENTORY.md
6. MANIFEST.json

Important current state:

- Total expected struts: 18,468
- Conservative spot-check-supported report baseline: 214 possible unintended candidates
- Newest Phase 2C automatic triage: 228 possible unintended candidates
- Newly promoted by Phase 2C: 14 rows
- Still review-required: 677 rows
- Low-priority uncertain audit set: 2,654 rows

Rules:

- Do not modify raw data under data/.
- Do not stage, commit, push, reset, clean, or delete files unless explicitly asked.
- Do not count the 677 review-required rows as defects without review.
- Do not count the 2,654 low-priority rows as defects without review.
- Do not call the 228 Phase 2C count spot-check-supported until the 14 newly promoted rows are reviewed.
- Do not let an AI model invent human labels from images.

First verification task:

Review review_tables/newly_promoted_14_to_verify.csv using the matching PNG panels when available in review_panels_phase2c_top120/.

Fill only these blank fields in review_tables/human_verification_template.csv:

- human_ct_label
- human_design_label_if_relevant
- reviewer_confidence
- reviewer_initials
- review_date
- reviewer_notes
- recommended_action

Allowed human_ct_label values:

- material_absent
- material_continuous
- material_disconnected
- unexpected_material
- ambiguous

After the 14 rows are reviewed, summarize:

- how many support material_absent or material_disconnected;
- how many are ambiguous;
- how many contradict the Phase 2C promotion;
- whether the baseline should stay at 214 or can be considered for update to 228.

Stop after that summary unless the user explicitly asks you to continue into the 677-row review queue.
```

