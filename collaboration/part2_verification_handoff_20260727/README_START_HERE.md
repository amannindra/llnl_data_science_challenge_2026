# Part 2 Verification Handoff - Start Here

This folder is a Git-trackable transfer packet for collaborators who will verify
the current Part 2 CT defect-analysis results.

It does not contain raw CT TIFF, STL, or source JSON data. It contains the
current notes, methods, agent configs, review tables, 120 existing Phase 2C
review panels, a local graph viewer, and a conservative final-report baseline.

## Current Status

```text
total expected struts = 18,468
current conservative report baseline = 214 possible unintended candidates
newest Phase 2C automatic triage = 228 possible unintended candidates
newly promoted by Phase 2C = 14 rows
still review-required = 677 rows
low-priority uncertain audit set = 2,654 rows
```

Important:

```text
The 214 count is the current spot-check-supported report baseline.
The 228 count is newer automatic triage and needs verification before replacing 214.
```

## What To Read First

Read these in order:

```text
README_START_HERE.md
LABEL_DEFINITIONS.md
DEFECT_FINDING_PROCESS.md
VERIFICATION_PROTOCOL.md
AGENT_INVENTORY.md
NEXT_AGENT_PROMPT.md
```

Then inspect:

```text
review_tables/newly_promoted_14_to_verify.csv
review_tables/remaining_review_required_677_to_verify.csv
review_tables/low_priority_uncertain_2654_audit_table.csv
review_tables/human_verification_template.csv
review_panels_phase2c_top120/
viewer/index.html
```

## Folder Map

```text
notes_snapshot/                  copied project notes through Phase 2C
method_and_config/               AGENTS rules, assumptions, methods ledger, config
agent_assets/                    Codex skills and agent TOML files
review_tables/                   Phase 2C labels and verification CSVs
review_panels_phase2c_top120/    existing 120 PNG review panels
viewer/                          local graph-level defect viewer
final_report_baseline/           conservative 214-candidate report package
```

## Verification Priority

1. Review `newly_promoted_14_to_verify.csv` first.
2. Then review the highest-priority rows in `remaining_review_required_677_to_verify.csv`.
3. Only audit-sample `low_priority_uncertain_2654_audit_table.csv`; do not review all 2,654 first.
4. Fill human labels only in `human_verification_template.csv`.

Do not count rows as final defects just because the automated system flagged
them. Final verified labels need human review or a documented validated
verification rule.

## No Git Push Was Done

This packet was created for Git transfer, but it has not been staged,
committed, or pushed.

