# Collaboration Handoff Automated Audit

Results: **43 passed, 19 warnings, 2 failures**.

This report validates packet integrity and internal consistency. It does not replace human CT review or recreate the absent production source code.

## Findings

### PASS — manifest.file_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/MANIFEST.json`)

Manifest file counts reconcile.

Severity: `info`.

### PASS — manifest.coverage (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/MANIFEST.json`)

Every handoff file is represented exactly once in the manifest.

Severity: `info`.

### PASS — manifest.nonself_integrity (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/MANIFEST.json`)

All non-manifest file hashes and sizes match the handoff manifest.

Severity: `info`.

### WARN — manifest.self_hash (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/MANIFEST.json`)

MANIFEST.json records a stale hash/size for itself; a directly embedded self-hash cannot be stable after serialization.

Severity: `medium`.

### PASS — packet.raw_data_exclusion

The packet excludes raw TIFF/STL/NumPy/source-data artifacts.

Severity: `info`.

### PASS — structured.parseability

Every JSON, CSV, YAML, and TOML artifact parses successfully.

Severity: `info`.

### FAIL — source.production_code_available

The handoff does not contain the production/test Python implementation it documents, and those directories are absent from this worktree.

Severity: `critical`.

### WARN — documentation.portability

Some copied runbooks contain collaborator-specific absolute paths and are not directly runnable on this Mac.

Severity: `medium`.

### PASS — phase2c.labels.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_labels.csv`)

labels row count: 18468 (expected 18468).

Severity: `info`.

### PASS — phase2c.labels.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_labels.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.candidates.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_auto_supported_unintended_candidates.csv`)

candidates row count: 228 (expected 228).

Severity: `info`.

### PASS — phase2c.candidates.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_auto_supported_unintended_candidates.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.remaining.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_remaining_review_queue.csv`)

remaining row count: 677 (expected 677).

Severity: `info`.

### PASS — phase2c.remaining.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_remaining_review_queue.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.new.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/newly_promoted_14_to_verify.csv`)

new row count: 14 (expected 14).

Severity: `info`.

### PASS — phase2c.new.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/newly_promoted_14_to_verify.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.remaining_verify.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/remaining_review_required_677_to_verify.csv`)

remaining_verify row count: 677 (expected 677).

Severity: `info`.

### PASS — phase2c.remaining_verify.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/remaining_review_required_677_to_verify.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.low.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/low_priority_uncertain_2654_audit_table.csv`)

low row count: 2654 (expected 2654).

Severity: `info`.

### PASS — phase2c.low.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/low_priority_uncertain_2654_audit_table.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.template.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/human_verification_template.csv`)

template row count: 3345 (expected 3345).

Severity: `info`.

### PASS — phase2c.template.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/human_verification_template.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2c.verification_template_union

The human template is the disjoint union of 14 promoted, 677 remaining, and 2,654 low-priority rows.

Severity: `info`.

### PASS — phase2c.queue_set_relationships

Candidate/review/audit queues are exact subsets of the all-edge table, and the two 677-row exports agree.

Severity: `info`.

### PASS — phase2c.label_distribution

The seven Phase 2C label categories reconcile exactly to 18,468 struts.

Severity: `info`.

### PASS — phase2c.summary_reconciliation (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_summary.json`)

Phase 2C JSON summary matches the exported tables.

Severity: `info`.

### PASS — phase2c.edge_id_integrity

Every canonical edge ID is well formed and agrees with node_u/node_v.

Severity: `info`.

### PASS — phase2c.required_numeric_domains

Core classifier metrics are finite and fraction-valued metrics stay in [0, 1].

Severity: `info`.

### PASS — phase2c.human_template_blank (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/human_verification_template.csv`)

Human-verification fields remain blank; no labels were invented by the transfer process.

Severity: `info`.

### PASS — phase2b4.candidates.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/auto_supported_unintended_candidates.csv`)

candidates row count: 214 (expected 214).

Severity: `info`.

### PASS — phase2b4.candidates.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/auto_supported_unintended_candidates.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2b4.manual.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/manual_review_queue.csv`)

manual row count: 920 (expected 920).

Severity: `info`.

### PASS — phase2b4.manual.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/manual_review_queue.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2b4.human.row_count (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv`)

human row count: 40 (expected 40).

Severity: `info`.

### PASS — phase2b4.human.unique_edges (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv`)

Edge IDs are unique at the expected one-row-per-strut grain.

Severity: `info`.

### PASS — phase2b4.baseline_reconciliation (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/final_ct_defect_summary.json`)

The conservative 214-candidate baseline, 920 blocked rows, 40 human labels, and 1.158761% fraction reconcile.

Severity: `info`.

### PASS — phase2c.promotion_delta

Phase 2C's 228 candidates are exactly the 214 baseline candidates plus the 14 newly promoted rows.

Severity: `info`.

### WARN — provenance.assumption_registry (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/method_and_config/scientific_assumptions.yaml`)

The all-edge table cites assumption IDs that are absent from the formal scientific-assumptions registry.

Severity: `medium`.

### WARN — provenance.method_registry (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md`)

Method IDs used in all-edge provenance are not defined or cited by the methods ledger.

Severity: `medium`.

### WARN — provenance.reference_id_normalization

Equivalent literature/source references use multiple identifiers, weakening automated lineage joins.

Severity: `low`.

### WARN — provenance.config_snapshot_stale (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/method_and_config/part2.yaml`)

The copied part2.yaml still encodes an unverified identity/unknown STL mapping even though later artifacts say the human-anchor gate selected perm021_signmmm; it is not a ready-to-rerun Phase 2C config.

Severity: `high`.

### WARN — schema.boolean_casing

Boolean columns mix True/False and true/false conventions; consumers must parse values explicitly because bool('false') is true in Python.

Severity: `medium`.

### WARN — schema.literal_nan

Several numeric fields serialize undefined measurements as literal nan strings; use null/blank plus an explicit validity/status field for interoperable schemas.

Severity: `medium`.

### WARN — schema.phase2c_changed_semantics

phase2c_changed_from_phase2b4 is true for 1,009 lexical/status changes, not just the 14 newly promoted candidates; its name is easy to misread as a promotion flag.

Severity: `low`.

### WARN — schema.viewer_numeric_types (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/viewer/viewer_data.json`)

Viewer score and evidence_count values are strings, which permits accidental lexical sorting/comparison.

Severity: `low`.

### WARN — provenance.source_artifact_lineage

Two included copies match their recorded source hashes, but the canonical graph and original Phase 2B.4 summary/all-label inputs are absent, so complete source-to-output lineage cannot be rehashed.

Severity: `high`.

### WARN — science.paper_external_consistency (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/2246722.pdf`)

The Phase 2C candidate taxonomy does not reproduce the paper's manually reviewed defect distribution: it flags far more missing-like edges and far fewer disconnected edges. Treat it as triage, not validated paper-equivalent classification.

Severity: `high`.

### WARN — science.human_review_sampling

The human evidence covers only ranks 1-40 of the 214 auto-supported candidates, with no random sampling and no present-like controls; it supports top-ranked precision directionally but cannot establish full-list precision, recall, or calibration.

Severity: `high`.

### WARN — science.phase2c_promotions_unreviewed

All 14 Phase 2C promotions remain unreviewed, so 228 must not replace the spot-check-supported 214 baseline yet.

Severity: `high`.

### WARN — science.spatial_candidate_profile

Possible unintended candidates are disproportionately boundary/near-boundary cases, increasing the risk of skin, crop, and registration artifacts.

Severity: `medium`.

### FAIL — coverage.auto_supported_without_ct_support (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_tables/phase2c_labels.csv`)

Three auto-supported possible-missing edges have both endpoints beyond the evidence pipeline's x=767 support, no-local-material endpoint statuses, and all-zero area profiles. They must be coverage-blocked until the x-clipping/axis issue is fixed.

Severity: `critical`.

### WARN — coverage.review_panels_zero_edge_signal (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/review_panels_phase2c_top120`)

Forty of the 120 review panels have all-zero edge-aligned slabs/traces because their requested edge lies beyond the evidence pipeline's x support; nearby context in a projection must not be mistaken for valid edge evidence.

Severity: `high`.

### WARN — coverage.promotions_cross_support_boundary

One newly promoted edge crosses the evidence x-support boundary and needs an explicit endpoint-coverage caution before review.

Severity: `high`.

### WARN — coverage.panel_metric_units

All 120 values named mean_delta_mm are actually the dimensionless quantity labeled CT anomaly score in the review index; the field name has misleading physical units.

Severity: `medium`.

### PASS — viewer.embedded_external_match (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/viewer/index.html`)

The self-contained HTML embeds the same data as viewer_data.json.

Severity: `info`.

### PASS — viewer.edge_counts (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/viewer/viewer_data.json`)

Viewer edge IDs are unique and all class counts reconcile to 18,468.

Severity: `info`.

### PASS — viewer.edge_coverage

Viewer edge IDs exactly cover the Phase 2C all-edge label table.

Severity: `info`.

### PASS — viewer.geometry_and_style

All viewer endpoints are finite/in-bounds and class styles match the legend.

Severity: `info`.

### PASS — viewer.static_ui_features (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/viewer/index.html`)

The HTML includes search, reset, rotate, zoom, click-selection, legend, and resize handlers.

Severity: `info`.

### PASS — images.decode_all

All 121 PNG artifacts decode completely and were inspected sequentially.

Severity: `info`.

### PASS — images.exact_duplicates

No exact duplicate PNGs were found.

Severity: `info`.

### PASS — images.panel_dimensions

All 120 review panels share the expected 2790×1655 layout.

Severity: `info`.

### PASS — images.panel_index_mapping

Ranks 001–120, edge IDs, filenames, summary rows, and review index agree exactly.

Severity: `info`.

### WARN — images.baseline_chart_scale (`/Users/amannindra/Projects/llnl_data_science_challenge_2026/collaboration/part2_verification_handoff_20260727/final_report_baseline/figures/automated_review_label_counts.png`)

The baseline bar chart uses one linear scale even though present-like exceeds the smallest headline defect class by more than 1,000×; small categories are visually unreadable.

Severity: `medium`.
