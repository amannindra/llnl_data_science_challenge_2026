"""Regression tests for every audit component against the real handoff."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Aman_Scripts.collaboration_codex.build_end_to_end import FILE_DESCRIPTIONS, panel_paragraphs
from Aman_Scripts.collaboration_codex.common import AuditReport, read_csv, sha256_file
from Aman_Scripts.collaboration_codex.coverage_audit import run_coverage_audit
from Aman_Scripts.collaboration_codex.file_audit import run_file_audit
from Aman_Scripts.collaboration_codex.provenance_audit import run_provenance_audit
from Aman_Scripts.collaboration_codex.report_audit import audit_report_file
from Aman_Scripts.collaboration_codex.scientific_audit import run_scientific_audit
from Aman_Scripts.collaboration_codex.table_audit import run_table_audit
from Aman_Scripts.collaboration_codex.viewer_audit import extract_embedded_viewer_data, run_viewer_audit
from Aman_Scripts.collaboration_codex.visual_audit import create_contact_sheets, run_visual_audit


REPO = Path(__file__).resolve().parents[3]
HANDOFF = REPO / "collaboration/part2_verification_handoff_20260727"
AUDIT = REPO / "Aman_Scripts/collaboration_codex/audit_outputs"


class CollaborationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = AuditReport()
        cls.inventory = run_file_audit(HANDOFF, REPO, cls.report)
        cls.tables = run_table_audit(HANDOFF, cls.report)
        cls.provenance = run_provenance_audit(HANDOFF, REPO, cls.report)
        cls.science = run_scientific_audit(HANDOFF, REPO, cls.report)
        cls.coverage = run_coverage_audit(HANDOFF, REPO, cls.report)
        cls.viewer = run_viewer_audit(HANDOFF, cls.report)
        cls.images = run_visual_audit(HANDOFF, cls.report)
        cls.by_id = {finding.check_id: finding for finding in cls.report.findings}

    def assert_check(self, check_id: str, expected: str = "pass") -> None:
        self.assertIn(check_id, self.by_id)
        self.assertEqual(self.by_id[check_id].status, expected, self.by_id[check_id])

    def test_01_inventory_has_every_handoff_file(self) -> None:
        self.assertEqual(len(self.inventory), 176)

    def test_02_manifest_covers_every_file(self) -> None:
        self.assert_check("manifest.coverage")

    def test_03_nonself_manifest_hashes_match(self) -> None:
        self.assert_check("manifest.nonself_integrity")

    def test_04_manifest_self_hash_limitation_is_detected(self) -> None:
        self.assert_check("manifest.self_hash", "warn")

    def test_05_all_structured_files_parse(self) -> None:
        self.assert_check("structured.parseability")

    def test_06_raw_data_is_excluded(self) -> None:
        self.assert_check("packet.raw_data_exclusion")

    def test_07_missing_production_source_is_detected(self) -> None:
        self.assert_check("source.production_code_available", "fail")

    def test_08_phase2c_all_edge_grain_is_unique(self) -> None:
        self.assert_check("phase2c.labels.unique_edges")
        self.assertEqual(len(self.tables["phase2c"]["labels"]), 18468)

    def test_09_phase2c_label_distribution_reconciles(self) -> None:
        self.assert_check("phase2c.label_distribution")

    def test_10_verification_template_is_exact_union(self) -> None:
        self.assert_check("phase2c.verification_template_union")

    def test_11_human_template_is_blank(self) -> None:
        self.assert_check("phase2c.human_template_blank")

    def test_12_phase2c_is_exact_214_plus_14(self) -> None:
        self.assert_check("phase2c.promotion_delta")

    def test_13_conservative_baseline_reconciles(self) -> None:
        self.assert_check("phase2b4.baseline_reconciliation")

    def test_14_viewer_covers_all_edges(self) -> None:
        self.assert_check("viewer.edge_counts")
        self.assert_check("viewer.edge_coverage")

    def test_15_viewer_embedded_json_is_valid_and_equal(self) -> None:
        html = (HANDOFF / "viewer/index.html").read_text(encoding="utf-8")
        self.assertEqual(extract_embedded_viewer_data(html), self.viewer)

    def test_16_all_images_decode(self) -> None:
        self.assert_check("images.decode_all")
        self.assertEqual(len(self.images), 121)

    def test_17_all_panel_names_map_to_indexes(self) -> None:
        self.assert_check("images.panel_index_mapping")

    def test_18_contact_sheet_generator_covers_all_panels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outputs = create_contact_sheets(HANDOFF, Path(directory))
            self.assertEqual(len(outputs), 6)
            self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in outputs))

    def test_19_csv_reader_rejects_ragged_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("a,b\n1,2,3\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_csv(path)

    def test_20_sha256_is_deterministic(self) -> None:
        path = HANDOFF / "README_START_HERE.md"
        self.assertEqual(sha256_file(path), sha256_file(path))

    def test_21_misleading_chart_scale_is_detected(self) -> None:
        self.assert_check("images.baseline_chart_scale", "warn")

    def test_22_paper_mismatch_is_detected(self) -> None:
        self.assert_check("science.paper_external_consistency", "warn")
        self.assertGreater(
            self.science["ratios"]["paper_disconnected_vs_pipeline_possible_disconnected"],
            50,
        )

    def test_23_top_rank_sampling_bias_is_detected(self) -> None:
        self.assert_check("science.human_review_sampling", "warn")

    def test_24_unreviewed_phase2c_promotions_are_detected(self) -> None:
        self.assert_check("science.phase2c_promotions_unreviewed", "warn")

    def test_25_missing_assumption_registry_entries_are_detected(self) -> None:
        self.assert_check("provenance.assumption_registry", "warn")
        self.assertEqual(
            self.provenance["missing_assumptions"],
            ["A-CT-FEATURES-001", "A-STL-AXIS-001-HUMAN-ANCHORED"],
        )

    def test_26_missing_method_ledger_entries_are_detected(self) -> None:
        self.assert_check("provenance.method_registry", "warn")
        self.assertEqual(
            self.provenance["missing_methods"],
            ["CT-ATLAS-001", "CT-REG-LOCAL-001", "CT-STRAIGHTEN-001"],
        )

    def test_27_stale_phase2_config_is_detected(self) -> None:
        self.assert_check("provenance.config_snapshot_stale", "warn")

    def test_28_schema_boolean_and_nan_issues_are_detected(self) -> None:
        self.assert_check("schema.boolean_casing", "warn")
        self.assert_check("schema.literal_nan", "warn")
        self.assertEqual(
            self.provenance["nan_counts"],
            {
                "centerline_displacement_voxels": 545,
                "curvature_voxels": 600,
                "node_u_registration_residual_voxels": 785,
                "node_v_registration_residual_voxels": 697,
            },
        )

    def test_29_phase2c_change_flag_semantics_are_detected(self) -> None:
        self.assert_check("schema.phase2c_changed_semantics", "warn")
        self.assertEqual(self.provenance["changed_count"], 1009)

    def test_30_viewer_numeric_strings_are_detected(self) -> None:
        self.assert_check("schema.viewer_numeric_types", "warn")

    def test_31_incomplete_source_artifact_lineage_is_detected(self) -> None:
        self.assert_check("provenance.source_artifact_lineage", "warn")
        self.assertTrue(all(self.provenance["included_hash_matches"].values()))

    def test_32_auto_candidates_without_ct_support_are_blocked(self) -> None:
        self.assert_check("coverage.auto_supported_without_ct_support", "fail")
        self.assertEqual(
            {row["edge_id"] for row in self.coverage["unsupported_candidates"]},
            {
                "E_N008309_N008313",
                "E_N009317_N009321",
                "E_N009443_N009447",
            },
        )

    def test_33_zero_signal_review_panels_are_detected(self) -> None:
        self.assert_check("coverage.review_panels_zero_edge_signal", "warn")
        self.assertEqual(len(self.coverage["all_zero_panels"]), 40)

    def test_34_partial_support_promotion_is_detected(self) -> None:
        self.assert_check("coverage.promotions_cross_support_boundary", "warn")
        self.assertEqual(
            [row["edge_id"] for row in self.coverage["partial_promotions"]],
            ["E_N001379_N001506"],
        )

    def test_35_panel_metric_unit_mislabel_is_detected(self) -> None:
        self.assert_check("coverage.panel_metric_units", "warn")

    def test_36_end_to_end_catalog_covers_every_packet_file(self) -> None:
        panel_prefix = "review_panels_phase2c_top120/rank_"
        nonpanel_paths = {
            row["path"] for row in self.inventory if not row["path"].startswith(panel_prefix)
        }
        self.assertEqual(nonpanel_paths, set(FILE_DESCRIPTIONS))
        panel_lines = panel_paragraphs(HANDOFF, AUDIT)
        self.assertEqual(sum(line.startswith("### Panel ") for line in panel_lines), 120)

    def test_37_generated_report_links_resolve(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["all_local_links_resolve"], result)

    def test_38_generated_report_covers_all_files(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["all_56_nonpanel_files_cataloged"], result)
        self.assertTrue(result["checks"]["all_120_panels_cataloged"], result)

    def test_39_generated_report_covers_documented_code_and_tests(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["all_documented_modules_cataloged"], result)
        self.assertTrue(result["checks"]["all_documented_tests_cataloged"], result)
        self.assertTrue(result["checks"]["all_audit_scripts_explained"], result)

    def test_40_generated_report_has_current_audit_counts(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["audit_counts_current"], result)

    def test_41_generated_report_names_coverage_failures(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["coverage_failures_named"], result)

    def test_42_generated_report_preserves_claim_guardrails(self) -> None:
        result = audit_report_file(
            REPO / "Aman_Scripts/collaboration_codex/end-2-end.md",
            AUDIT / "audit_report.json",
        )
        self.assertTrue(result["checks"]["required_sections_present"], result)
        self.assertTrue(result["checks"]["no_paste_placeholder"], result)
        self.assertTrue(result["checks"]["candidate_not_ground_truth_guardrail"], result)

    def test_43_reference_id_split_is_detected_across_artifacts(self) -> None:
        self.assert_check("provenance.reference_id_normalization", "warn")
        self.assertIn(
            ["LLNL-DSC-2026", "LLNLDSC2026"],
            self.provenance["split_references"].values(),
        )


if __name__ == "__main__":
    unittest.main()
