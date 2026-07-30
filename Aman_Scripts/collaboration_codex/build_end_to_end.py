#!/usr/bin/env python3
"""Build the audited, file-by-file Part 2 handoff guide.

The narrative is deliberately conservative: artifact facts are reported as
verified, while behavior of the missing production source is identified as
documentation-derived.  The 120 panel paragraphs are generated from their
index records so the catalog remains exact and reviewable.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DEFAULT_HANDOFF = Path("collaboration/part2_verification_handoff_20260727")
DEFAULT_AUDIT = Path("Aman_Scripts/collaboration_codex/audit_outputs")
DEFAULT_OUTPUT = Path("Aman_Scripts/collaboration_codex/end-2-end.md")


FILE_DESCRIPTIONS = {
    "AGENT_INVENTORY.md": "A directory-level index of the packaged Codex agents and skills. It explains which specialist prompt is intended for segmentation, CT review, Part 2 defect analysis, and calibration; it is routing information, not scientific evidence or executable implementation.",
    "DEFECT_FINDING_PROCESS.md": "A concise description of the intended defect-finding chain, from design geometry and registered CT evidence through guarded labels, human spot checks, Phase 2C triage, and viewer export. Its wording correctly treats the outputs as candidates, but it cannot make the absent implementation reproducible.",
    "LABEL_DEFINITIONS.md": "The semantic contract for designed-removed, possible unintended missing, possible unintended disconnected, present-like, review-required, and low-priority uncertain states. This file is essential because several names encode evidence strength rather than physical ground truth; downstream reports must preserve those distinctions.",
    "MANIFEST.json": "The package inventory with expected paths, sizes, and SHA-256 values. All 175 non-self entries match the files on disk, but its entry for MANIFEST.json itself is stale because embedding a file's own final hash is self-referential; future packages should sign or checksum the manifest externally.",
    "NEXT_AGENT_PROMPT.md": "A handoff prompt telling a later agent how to continue review without silently promoting candidates to truth. It provides useful operational guardrails, although collaborator-specific paths and missing source prevent literal end-to-end execution.",
    "README_START_HERE.md": "The packet's front door. It identifies the conservative 214-candidate baseline, the provisional 228-candidate Phase 2C extension, the review queues, viewer, and documentation; this is the right first human-readable file, subject to the reproducibility warning in this audit.",
    "VERIFICATION_PROTOCOL.md": "The manual-review protocol and allowed label vocabulary. It requires evidence-based CT inspection and preservation of ambiguous cases; this is scientifically safer than treating the automated score as truth, but the supplied Phase 2C verification fields are still blank.",
    "agent_assets/.agents/skills/nde_report_expert/SKILL.md": "Instructions for extracting volume, mask, and skeleton features and building consistent NDE visual reports. The audit used its emphasis on traceable metrics and fixed views when checking the packet's summaries and imagery; it does not implement the missing Part 2 classifier.",
    "agent_assets/.agents/skills/part2-defect-analysis/SKILL.md": "The main specialist workflow for design-aware CT defect analysis. It enforces coordinate-frame checks, welded graph topology, conservative labels, review gates, and provenance, which directly shaped this audit's separation of verified artifacts from provisional inference.",
    "agent_assets/.agents/skills/part2-defect-analysis/agents/openai.yaml": "Display and invocation metadata for the Part 2 defect-analysis skill. It tells an agent when to select the skill but contains no numerical method or trained model.",
    "agent_assets/.agents/skills/threshold-optimizer/SKILL.md": "Guidance for threshold selection using structural metrics rather than voxel accuracy alone. It is relevant to Task 1 and to sensitivity analysis, while Part 2's final labels rely on a broader feature pipeline documented elsewhere.",
    "agent_assets/.agents/skills/threshold-optimizer/agents/openai.yaml": "Display and invocation metadata for the threshold-optimizer skill. It is configuration for agent routing, not a threshold result or test fixture.",
    "agent_assets/.codex/agents/ct_visual_review_agent.toml": "A specialist-agent prompt for inspecting CT review panels conservatively, checking multiple projections and recording uncertainty. It supports human-in-the-loop review but cannot substitute for the absent raw-panel generation code.",
    "agent_assets/.codex/agents/part2_defect_analysis_agent.toml": "The broad Part 2 analysis-agent prompt. It coordinates graph, design, CT, calibration, and reporting concerns and repeatedly warns against overclaiming; its claims about script behavior remain documentation-only here.",
    "agent_assets/.codex/agents/phase2b_ct_calibration_agent.toml": "A focused agent prompt for CT feature calibration and gate evaluation. It is useful for assigning a bounded calibration task, but it contains no executable sampler or learned parameters by itself.",
    "agent_assets/.codex/agents/segmentation_agent.toml": "A specialist prompt for segmentation work and structural validation. It belongs to the broader project toolchain and is not evidence that the Part 2 TIFF was re-segmented in this packet.",
    "final_report_baseline/agentic_workflow.md": "A narrative of how agents, deterministic scripts, and manual review were intended to cooperate. It is valuable as an orchestration design, but the claimed commands cannot be rerun until the original untracked source, tests, configs, and upstream outputs are recovered.",
    "final_report_baseline/figures/automated_review_label_counts.png": "The only non-panel PNG, a bar chart of automated-review class counts. It decodes correctly at 2160 x 1170, but the 14,820 present-like bar is more than 1,000 times the smallest headline defect class, making the small categories unreadable on one linear scale.",
    "final_report_baseline/final_ct_defect_report.md": "The conservative written result for Phase 2B.4. It reports 202 possible unintended missing plus 12 possible unintended disconnected candidates (214 combined, 1.158761% of 18,468 expected struts), alongside 89 designed-removed and 14,820 present-like edges; its status explicitly says this is a spot-check-supported automated estimate, not full ground truth.",
    "final_report_baseline/final_ct_defect_summary.json": "The machine-readable counterpart to the baseline report. Its counts and percentages reconcile exactly with the baseline tables, and it records the 40 top-ranked human spot checks: 29 absent, 7 disconnected, 4 ambiguous, and no clearly present-like contradiction.",
    "final_report_baseline/run_manifest.json": "A provenance snapshot for baseline packaging. It records hashes and Git state, and it supplies the decisive evidence that src/part2 and tests were untracked on the originating machine; it also contains machine-specific paths and therefore is evidence, not a portable run recipe.",
    "final_report_baseline/tables/auto_supported_unintended_candidates.csv": "The 214-row Phase 2B.4 candidate list: 202 possible missing and 12 possible disconnected. Row grain and edge IDs are internally consistent, but only the top 40 were manually spot-checked and that non-random sample cannot establish recall or whole-list precision.",
    "final_report_baseline/tables/headline_numbers.csv": "A compact table of baseline counts, denominators, and draft percentages used by the report. The arithmetic reconciles with the JSON summary and full candidate table.",
    "final_report_baseline/tables/human_spotcheck_label_counts.csv": "The aggregate of the 40 supplied human labels. It correctly preserves absent, disconnected, and ambiguous as separate outcomes; because the sample is ranks 1 through 40 only and lacks present-like controls, it is supportive evidence rather than a validation study.",
    "final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv": "The row-level record of the top-40 baseline spot check, including normalized label, notes, and source. These edge IDs are not the same set as ranks 1 through 40 in the later Phase 2C top-120 panel packet, so the labels must never be joined by rank alone.",
    "final_report_baseline/tables/manual_review_queue.csv": "The 920 Phase 2B.4 blocked cases retained for review. It represents uncertainty rather than confirmed defects and is a key safeguard against forcing mixed or unstable evidence into a binary label.",
    "final_report_baseline/tables/spotcheck_panel_index.csv": "The lookup between the baseline top-40 reviewed candidates and their original panel metadata. It supports provenance for the recorded human labels but the corresponding baseline panel PNGs are not included in this handoff.",
    "method_and_config/AGENTS.md": "Repository-level operating rules copied into the packet. It documents scope, terminology, and scientific caution expected of agents; it should guide work but does not provide missing runtime dependencies or source.",
    "method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md": "The 1,078-line method ledger linking method IDs, assumptions, physics, literature, thresholds, and phase decisions. It is the best technical rationale in the packet and was read in full, but several entries describe historical execution that cannot be independently rerun from this checkout.",
    "method_and_config/part2.yaml": "An early snapshot of Part 2 paths, stage settings, thresholds, and output conventions. It is useful for reconstructing intent, but it still says specimen mapping is UNVERIFIED, STL axis mapping is null, and the Phase 1 identity mapping is unverified, whereas later artifacts say the anchor gate selected perm021_signmmm. It is therefore stale planning context, not a ready-to-rerun Phase 2C configuration.",
    "method_and_config/requirements.txt": "A dependency snapshot from the originating environment. The current DSC environment contains the listed packages plus YAML support; optional VTK is absent, and the original run used Python 3.9 while DSC currently uses Python 3.11, so recovered source would still need compatibility testing.",
    "method_and_config/scientific_assumptions.yaml": "A structured registry of coordinate, segmentation, design, CT-feature, calibration, reporting, and triage assumptions. It is especially useful for identifying what must be challenged experimentally rather than silently accepted.",
    "notes_snapshot/00-big-picture.md": "A high-level map of the entire challenge, separating completed MCP tasks from the Part 2 research pipeline. It provides context and emphasizes that missing-strut analysis is design-aware rather than simple connected-component counting.",
    "notes_snapshot/01-how-to-run-code.md": "A 2,465-line chronological command journal covering Tasks 1 through 7 and all Part 2 phases. It is detailed enough to reconstruct intended CLI interfaces, but many commands reference absent Python modules, missing upstream output directories, and the collaborator's absolute paths.",
    "notes_snapshot/05-task-log-and-experiments.md": "A 2,971-line experiment log recording decisions, failures, test-count growth, timings, memory use, and status changes. It is valuable provenance: notably, Phase 2A failed to separate groups and Phase 2R was downgraded from verified to provisional after sparse transform coverage was recognized.",
    "notes_snapshot/21-part2-phase2b3-guarded-labels.md": "The focused record for converting complete CT features into guarded observations. It documents the 420 possible-missing, 58 possible-disconnected, 3,076 uncertain, 14,820 present-like, and 3,573 review-required Phase 2B.3 state before stricter automation.",
    "notes_snapshot/22-part2-phase2b4-automated-review.md": "The focused record for the stricter Phase 2B.4 rules that produced the conservative 214-candidate baseline, 920 blocked rows, and 2,425 low-priority uncertain rows. It explains why strong evidence flags and stability margins were required.",
    "notes_snapshot/23-part2-final-report-and-agentic-system.md": "The focused record for final baseline packaging, top-40 human labels, and the role of agents. It correctly distinguishes deterministic evidence generation from LLM orchestration and human judgment.",
    "notes_snapshot/24-part2-phase2c-automatic-triage-and-viewer.md": "The focused record for the second-pass queue triage, the 14 new promotions, 677 remaining review-required rows, 2,654 low-priority cases, and the all-edge viewer. The new promotions remain provisional because their human verification fields are blank.",
    "notes_snapshot/project-notebook.md": "A short notebook/index that directs readers to the larger logs and records the packet's overall state. It is useful orientation, not a substitute for the detailed journals or executable code.",
    "review_panels_phase2c_top120/ct_edge_panel_summary.csv": "The 120-row panel-generation summary with rank, edge ID, design state, crop shape, display window, and along-edge intensity statistics. It maps exactly to the 120 PNG filenames and JSON summary, but the field mean_delta_mm is misleading: it equals the dimensionless CT anomaly score in all 120 rows.",
    "review_panels_phase2c_top120/ct_edge_panel_summary.json": "The JSON form of the top-120 panel summary. It preserves the same ranking and quantitative panel metadata for programmatic consumers and reconciles with the CSV/PNG set, including the same incorrectly unit-labeled mean_delta_mm field.",
    "review_tables/human_verification_template.csv": "The 3,345-row blank review workbook covering the 14 Phase 2C promotions, 677 remaining review-required rows, and 2,654 low-priority audit rows. All human fields are blank, which is correct for a template but proves Phase 2C has not yet been verified.",
    "review_tables/low_priority_uncertain_2654_audit_table.csv": "The 2,654 cases demoted to low priority by Phase 2C. These are not asserted present and not counted as defects; a probability sample should still be reviewed to measure false negatives.",
    "review_tables/manual_queue_triage_report.md": "The written Phase 2C triage report. It explains the second-pass rules, 14 promotions, remaining queue, and limitations, and should be read together with the structured summary rather than as ground truth.",
    "review_tables/newly_promoted_14_to_verify.csv": "The first-priority verification list for the 14 cases promoted beyond the 214 baseline. Every corresponding human-review field is blank, so these rows cannot yet justify replacing the 214 baseline with 228.",
    "review_tables/phase2c_auto_supported_unintended_candidates.csv": "The combined 228 Phase 2C candidate rows: the baseline 214 plus exactly 14 promotions. Internal set reconciliation passes, but the file is a candidate queue, not a manually confirmed defect list.",
    "review_tables/phase2c_labels.csv": "The all-edge Phase 2C table with one unique record for each of 18,468 expected edges and extensive inherited features, evidence flags, prior labels, and current triage state. It is the central late-stage analytical artifact and the source for viewer classes.",
    "review_tables/phase2c_remaining_review_queue.csv": "The 677 cases still requiring review after Phase 2C, including five design-intent conflicts. Keeping these unresolved is appropriate; reporting them as defects or present would overstate the evidence.",
    "review_tables/phase2c_summary.json": "The machine-readable Phase 2C counts, settings, thresholds, and output paths. Its seven class counts sum exactly to 18,468 and its 228-candidate set reconciles to 214 prior candidates plus 14 promotions.",
    "review_tables/remaining_review_required_677_to_verify.csv": "A verification-focused copy/order of the same 677 unresolved rows. It is designed for human review and is not an additional population beyond phase2c_remaining_review_queue.csv.",
    "review_tables/review_panel_index.csv": "The detailed top-120 review index with graph endpoints, midpoint, exact TIFF Z slice/crop limits, anomaly score, and reason. It is the bridge between an edge ID and the CT evidence panel and agrees exactly with panel filenames and summaries.",
    "viewer/index.html": "A self-contained canvas-based graph viewer with embedded data, search, rotation, zoom, class toggles, reset, and click selection. Runtime smoke testing passed all 10 checks; it visualizes expected graph edges, not the CT surface, and default uncertain layers create substantial clutter.",
    "viewer/legend.json": "The seven-class legend and style mapping used by the viewer. Every edge style in viewer_data.json matches this mapping.",
    "viewer/run_manifest.json": "Viewer export provenance and input hashes. Its recorded Phase 2C label hash matches the packaged table, while the canonical graph input it cites is not included and therefore cannot be independently rehashed here.",
    "viewer/viewer_data.json": "The external viewer payload containing 18,468 unique graph edges, endpoints, current class, color, width, opacity, and metadata. It matches the JSON embedded in index.html exactly, and all endpoints are finite and lie within the recorded bounds.",
}


DOCUMENTED_MODULES = [
    ("src/part2/io/lattice_graph.py", "Parsed the real junction/strut/unit-cell schema, welded coincident raw junction aliases into physical nodes, retained provenance, and checked connectivity/topology. This welding is mandatory: raw per-cell IDs do not represent the global physical graph."),
    ("src/part2/phase0.py", "Orchestrated input preflight, LFS checks, canonicalization, graph consistency, nominal-to-registered transform estimation, and Phase 0 reports."),
    ("src/part2/design_intent/__init__.py", "Marked the design-intent helper package; no standalone behavior is documented."),
    ("src/part2/design_intent/stl_design_mapping.py", "Implemented the original provisional STL-difference heuristic and ranked 92 apparent design-removed edges; later methods superseded its mapping."),
    ("src/part2/ct_features/__init__.py", "Marked the CT-feature package; no standalone behavior is documented."),
    ("src/part2/ct_features/edge_sampler.py", "Prepared registered graph-edge samples in CT coordinates and handled the critical JSON [x,y,z] to TIFF-array [z,y,x] indexing conversion."),
    ("src/part2/phase1.py", "Ran initial STL inspection, provisional design mapping, edge previews, score plots, and review panels without claiming design labels were CT truth."),
    ("src/part2/visual_review/__init__.py", "Marked the visual-review package; no standalone behavior is documented."),
    ("src/part2/visual_review/ct_review_index.py", "Mapped edge geometry to exact TIFF slices and crop windows. It located evidence but did not classify a defect."),
    ("src/part2/visual_review/ct_edge_panels.py", "Rendered XY/XZ/YZ projections, a straightened edge slab, intensity profile, centerline overlay, and optional threshold contours from local TIFF crops."),
    ("src/part2/visual_review/ct_edge_compare.py", "Made shared-intensity side-by-side edge comparisons for visual teaching and QA, not final classification."),
    ("src/part2/design_intent/stl_axis_audit.py", "Enumerated axis permutations/reflections and audited skins, boundary directions, and graph/STL frames so identity orientation was not assumed."),
    ("src/part2/ct_features/edge_owned_sampler.py", "Excluded node-dominated endpoints, assigned voxels to the nearest eligible edge, measured core/background evidence, and evaluated threshold/radius/registration sensitivity."),
    ("src/part2/phase2a.py", "Swept CT sampler parameters on candidate and control edges. Its negative separation result was an appropriate stop rather than a classification success."),
    ("src/part2/design_intent/exact_stl_distance.py", "Compared sampled edge centerlines to both STL surfaces with point-to-triangle distances; despite its name, documentation says this was not a signed exact solid distance."),
    ("src/part2/phase2a1.py", "Scored all 18,468 edges under 48 frame symmetries and stopped because orientation remained unresolved."),
    ("src/part2/phase2r_tools.py", "Held heavy hybrid primitives for voxelized STL subtraction, deleted-component mapping, local CT correction, straightening, feature extraction, robust templates, transform fusion, bootstrap summaries, and gates."),
    ("src/part2/phase2r.py", "Ran the design/CT late-fusion benchmark. The logged run took about 464 seconds and 3.1 GB peak RAM and ended PROVISIONAL because the apparent best transform initially covered only 7 of 67 components."),
    ("src/part2/phase2r1_tools.py", "Expanded transform cohorts, ranked anchor cases, preserved human fields, validated CSV inputs, and performed numerical gate decisions."),
    ("src/part2/phase2r1.py", "Expanded CT coverage from 500 to 1,300 edges, obtained 67/67 coverage for the leading transform, and produced five primary human-anchor cases."),
    ("src/part2/phase2r1_anchor_gate.py", "Applied a lightweight post-review gate; five supplied anchors supported perm021_signmmm, but five anchors do not validate all defect labels."),
    ("src/part2/phase2b_tools.py", "Provided AUC/threshold summaries, robust template updates, deleted-component multiplicity estimates, candidate collapse, and safe boolean parsing."),
    ("src/part2/phase2b_calibration.py", "Calibrated 1,300 CT rows after the transform gate, obtaining documented AUC 0.9626 while still avoiding final specimen-wide percentages."),
    ("src/part2/phase2b1_reconcile.py", "Recognized one deleted STL component could represent several struts, expanding 67 components to 94 candidate edges and sampling missing CT rows."),
    ("src/part2/phase2b2_all_edge_prep.py", "Checkpointed, resumed, and prioritized feature sampling for all 18,468 edges. The logged full run took about 2.74 hours and reached roughly 3.15 GB memory."),
    ("src/part2/phase2b3_guarded_labels.py", "Converted complete CT features into guarded observations using anomaly, gap, area, occupancy, contrast, bridge, template, and stability evidence, leaving mixed cases unresolved."),
    ("src/part2/phase2b4_automated_review.py", "Applied stricter margins and evidence-count requirements to form the conservative 214-candidate baseline, 920 blocked cases, and 2,425 low-priority cases."),
    ("src/part2/final_report.py", "Packaged existing Phase 2B.4 artifacts and supplied top-40 labels into tables, figures, reports, and provenance; it did not generate new CT evidence."),
    ("src/part2/phase2c_manual_queue_triage.py", "Reused existing features for a stricter second pass, promoting 14 rows, retaining 677 for review, and demoting 2,654 to low priority."),
    ("src/part2/visualization/__init__.py", "Marked the visualization package; no standalone behavior is documented."),
    ("src/part2/visualization/export_defect_viewer.py", "Joined registered endpoints to labels and exported the dependency-free graph viewer and legend."),
    ("src/part2/run_defect_pipeline.py", "Checked inputs/hashes, planned stages, supported dry-run, reused Phase 2B.4 evidence, invoked Phase 2C and viewer export, and packaged reports."),
]


DOCUMENTED_TESTS = [
    ("test_lattice_graph.py", "schema parsing, alias welding, provenance, connectivity, and nominal/registered consistency"),
    ("test_stl_design_mapping.py", "initial STL-to-edge scoring and deterministic ranking"),
    ("test_edge_sampler.py", "registered edge sampling and CT-axis conversion"),
    ("test_ct_review_index.py", "deterministic edge-to-TIFF slice/window instructions"),
    ("test_ct_edge_panels.py", "crop extraction and repeatable panel rendering"),
    ("test_ct_edge_compare.py", "shared-scale comparison rendering and metadata"),
    ("test_stl_axis_audit.py", "coordinate-frame evidence and transform enumeration"),
    ("test_edge_owned_sampler.py", "endpoint exclusion, finite-edge ownership, local sampling, and perturbations"),
    ("test_phase2a1_exact_stl_distance.py", "point-to-triangle scoring and review ranking"),
    ("test_phase2r_hybrid_benchmark.py", "voxel subtraction, straightening, registration, robust statistics, transform fusion, coverage/anchor gates, and CSV validation; one VTK case was optional"),
    ("test_phase2b_calibration.py", "calibration statistics, multiplicity, candidate collapse, boolean parsing, batches, checkpoints, and all-edge preparation"),
    ("test_phase2b3_guarded_labels.py", "guarded-label boundaries, warnings, uncertainty, and design/CT separation"),
    ("test_phase2b4_automated_review.py", "strict auto-support, blocking, and low-priority rules"),
    ("test_final_report.py", "arithmetic, preservation of human labels, conservative wording, and packaging"),
    ("test_phase2c_manual_queue_triage.py", "promotion, demotion, preservation, and unresolved-case rules"),
    ("test_pipeline_and_viewer.py", "viewer joining/export and configuration-driven dry/full orchestration"),
]


AUDIT_SCRIPTS = [
    ("__init__.py", "Marks this audit directory as an importable Python package."),
    ("common.py", "Defines finding/report data models, streaming SHA-256, a strict ragged-row-aware CSV reader, JSON loading, and deterministic file enumeration."),
    ("file_audit.py", "Inventories all handoff files, reconciles the manifest, parses every structured artifact, detects raw-data exclusion and nonportable paths, and proves the documented production source is absent."),
    ("table_audit.py", "Checks row grain, edge-ID format, numeric domains, Phase 2B.4/2C counts, queue unions and disjointness, summaries, human-field blankness, and the exact 214-plus-14 set relationship."),
    ("scientific_audit.py", "Challenges external validity by comparing the candidate taxonomy with the paper, measuring top-rank review bias, checking the 14 unreviewed promotions, and profiling boundary concentration."),
    ("provenance_audit.py", "Checks assumption/method/reference registries, stale configuration, Boolean and NaN schema conventions, the Phase 2C change flag, viewer numeric types, and source-artifact hash lineage."),
    ("coverage_audit.py", "Reads only TIFF metadata plus saved tables/viewer geometry to detect invalid evidence support, zero-signal panels, partly covered promotions, and the mislabeled panel anomaly-score unit."),
    ("viewer_audit.py", "Confirms embedded/external viewer JSON equality, unique all-edge coverage, class counts, finite geometry, legend styles, and required static controls."),
    ("visual_audit.py", "Decodes all PNGs sequentially, checks dimensions and duplicates, reconciles panel ranks/edge IDs/indexes, and creates bounded-size contact sheets without holding the packet in memory."),
    ("make_contact_sheets.py", "Provides a focused CLI for regenerating the six 20-panel visual audit sheets."),
    ("browser_smoke.py", "Starts an ephemeral local viewer server and headless Chrome session, exercises search/toggle/zoom/reset/canvas behavior, captures two screenshots, and records console errors."),
    ("run_audit.py", "Orchestrates all static, tabular, provenance, scientific, coverage, viewer, and visual checks; saves inspectable evidence and exits nonzero while any blocking finding remains."),
    ("build_end_to_end.py", "Generates this guide from audited metadata, asserts exact 56-file description coverage, and emits one evidence paragraph for each of 120 panels."),
    ("report_audit.py", "Validates this generated Markdown's local links, catalog counts, required sections, current audit totals, coverage-failure IDs, and claim-language guardrails."),
    ("tests/__init__.py", "Marks the regression-test directory as a package."),
    ("tests/test_audit.py", "Runs the real packet through every audit component and locks in 43 integrity, scientific, coverage, provenance, viewer, visual, and report regressions."),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def rel_link(path: str) -> str:
    return f"../../collaboration/part2_verification_handoff_20260727/{path}"


def panel_paragraphs(handoff: Path, audit: Path) -> list[str]:
    summary = read_csv(handoff / "review_panels_phase2c_top120/ct_edge_panel_summary.csv")
    index_rows = read_csv(handoff / "review_tables/review_panel_index.csv")
    index = {row["edge_id"]: row for row in index_rows}
    evidence_x_max = max(int(row["tiff_x_max"]) for row in index_rows)
    images = {row["path"]: row for row in read_csv(audit / "image_inventory.csv")}
    paragraphs: list[str] = []
    for row in summary:
        rank = int(row["rank"])
        edge = row["edge_id"]
        filename = f"rank_{rank:03d}_{edge}_ct_panel.png"
        relative = f"review_panels_phase2c_top120/{filename}"
        image = images[relative]
        details = index[edge]
        state = row["design_state"].replace("phase2c_auto_supported_", "").replace("_", " ")
        all_zero_edge_signal = all(
            float(row[column]) == 0.0
            for column in (
                "axial_max_median",
                "axial_p95_median",
                "axial_mean_median",
                "centerline_median",
            )
        )
        endpoint_x = [float(details["endpoint_u_x"]), float(details["endpoint_v_x"])]
        if all_zero_edge_signal:
            coverage_note = (
                f" **Coverage warning:** all edge-aligned intensity summaries are zero and both endpoints lie beyond the observed x={evidence_x_max} evidence-support boundary. This is unreviewable coverage failure, not proof of absent material."
            )
        elif max(endpoint_x) > evidence_x_max:
            coverage_note = (
                f" **Coverage caution:** one endpoint crosses the observed x={evidence_x_max} evidence-support boundary, so endpoint evidence is incomplete."
            )
        else:
            coverage_note = ""
        paragraphs.extend(
            [
                f"### Panel {rank:03d}: `{filename}`",
                "",
                f"This is the Phase 2C review panel for edge `{edge}` (source strut `{row['source_strut_id']}`), ranked {rank} with recorded state **{state}**, CT anomaly score `{float(details['ct_missing_material_anomaly_score']):.6g}`, and review reason `{details['review_reason']}`. The TIFF crop is `{row['crop_shape_zyx']}` in array `[z,y,x]` order, centered near Z slice `{details['tiff_center_z_slice']}`. The PNG decoded successfully at {image['width']} x {image['height']} and maps exactly to both index tables.{coverage_note} It is visual evidence for a reviewer, not a human label; the supplied Phase 2C verification template is blank. [Open panel]({rel_link(relative)}).",
                "",
            ]
        )
    return paragraphs


def file_catalog(handoff: Path, audit: Path) -> list[str]:
    inventory = read_csv(audit / "file_inventory.csv")
    panel_prefix = "review_panels_phase2c_top120/rank_"
    nonpanels = [row for row in inventory if not row["path"].startswith(panel_prefix)]
    actual = {row["path"] for row in nonpanels}
    expected = set(FILE_DESCRIPTIONS)
    if actual != expected:
        raise RuntimeError(
            f"File-description catalog mismatch; missing={sorted(actual - expected)}, extra={sorted(expected - actual)}"
        )
    lines: list[str] = []
    for row in nonpanels:
        path = row["path"]
        lines.extend(
            [
                f"### `{path}`",
                "",
                f"{FILE_DESCRIPTIONS[path]} Audit metadata: {int(row['size_bytes']):,} bytes; SHA-256 `{row['sha256']}`. [Open file]({rel_link(path)}).",
                "",
            ]
        )
    return lines


def build_report(handoff: Path, audit: Path) -> str:
    report = json.loads((audit / "audit_report.json").read_text(encoding="utf-8"))
    counts = report["counts"]
    lines = [
        "# Part 2 Collaboration Handoff: Audited End-to-End Guide",
        "",
        "Generated 2026-07-28 from the local handoff and raw-data checkout. This document explains the intended system, records what was actually verified, catalogs every one of the 176 packaged files, and gives a safe path forward.",
        "",
        "## Executive verdict",
        "",
        "**Overall status: needs revision before the Part 2 result can be called reproducible or ground truth.** The handoff itself is unusually thorough and internally consistent: all 176 files were inventoried, all 175 non-self manifest hashes match, every structured file parses, all 121 PNGs decode, the all-edge tables and viewer reconcile, and the viewer passed runtime interaction tests. However, the packet contains **zero Python source files**. The documented `src/part2/` implementation and `tests/part2/` suite are absent from this working tree and from every reachable Git revision.",
        "",
        "The provenance is conclusive rather than speculative. `final_report_baseline/run_manifest.json` records `?? src/part2/` and `?? tests/` in the originating worktree, which means the friend generated the outputs while those directories were untracked and then committed the handoff without them. Consequently, the historical claim of 93 passing tests plus one optional VTK skip cannot be reproduced here. Re-implementing the algorithms from prose would create a new method, not validate the old one.",
        "",
        "The original packet's most conservative numerical result is the **Phase 2B.4 214-candidate queue**: 202 possible unintended missing plus 12 possible unintended disconnected among 18,468 expected struts, or a 1.158761% candidate fraction. This audit found that three of those 202 possible-missing rows have both endpoints beyond the evidence pipeline's apparent x=767 support limit, `no_local_material` endpoint statuses, and all-zero area profiles, despite being marked clean for auto-support. The raw TIFF is 761 x 815 x 837, so the x=767 clamp is an unexplained sampling/cropping problem rather than the TIFF's true boundary. Those three must become `coverage_blocked`; therefore even 214 cannot be presented as a fully defensible auto-supported count until that logic is fixed. Phase 2C's 228 is still more provisional because all 14 promotions have blank human-review fields.",
        "",
        "## What was verified",
        "",
        f"The automated audit records **{counts['pass']} passes, {counts['warn']} warnings, and {counts['fail']} blocking failures**. The failures are absent production/test source and invalid CT support for three auto-supported candidates; neither indicates corruption of the preserved packet files. The audit checked:",
        "",
        "- all 176 package paths, sizes, and streamed SHA-256 hashes;",
        "- every CSV, JSON, YAML, and TOML for parseability and table shape;",
        "- exact set/count reconciliation across Phase 2B.4, Phase 2C, review queues, and viewer data;",
        "- every one of 121 PNGs sequentially, avoiding simultaneous full-resolution image loads;",
        "- exact rank, edge-ID, filename, panel-summary, and panel-index mapping for all 120 CT panels;",
        "- viewer data, embedded JSON, legend styles, finite geometry, and all 18,468 edge IDs;",
        "- live viewer search, legend toggling, zoom, reset, canvas rendering, console health, and screenshots;",
        "- scientific stress checks against the cited 2023 paper, the top-40 review design, all 14 Phase 2C promotions, and boundary enrichment;",
        "- CT-support checks against raw TIFF metadata, exposing three unsupported baseline candidates and 40 zero-signal top-120 panels;",
        "- method/assumption/reference registries, config freshness, Boolean/NaN conventions, viewer numeric types, and source-artifact lineage.",
        "",
        "These checks validate **artifact integrity and internal consistency**. They do not validate the absent feature extractor, registration, classification thresholds, or physical truth of each candidate.",
        "",
        "## How the specialist skills changed this audit",
        "",
        "The packaged `part2-defect-analysis` skill made coordinate-frame auditing, junction welding, provenance, design/CT separation, and conservative label language mandatory. The `threshold-optimizer` skill shifted attention from raw voxel agreement to structural stability and sensitivity. The `nde_report_expert` skill motivated consistent visual inventories and traceable summaries. The external data-validation workflow then required grain checks, reconciliation, representativeness, caveats, and an explicit readiness verdict. These instructions are why this guide does not silently equate an anomaly score, a colored viewer edge, or a top-ranked panel with a confirmed physical defect.",
        "",
        "## Physical and coordinate context",
        "",
        "The cited paper describes Ti-5553 lattices with nominal 424 micrometer struts, 4.56 mm cells, build direction along y, skins normal to z, and CT voxel size 58.1 micrometers. Its MATLAB workflow aligned the scan and model with translation, rotation, and scale, thresholded the volume, extracted an expected-strut subvolume, flagged gaps/deviation, and **manually reviewed every flagged subvolume**.",
        "",
        "Graph/registered coordinates are stored as `[x,y,z]`; NumPy/TIFF volumes are indexed `[z,y,x]`. Therefore an expected edge with endpoints `(x1,y1,z1)` and `(x2,y2,z2)` must be sampled by converting physical/registered coordinates through the documented transform and then indexing `volume[z, y, x]`. A 'vortex' in earlier discussion is more accurately a **vertex/junction**. The TIFF does not directly store named vertices; vertex coordinates come from the registered design graph, while CT evidence tells whether material is present around each expected segment.",
        "",
        "The graph also requires positional welding. Raw junction IDs repeat across unit-cell boundaries; treating them as globally distinct creates hundreds of false components. The documented canonical graph has 3,430 physical nodes and 18,468 unique expected edges only after aliases are welded.",
        "",
        "## End-to-end pipeline",
        "",
        "```text",
        "design JSON + registered JSON + 0%/0.5% STL + CT TIFF",
        "  -> Phase 0 canonical welded graph and frame audit",
        "  -> Phase 1 provisional design-removed mapping and CT crop locations",
        "  -> Phase 2A / 2A.1 negative calibration and exact-distance/frame audits",
        "  -> Phase 2R hybrid STL subtraction + CT feature benchmark (provisional)",
        "  -> Phase 2R.1 expanded coverage + five human transform anchors",
        "  -> Phase 2B calibrated CT evidence",
        "  -> Phase 2B.1 component-to-multiple-edge reconciliation",
        "  -> Phase 2B.2 checkpointed all-18,468-edge feature sampling",
        "  -> Phase 2B.3 guarded observations and uncertainty",
        "  -> Phase 2B.4 strict 214-candidate conservative baseline",
        "  -> top-40 non-random human spot check",
        "  -> Phase 2C 14 provisional promotions + 677-row review queue",
        "  -> all-edge graph viewer, reports, and manifests",
        "```",
        "",
        "### Phase 0: canonical design graph",
        "",
        "The pipeline first parses nominal and registered graph JSON, detects LFS placeholders, welds coincident junction aliases, preserves raw provenance, and verifies connectivity and topology. This produces the only defensible edge universe. Any downstream method built directly on raw per-cell IDs can hallucinate disconnections at cell boundaries.",
        "",
        "### Phase 1: provisional design intent and review locations",
        "",
        "The two STL meshes are compared to find geometry apparently removed from the 0.5% design, then candidates are mapped to canonical edges. The initial heuristic yielded 92 candidates and was explicitly provisional. Registered edge geometry is also converted to TIFF slice/crop instructions; this locates evidence but does not itself decide present, missing, or disconnected.",
        "",
        "### Phase 2A and 2A.1: methods that correctly stopped",
        "",
        "Phase 2A calibrated an edge-owned CT sampler against the provisional removed/control groups and found poor separation (documented AUC 0.4758). Phase 2A.1 replaced the weak STL mapping with point-to-triangle distance scoring over all edges and audited 48 axis/sign symmetries, but stopped because the transform remained ambiguous. These negative results are useful: they prevent an attractive but invalid classifier from becoming a final answer.",
        "",
        "### Phase 2R and 2R.1: hybrid transform selection",
        "",
        "Phase 2R combined voxelized STL subtraction, deleted-component geometry, local CT alignment, straightened-strut features, robust templates, and late fusion over transforms. The apparent best transform `perm021_signmmm` was initially overclaimed because it covered only 7 of 67 components; the status was corrected to PROVISIONAL. Phase 2R.1 expanded CT coverage from 500 to 1,300 edges, achieved 67/67 candidate-component coverage for the leading transform, and used five manually reviewed anchors to pass a transform gate. This supports the frame choice but is not a specimen-wide defect truth set.",
        "",
        "### Phase 2B through 2B.2: calibration and all-edge features",
        "",
        "Phase 2B used the passed transform gate to calibrate removed candidates against controls and documented AUC 0.9626. Phase 2B.1 corrected the one-component/one-edge assumption by expanding 67 deleted components to 94 plausible edges. Phase 2B.2 then sampled all 18,468 expected edges with checkpoints and recomputed robust orientation/boundary/spatial templates. The journal says this all-edge run took about 2.74 hours and roughly 3.15 GB; it was not rerun on this 16 GB Mac because the source and prerequisite artifacts are absent.",
        "",
        "### Phase 2B.3 and 2B.4: guarded labels and baseline",
        "",
        "Phase 2B.3 combined anomaly score, axial occupancy, longest low-area gap, area, core/background contrast, template residual, 26-connectivity bridge status, threshold stability, and registration stability. It deliberately left mixed evidence unresolved. Phase 2B.4 raised the bar with stricter margins and minimum evidence counts, resulting in 202 possible unintended missing, 12 possible unintended disconnected, 89 designed-removed absent/disconnected, 14,820 present-like, 920 blocked, and 2,425 low-priority edges. That is the documented 214-candidate baseline, but the newly detected three-row support failure means its auto-support guard is incomplete.",
        "",
        "### Human spot check and Phase 2C",
        "",
        "A human reviewed only the top-ranked 40 of the baseline 214 and reported 29 absent, 7 disconnected, 4 ambiguous, and zero clearly present-like contradictions. This supports the ranking directionally but is a consecutive top-score sample with no present controls, so it cannot estimate whole-list precision, recall, or calibration. Phase 2C then reprocessed the blocked queue with stricter deterministic rules, promoted 14 rows, left 677 review-required, and moved 2,654 to low priority. Because none of the 14 is reviewed, 228 remains provisional.",
        "",
        "### Viewer and reporting",
        "",
        "The viewer draws every expected graph edge with a color representing its Phase 2C state. It is useful for global context, searching by edge ID, and toggling categories. It is **not a MeshLab/CT surface rendering** and cannot show voxel evidence by itself. The default view is cluttered because 2,654 low-priority and 677 review-required edges are enabled; a defect-focused preset is easier to interpret.",
        "",
        "### CT evidence-coverage failure found by this audit",
        "",
        "The raw TIFF metadata is `(z,y,x) = (761,815,837)`, yet every top-120 crop stops at x=767 and the viewer graph extends to x=773.744. Exactly 1,008 expected edges have at least one endpoint beyond x=767. Forty top-120 panels have completely zero edge-aligned slabs and traces; all 40 are review-required, which prevented those particular rows from being promoted, but they occupy one third of the review packet and need an explicit OUT OF SUPPORT watermark. More seriously, `E_N008309_N008313`, `E_N009317_N009321`, and `E_N009443_N009447` are already inside both the 214 and 228 candidate tables with two `no_local_material` endpoints, all-zero area profiles, and `phase2b4_clean_for_auto_support=true`. Rank 13 of the Phase 2C panels, `E_N001379_N001506`, also crosses the support boundary and needs endpoint caution. This is a pipeline-logic defect, not a new human judgment about whether any strut is physically present.",
        "",
        "## External scientific cross-check against 2246722.pdf",
        "",
        "For the paper's 0.5% specimen #1, Table 3 reports 0.57% total missing and 4.97% disconnected, with 0.50% nominal design removal; missing and disconnected are mutually exclusive there. Using 18,468 only as a common comparison denominator gives roughly 105 total missing, 92 nominally removed, about 13 excess/unintended missing, and 918 disconnected. Phase 2C instead contains 89 designed-removed, 215 possible unintended missing, and only 13 possible unintended disconnected.",
        "",
        "This mismatch does not automatically prove individual candidates wrong because the denominators, label rules, and pipeline purposes differ. It does prove the packet is **not paper-equivalent classification**: missing-like candidates are much more numerous and disconnected candidates much less numerous than the manually reviewed paper distribution. The leading interpretation is that the current output is a high-recall/uncertainty triage queue with a disconnected rule that is too strict or semantically different. It must be validated against a representative manual sample before physical percentages are claimed.",
        "",
        "## Documented production scripts (source absent)",
        "",
        "Every paragraph in this section is reconstructed from the journals and ledgers. None of these files exists in the packet, current worktree, or reachable Git history, so no function body was code-reviewed and no listed script was executed.",
        "",
    ]
    for path, description in DOCUMENTED_MODULES:
        lines.extend([f"### `{path}`", "", f"{description} **Verification status: documentation-only; source absent.**", ""])
    lines.extend(
        [
            "## Documented original tests (also absent)",
            "",
            "The journals say this suite reached 93 passing tests with one optional VTK skip. The following files and responsibilities are documentation-derived; the claim is historical testimony, not a reproducible result in this checkout.",
            "",
        ]
    )
    for path, description in DOCUMENTED_TESTS:
        lines.extend([f"### `tests/part2/{path}`", "", f"This test module reportedly covered {description}. **Verification status: test source absent and not runnable.**", ""])
    lines.extend(
        [
            "## How to use what is available now",
            "",
            "### 1. Run the memory-conscious artifact audit",
            "",
            "From the repository root:",
            "",
            "```bash",
            "/Users/amannindra/miniconda3/envs/DSC/bin/python -m unittest \\",
            "  Aman_Scripts.collaboration_codex.tests.test_audit -v",
            "",
            "/Users/amannindra/miniconda3/envs/DSC/bin/python \\",
            "  Aman_Scripts/collaboration_codex/run_audit.py",
            "```",
            "",
            "The unit tests should pass. `run_audit.py` intentionally exits with status 1 while production source is missing; inspect the JSON/Markdown outputs rather than suppressing that blocker. Image inspection is sequential, and contact sheets are capped at 20 panels each.",
            "",
            "### 2. Open and exercise the viewer",
            "",
            "Opening index.html directly may be sufficient because data are embedded. For a local web server:",
            "",
            "```bash",
            "cd collaboration/part2_verification_handoff_20260727/viewer",
            "/Users/amannindra/miniconda3/envs/DSC/bin/python -m http.server 8000 --bind 127.0.0.1",
            "```",
            "",
            "Then visit `http://127.0.0.1:8000/`. Search by exact edge ID, turn off present-like and uncertain categories for a defect-focused view, and use the review index to open CT evidence. The automated headless check is:",
            "",
            "```bash",
            "/Users/amannindra/miniconda3/envs/DSC/bin/python \\",
            "  Aman_Scripts/collaboration_codex/browser_smoke.py",
            "```",
            "",
            "### 3. Review Phase 2C without contaminating labels",
            "",
            "Start with `newly_promoted_14_to_verify.csv`, find each edge in `review_panel_index.csv`, inspect all available panel views, and enter only the allowed human label plus confidence/initials/date in a copy of `human_verification_template.csv`. Do not join the old baseline human labels to these panels by rank, and do not train/tune thresholds on the held-out verification decisions before reporting evaluation.",
            "",
            "### 4. Recover the real code before rerunning science",
            "",
            "Ask the friend for the exact untracked `src/part2/`, `tests/part2/`, root `configs/part2.yaml`, and the missing upstream Phase 2R/2B.2/2B.4 outputs or their immutable manifests. Preserve their original hashes and environment. First run unit tests serially with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, then a pipeline dry run. Do not initially launch Phase 2R, all-edge sampling, or a full pipeline on this 16 GB Mac; run heavy stages one at a time only after source and prerequisite recovery.",
            "",
            "## Audit scripts added in `Aman_Scripts/collaboration_codex`",
            "",
            "These are independent verification utilities written for this review. They do not modify the collaboration packet or invent replacement Part 2 science.",
            "",
        ]
    )
    for path, description in AUDIT_SCRIPTS:
        lines.extend([f"### `{path}`", "", description, ""])
    lines.extend(
        [
            "## Tests actually run in this audit",
            "",
            "- **43/43 local audit unit tests passed.** These cover inventory, non-self hashes, parser coverage, missing-source detection, Phase 2B.4/2C reconciliation, viewer equivalence, all-image decode, panel mapping, contact-sheet coverage, ragged-CSV rejection, hash determinism, chart readability, paper mismatch, sampling bias, unreviewed promotions, provenance registries, stale config, schema hazards, source lineage, and CT-support failures.",
            f"- **{sum(counts.values())} consolidated checks:** {counts['pass']} passed, {counts['warn']} warned, and {counts['fail']} failed. The failures are retained for absent production/test source and three auto-supported candidates without valid CT support.",
            "- **Three packaged skills validated** with the skill validator.",
            "- **All 121 PNGs decoded**, including 120 panels at 2790 x 1655; no exact duplicates were found.",
            "- **Viewer runtime passed 10/10 checks** in headless Chrome, including 18,468 edges, seven legend classes, search, toggle, wheel zoom, reset, screenshots, and no material console errors. A favicon 404 was recorded separately as harmless.",
            "- **The original claimed 93-test suite was not run** because no such test or production source exists in the checkout.",
            "- **Heavy scientific stages were not rerun** because their implementation and cumulative inputs are absent; doing so would also be an unnecessary memory/runtime risk at this stage.",
            "",
            "## Errors and improvements, in priority order",
            "",
            "### P0 - fix the CT valid-sample gate",
            "",
            "Demote the three fully unsupported candidate edges to a new `coverage_blocked` state immediately. Find why edge/panel support clamps at x=767 while the source TIFF contains x indices 0 through 836, then regenerate their features from the correct axis/volume. Require a minimum valid-sample/in-bounds fraction before any missing or disconnected auto-support rule can fire. Watermark all 40 zero-signal panels as OUT OF SUPPORT and retain an explicit validity mask. Recheck the partially covered Phase 2C rank-13 promotion before accepting it.",
            "",
            "### P0 - recover reproducibility",
            "",
            "Recover and commit the exact source, tests, root config, lock/environment file, and required upstream outputs. Add a run manifest for every stage containing source commit/tree hash, config hash, raw-input hashes, upstream-output hashes, command, Python/package versions, seed, timestamps, and peak memory. Exclude MANIFEST.json from its own internal hash and instead publish an external checksum or signature.",
            "",
            "Do not reuse the packaged `method_and_config/part2.yaml` as-is: it still encodes an unverified identity/unknown STL mapping, whereas later outputs depend on `perm021_signmmm`. Recover the exact effective run config and register the missing method IDs `CT-ATLAS-001`, `CT-REG-LOCAL-001`, `CT-STRAIGHTEN-001` and assumption IDs `A-CT-FEATURES-001`, `A-STL-AXIS-001-HUMAN-ANCHORED`.",
            "",
            "### P0 - build a defensible truth/evaluation set",
            "",
            "Blindly review all 14 Phase 2C promotions plus a stratified random sample from the remaining 200 baseline candidates, 677 review-required rows, 2,654 low-priority rows, and 14,820 present-like controls. Stratify by orientation, boundary bin, spatial region, anomaly score, and label type. Use at least two reviewers on a subset, adjudicate disagreement, and report confidence intervals, inter-rater agreement, per-class precision/recall, and calibration. The present pipeline has no recall estimate.",
            "",
            "### P0 - align physical class definitions",
            "",
            "Match the paper's mutually exclusive missing/disconnected definitions or clearly publish a different taxonomy. Investigate why the paper-equivalent comparison suggests roughly 918 disconnected edges while the pipeline flags only 13, and why 215 unintended-missing candidates greatly exceed the paper's approximate excess of 13. Treat this as a calibration/semantic alarm, not as a reason to force counts to match.",
            "",
            "### P1 - challenge boundary and registration artifacts",
            "",
            "Possible-unintended candidates are disproportionately boundary/near-boundary. Add boundary/skin-specific templates, crop-completeness flags, perturbation tests around the transform, local alignment residual thresholds, and negative controls. Report how candidate counts change under plausible registration, threshold, radius, and endpoint-exclusion perturbations.",
            "",
            "### P1 - make review evidence easier to use",
            "",
            "Default the viewer to defect-focused classes, add a preset for all/defects/review-required, center and zoom a searched edge, prevent a selected class from becoming invisibly hidden, link directly to its CT panel, add depth sorting or a 3D library, and optionally overlay CT/STL surfaces. A graph line alone cannot prove material loss.",
            "",
            "### P1 - improve reporting and portability",
            "",
            "Replace collaborator-specific absolute paths with repository-relative paths and a single configurable data root. Rename `mean_delta_mm` to `ct_anomaly_score`, normalize `LLNLDSC2026`/`LLNL-DSC-2026`, serialize booleans consistently, replace literal `nan` with null plus validity status, make viewer scores/evidence counts numeric, and rename the Phase 2C change flag to distinguish lexical changes from promotions. Redesign the class-count chart with direct labels and either a separate defect-only panel, broken axis, or log scale. Record exactly which panels were reviewed and avoid reusing rank as identity across runs.",
            "",
            "## Simple high-level explanation",
            "",
            "Think of the design as a list of 18,468 expected sticks. The JSON says where each stick should be. The TIFF is a 3D X-ray image that says where metal appears to be. The intended code follows each expected stick through the X-ray volume, measures whether metal continues from one end to the other, compares it with similar healthy sticks, and gives suspicious sticks to a person for review.",
            "",
            "The packet is good at preserving the **results of that process**: tables, panels, counts, notes, and a viewer all agree with one another. What is missing is the **machine that produced them**: the Part 2 Python files and their tests. That means we can prove the package is internally intact, but we cannot yet prove the underlying detector was implemented exactly as described.",
            "",
            "The best current answer is therefore: the original system nominated 214 edges and the 40 highest-ranked looked defect-like or ambiguous to the reviewer, but at least three lower-ranked nominees lack valid CT support because of an x-coverage bug. This is not enough to claim 214 confirmed defects. Fourteen more candidates are unreviewed, and one of those is only partly covered. Fix coverage, recover the source, review a representative sample including normal-looking controls, and then calculate real accuracy before publishing a physical defect percentage.",
            "",
            "## Audit artifacts produced by Codex terminal 2",
            "",
            "- [Consolidated audit summary](audit_outputs/audit_summary.md)",
            "- [Machine-readable audit report](audit_outputs/audit_report.json)",
            "- [Complete file inventory](audit_outputs/file_inventory.csv)",
            "- [Complete image inventory](audit_outputs/image_inventory.csv)",
            "- [Viewer runtime result](audit_outputs/browser/viewer_runtime_result.json)",
            "- [Viewer default screenshot](audit_outputs/browser/viewer_runtime.png)",
            "- [Viewer candidate-focused screenshot (also includes designed removals)](audit_outputs/browser/viewer_defects_only.png)",
            "- [Panels 001-020 contact sheet](audit_outputs/contact_sheets/phase2c_panels_001_020.jpg)",
            "- [Panels 021-040 contact sheet](audit_outputs/contact_sheets/phase2c_panels_021_040.jpg)",
            "- [Panels 041-060 contact sheet](audit_outputs/contact_sheets/phase2c_panels_041_060.jpg)",
            "- [Panels 061-080 contact sheet](audit_outputs/contact_sheets/phase2c_panels_061_080.jpg)",
            "- [Panels 081-100 contact sheet](audit_outputs/contact_sheets/phase2c_panels_081_100.jpg)",
            "- [Panels 101-120 contact sheet](audit_outputs/contact_sheets/phase2c_panels_101_120.jpg)",
            "",
            "## File-by-file catalog: 56 documents, tables, configs, agents, viewer files, and figure",
            "",
            "The following paragraphs cover every packaged file except the 120 review-panel PNGs, which have their own one-by-one catalog afterward. Hashes are from the fresh local audit.",
            "",
        ]
    )
    lines.extend(file_catalog(handoff, audit))
    lines.extend(
        [
            "## File-by-file catalog: all 120 CT review panels",
            "",
            "Every panel was decoded and visually sampled through six contact sheets. No panel is silently assigned a new human label here. The quantitative metadata below identify exactly what each file represents and where its CT crop lies.",
            "",
        ]
    )
    lines.extend(panel_paragraphs(handoff, audit))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-root", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    handoff = args.handoff_root.resolve()
    audit = args.audit_dir.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(handoff, audit), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
