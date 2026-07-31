# Collaborator handoff verification

Packet: `collaboration/part2_verification_handoff_20260727` (created 2026-07-27T23:33:33.167018+00:00)

- Checks: 81 total, 78 PASS, 3 FAIL, 0 SKIP
- Integrity gate: **FAIL**

## Results by category

| Category | Total | Pass | Fail | Skip |
| --- | ---: | ---: | ---: | ---: |
| arithmetic | 20 | 20 | 0 | 0 |
| cross_check | 6 | 6 | 0 | 0 |
| integrity | 10 | 8 | 2 | 0 |
| linkage | 26 | 25 | 1 | 0 |
| row_counts | 15 | 15 | 0 | 0 |
| viewer | 4 | 4 | 0 | 0 |

## Checks

| ID | Category | Status | Check | Detail |
| --- | --- | --- | --- | --- |
| INT-01 | integrity | PASS | MANIFEST.json exposes a files[] array | 176 entries |
| INT-02 | integrity | PASS | manifest paths are unique | 176 unique paths |
| INT-03 | integrity | PASS | manifest paths stay inside the packet | no absolute or '..' paths |
| INT-04 | integrity | PASS | file_count equals len(files) | file_count=176, len(files)=176 |
| INT-05 | integrity | PASS | file_count equals the recursive on-disk file count | file_count=176, on disk=176 |
| INT-06 | integrity | PASS | every manifest file exists on disk | 176/176 present |
| INT-07 | integrity | FAIL | every file's size matches the manifest | 1 mismatch(es): ['MANIFEST.json'] |
| INT-08 | integrity | FAIL | every file's SHA-256 matches the manifest | 1 mismatch(es): ['MANIFEST.json'] |
| INT-09 | integrity | PASS | every payload file (excluding the manifest's self-entry) verifies | 175 payload files verified |
| INT-10 | integrity | PASS | no unlisted files exist on disk | no orphan files |
| ARI-01 | arithmetic | PASS | headline combined == missing + disconnected | 214.0 vs 202.0 + 12.0 = 214.0 |
| ARI-02 | arithmetic | PASS | important_counts baseline == headline combined | important_counts=214, headline=214.0 |
| ARI-03 | arithmetic | PASS | phase2c candidates == baseline candidates + newly promoted rows | 228 vs 214 + 14 |
| ARI-04 | arithmetic | PASS | draft_percent == 100 * combined / total | csv=1.158761, recomputed=1.158761100281568 |
| ARI-05 | arithmetic | PASS | human defect_like + ambiguous + contradictions == reviewed_panels | 40.0 vs reviewed_panels=40.0 |
| ARI-06 | arithmetic | PASS | human_spotcheck_label_counts.csv reproduces the headline spot-check | tally={'ambiguous': 4, 'material_absent': 29, 'material_disconnected': 7}, sum=40, defect_like=36 |
| ARI-07 | arithmetic | PASS | phase2c label breakdown sums to total_edge_count | sum=18468, total_edge_count=18468 |
| ARI-08 | arithmetic | PASS | phase2c status breakdown sums to total_edge_count | sum=18468, total_edge_count=18468 |
| ARI-09 | arithmetic | PASS | phase2c triage bucket breakdown sums to total_edge_count | sum=18468, total_edge_count=18468 |
| ARI-10 | arithmetic | PASS | phase2c combined == phase2c missing + disconnected | 228 vs 215 + 13 |
| ARI-11 | arithmetic | PASS | phase2c combined == important_counts phase2c candidates | summary=228, manifest=228 |
| ARI-12 | arithmetic | PASS | phase2c combined fraction == combined / total_edge_count | json=0.012345679012345678, recomputed=0.012345679012345678 |
| ARI-13 | arithmetic | PASS | human_verification_template_rows == sum of its three sub-queue counts | 3345 vs 14 + 677 + 2654 = 3345 |
| ARI-14 | arithmetic | PASS | baseline label partition sums to total_expected_struts | 214 + 89 + 14820 + 920 + 2425 = 18468 vs 18468 |
| ARI-15 | arithmetic | PASS | phase2c re-triages exactly the baseline's blocked rows | blocked=920 vs promoted+review_required+low_priority_delta=14+677+229=920 |
| ARI-16 | arithmetic | PASS | final_ct_defect_summary percent agrees with headline_numbers.csv | json=1.158761100281568, csv=1.158761 |
| ARI-17 | arithmetic | PASS | viewer class_counts sum to the viewer edge_count | sum=18468, edge_count=18468 |
| ARI-18 | arithmetic | PASS | phase2c_labels.csv phase2c_label tally reproduces phase2c_summary.json | recounted tally matches |
| ARI-19 | arithmetic | PASS | phase2c_labels.csv phase2c_status tally reproduces phase2c_summary.json | recounted tally matches |
| ARI-20 | arithmetic | PASS | phase2c_labels.csv phase2c_triage_bucket tally reproduces phase2c_summary.json | recounted tally matches |
| ROW-01 | row_counts | PASS | review_tables/newly_promoted_14_to_verify.csv has 14 data rows | actual=14, claimed=14 (source: MANIFEST.important_counts.newly_promoted_phase2c_rows_to_verify_first) |
| ROW-02 | row_counts | PASS | review_tables/remaining_review_required_677_to_verify.csv has 677 data rows | actual=677, claimed=677 (source: MANIFEST.important_counts.remaining_review_required_rows) |
| ROW-03 | row_counts | PASS | review_tables/low_priority_uncertain_2654_audit_table.csv has 2654 data rows | actual=2654, claimed=2654 (source: MANIFEST.important_counts.low_priority_uncertain_audit_rows) |
| ROW-04 | row_counts | PASS | review_tables/human_verification_template.csv has 3345 data rows | actual=3345, claimed=3345 (source: MANIFEST.important_counts.human_verification_template_rows) |
| ROW-05 | row_counts | PASS | review_tables/phase2c_auto_supported_unintended_candidates.csv has 228 data rows | actual=228, claimed=228 (source: MANIFEST.important_counts.phase2c_auto_supported_possible_unintended_candidates) |
| ROW-06 | row_counts | PASS | review_tables/phase2c_labels.csv has 18468 data rows | actual=18468, claimed=18468 (source: phase2c_summary.json.summary.total_edge_count) |
| ROW-07 | row_counts | PASS | review_tables/phase2c_remaining_review_queue.csv has 677 data rows | actual=677, claimed=677 (source: phase2c_summary.json.summary.phase2c_remaining_review_required_count) |
| ROW-08 | row_counts | PASS | final_report_baseline/tables/auto_supported_unintended_candidates.csv has 214 data rows | actual=214, claimed=214 (source: headline_numbers.csv.auto_supported_possible_unintended_combined) |
| ROW-09 | row_counts | PASS | final_report_baseline/tables/manual_review_queue.csv has 920 data rows | actual=920, claimed=920 (source: headline_numbers.csv.blocked_manual_review_rows) |
| ROW-10 | row_counts | PASS | final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv has 40 data rows | actual=40, claimed=40 (source: headline_numbers.csv.reviewed_panels) |
| ROW-11 | row_counts | PASS | review_panels_phase2c_top120/ct_edge_panel_summary.csv has 120 data rows | actual=120, claimed=120 (source: ct_edge_panel_summary.json.edge_count) |
| ROW-12 | row_counts | PASS | review_tables/review_panel_index.csv has 120 data rows | actual=120, claimed=120 (source: ct_edge_panel_summary.json.edge_count (same 120-panel review packet)) |
| ROW-13 | row_counts | PASS | review_tables/newly_promoted_14_to_verify.csv has 14 data rows | actual=14, claimed=14 (source: filename) |
| ROW-14 | row_counts | PASS | review_tables/remaining_review_required_677_to_verify.csv has 677 data rows | actual=677, claimed=677 (source: filename) |
| ROW-15 | row_counts | PASS | review_tables/low_priority_uncertain_2654_audit_table.csv has 2654 data rows | actual=2654, claimed=2654 (source: filename) |
| LNK-01 | linkage | PASS | every panel referenced by the summary exists on disk | 120 referenced |
| LNK-02 | linkage | PASS | every panel PNG on disk appears in the summary | 120 on disk |
| LNK-03 | linkage | PASS | every panel filename follows rank_NNN_E_<u>_<v>_ct_panel.png | 120 filenames parsed |
| LNK-04 | linkage | PASS | panel ranks are contiguous 1..120 | {"duplicates": [], "missing": [], "unexpected": []} |
| LNK-05 | linkage | PASS | panel filename rank/edge match the summary row | 120 rows agree |
| LNK-06 | linkage | PASS | panel filename node pair matches the row's edge_id | 120 rows agree |
| LNK-07a | linkage | PASS | review_panel_index.csv ranks are contiguous 1..120 | {"duplicates": [], "missing": [], "unexpected": []} |
| LNK-07b | linkage | PASS | review_panel_index.csv edge_id values parse to a node pair | 120 edge IDs parsed |
| LNK-07 | linkage | PASS | review_panel_index.csv panels resolve to files in this packet | 120/120 derived panel filenames present |
| LNK-08a | linkage | PASS | spotcheck_panel_index.csv ranks are contiguous 1..80 | {"duplicates": [], "missing": [], "unexpected": []} |
| LNK-08b | linkage | PASS | spotcheck_panel_index.csv edge_id values parse to a node pair | 80 edge IDs parsed |
| LNK-08 | linkage | FAIL | spotcheck_panel_index.csv panels resolve to files in this packet | 0/80 derived panel filenames present |
| LNK-10 | linkage | PASS | newly_promoted_14_to_verify.csv edge IDs are all present in phase2c_labels.csv | 14 unique edge IDs resolve against the label table |
| LNK-11 | linkage | PASS | remaining_review_required_677_to_verify.csv edge IDs are all present in phase2c_labels.csv | 677 unique edge IDs resolve against the label table |
| LNK-12 | linkage | PASS | low_priority_uncertain_2654_audit_table.csv edge IDs are all present in phase2c_labels.csv | 2654 unique edge IDs resolve against the label table |
| LNK-13 | linkage | PASS | human_verification_template.csv edge IDs are all present in phase2c_labels.csv | 3345 unique edge IDs resolve against the label table |
| LNK-14 | linkage | PASS | phase2c_auto_supported_unintended_candidates.csv edge IDs are all present in phase2c_labels.csv | 228 unique edge IDs resolve against the label table |
| LNK-15 | linkage | PASS | phase2c_remaining_review_queue.csv edge IDs are all present in phase2c_labels.csv | 677 unique edge IDs resolve against the label table |
| LNK-16 | linkage | PASS | review_panel_index.csv edge IDs are all present in phase2c_labels.csv | 120 unique edge IDs resolve against the label table |
| LNK-17 | linkage | PASS | ct_edge_panel_summary.csv edge IDs are all present in phase2c_labels.csv | 120 unique edge IDs resolve against the label table |
| LNK-18 | linkage | PASS | spotcheck_panel_index.csv edge IDs are all present in phase2c_labels.csv | 80 unique edge IDs resolve against the label table |
| LNK-19 | linkage | PASS | auto_supported_unintended_candidates.csv edge IDs are all present in phase2c_labels.csv | 214 unique edge IDs resolve against the label table |
| LNK-20 | linkage | PASS | manual_review_queue.csv edge IDs are all present in phase2c_labels.csv | 920 unique edge IDs resolve against the label table |
| LNK-21 | linkage | PASS | human_spotcheck_labels_rank001_040.csv edge IDs are all present in phase2c_labels.csv | 40 unique edge IDs resolve against the label table |
| LNK-22 | linkage | PASS | human_verification_template.csv queue composition matches its three sources | template={'newly_promoted_14_first_priority': 14, 'remaining_review_required_677_second_priority': 677, 'low_priority_uncertain_2654_audit_only': 2654}, sources={'newly_promoted_14_first_priority': 14, 'remaining_review_required_677_second_priority': 677, 'low_priority_uncertain_2654_audit_only': 2654} |
| LNK-23 | linkage | PASS | human spot-check labels cover the top-ranked spotcheck panel rows | 40 labelled rows align with spotcheck_panel_index ranks 1..40 |
| XVL-01 | cross_check | PASS | registered lattice JSON parses to 10,206 junction records | junctions=10206, source struts=18468, unit cells=729 |
| XVL-02 | cross_check | PASS | coincident-node welding yields 3,430 physical nodes | welded nodes=3430 |
| XVL-03 | cross_check | PASS | welded strut count reproduces the packet's total_expected_struts | recomputed=18468 from data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json, packet claims 18468 |
| XVL-04 | cross_check | PASS | packet node IDs fall inside the source junction ID range | 3430 distinct node IDs in [0, 10205] |
| XVL-05 | cross_check | PASS | packet edge set equals this repo's welded strut set | packet=18468, repo=18468, packet-only=0, repo-only=0, unmapped=0 |
| XVL-06 | cross_check | PASS | packet source_strut_id values are real source strut IDs | 18468 distinct IDs inside [0, 18467] |
| VWR-01 | viewer | PASS | the manifest's viewer_entrypoint exists | viewer/index.html |
| VWR-02 | viewer | PASS | every path the viewer references exists | 0 referenced local path(s) |
| VWR-03 | viewer | PASS | the viewer is self-contained (no fetch/XHR/external hosts) | no network calls; data arrives via inline <script type=application/json> block(s) ['viewer-data'] |
| VWR-04 | viewer | PASS | the viewer's embedded payload parses and matches its edge_count | inline edges=18468, metadata.edge_count=18468, class tally matches run_manifest.json |

## Findings

- **info** (INT-05): MANIFEST.json counts itself: it is one of the files[] entries, so file_count includes the manifest file
- **blocking** (INT-07): 1 mismatch(es): ['MANIFEST.json']
- **blocking** (INT-08): 1 mismatch(es): ['MANIFEST.json']
- **warning** (INT-08): MANIFEST.json contains a self-entry whose size/SHA-256 describe an earlier revision of itself. A manifest cannot contain its own final hash, so this entry is unsatisfiable by construction and should be omitted or recorded in a detached sidecar.
- **info** (LNK-01): ct_edge_panel_summary.csv output_path values point at the collaborator's own run directory (outputs/part2/phase2c/...); linkage is matched on the filename component only
- **warning** (LNK-08): 0/80 derived panel filenames present
- **info** (LNK-08): spotcheck_panel_index.csv indexes 80 panels from a run whose PNGs are not shipped in this packet (80 absent). Only the 120 Phase 2C panels under review_panels_phase2c_top120/ are included.
- **info** (VWR-04): viewer/viewer_data.json duplicates the payload already embedded in index.html; index.html never references it, so the sidecar (10.5 MiB) is redundant inside the packet
- **info** (VWR-02): viewer sidecar files never referenced by viewer/index.html: ['legend.json', 'run_manifest.json', 'viewer_data.json']
- **info** (VWR-03): the viewer opens directly from the filesystem (file://) because it makes no fetch/XHR calls; no local web server is required
