from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import sys
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path


AGENTS_ROOT = Path(__file__).resolve().parents[1]
ANTHONY_ROOT = AGENTS_ROOT.parent
sys.path.insert(0, str(AGENTS_ROOT))

from fastmcp import Client

from spatial_clustering.core import (
    analyze_data,
    analyze_knn_association,
    compare_random_baseline_data,
    graph_components,
    knn_association_data,
    load_config,
    load_records,
    prepare_cluster_scene,
    run_complete_analysis,
)
from spatial_clustering.mcp_server import mcp


CURRENT_CONFIG = AGENTS_ROOT / "configs" / "current_specimen.json"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_synthetic_case(root: Path, permutations: int = 30) -> Path:
    junctions = [
        {"id": 0, "position": [0.0, 0.0, 0.0]},
        {"id": 1, "position": [1.0, 1.0, 0.0]},
        {"id": 2, "position": [2.0, 0.0, 0.0]},
        {"id": 3, "position": [3.0, 1.0, 0.0]},
        {"id": 4, "position": [4.0, 0.0, 0.0]},
        {"id": 5, "position": [5.0, 1.0, 0.0]},
        {"id": 6, "position": [6.0, 0.0, 0.0]},
    ]
    struts = [
        {"id": i, "junction0": i, "junction1": i + 1}
        for i in range(6)
    ]
    nominal = {"junctions": junctions, "struts": struts, "unit_cells": []}
    registered = {
        "junctions": [
            {"id": row["id"], "position": [10.0 + 4.0 * v for v in row["position"]]}
            for row in junctions
        ],
        "struts": struts,
        "unit_cells": [],
    }
    (root / "nominal.json").write_text(json.dumps(nominal), encoding="utf-8")
    (root / "registered.json").write_text(json.dumps(registered), encoding="utf-8")

    labels = [
        "phase2c_auto_supported_possible_unintended_missing",
        "phase2c_auto_supported_possible_unintended_disconnected",
        "phase2c_auto_supported_present_like",
        "phase2c_still_review_required",
        "phase2c_low_priority_uncertain_not_defect_like",
        "phase2c_auto_supported_designed_removed_absent_or_disconnected",
    ]
    rows = []
    for i, label in enumerate(labels):
        rows.append(
            {
                "edge_id": f"E_N{i:06d}_N{i+1:06d}",
                "source_strut_id": i,
                "node_u": f"N{i:06d}",
                "node_v": f"N{i+1:06d}",
                "phase2c_label": label,
                "phase2c_status": "test",
                "phase2c_confidence_tier": "test",
                "phase2c_reason": "synthetic",
                "boundary_bin": "boundary" if i < 3 else "interior",
                "orientation_key": "ori110",
                "phase2c_method_ids": "TEST",
                "phase2c_assumption_ids": "TEST",
                "phase2c_reference_ids": "TEST",
            }
        )
    write_csv(root / "labels.csv", rows)
    write_csv(
        root / "humans.csv",
        [
            {
                "edge_id": "E_N000000_N000001",
                "normalized_human_ct_label": "material_disconnected",
            }
        ],
    )
    config = {
        "schema_version": "1.0.0",
        "specimen_id": "synthetic",
        "records_path": "labels.csv",
        "human_labels_path": "humans.csv",
        "registered_graph_path": "registered.json",
        "nominal_graph_path": "nominal.json",
        "output_root": "outputs",
        "graph_unit_mm": 2.28,
        "unit_cell_mm": 4.56,
        "estimated_voxel_size_um": 57.7379,
        "dbscan_eps_mm": [2.28, 4.56, 6.84],
        "dbscan_min_samples": 2,
        "permutation_count": permutations,
        "random_seed": 9,
        "build_axis_xyz": 1,
    }
    path = root / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


class CurrentDataIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(CURRENT_CONFIG)
        cls.records, cls.metadata = load_records(cls.config)

    def test_expected_population_counts(self) -> None:
        groups: dict[str, int] = {}
        for record in self.records:
            groups[record["automated_group"]] = groups.get(record["automated_group"], 0) + 1
        self.assertEqual(
            groups,
            {
                "present": 14820,
                "low_priority_uncertain": 2654,
                "review_required": 677,
                "main": 228,
                "intentional": 89,
            },
        )
        main = [
            row["automated_defect_class"]
            for row in self.records
            if row["automated_group"] == "main"
        ]
        self.assertEqual(main.count("missing"), 215)
        self.assertEqual(main.count("broken"), 13)
        self.assertEqual(main.count("thin"), 0)

    def test_graph_and_coordinate_invariants(self) -> None:
        self.assertEqual(self.metadata["registered_strut_count"], 18468)
        self.assertEqual(self.metadata["classification_row_count"], 18468)
        self.assertEqual(
            self.metadata["bounds_lattice_xyz_mm"],
            [[0.0, 0.0, 0.0], [41.04, 41.04, 41.04]],
        )
        main = [row for row in self.records if row["automated_group"] == "main"]
        _, components, adjacent_pairs = graph_components(main)
        self.assertEqual(max(map(len, components)), 207)
        self.assertEqual(adjacent_pairs, 563)

    def test_human_labels_are_attached_without_removing_primary_candidates(self) -> None:
        reviewed = [row for row in self.records if row["human_ct_label"]]
        self.assertEqual(len(reviewed), 40)
        ambiguous = [row for row in reviewed if row["human_ct_label"] == "ambiguous"]
        self.assertEqual(len(ambiguous), 4)
        self.assertTrue(all(row["automated_group"] == "main" for row in ambiguous))
        self.assertTrue(all(row["adjudicated_group"] == "review_required" for row in ambiguous))

    def test_knn_target_categories_cover_complete_graph(self) -> None:
        config = replace(self.config, permutation_count=5)
        result = knn_association_data(self.records, config)
        self.assertEqual(
            result["target_category_counts"],
            {
                "present": 14820,
                "unintentional_missing": 215,
                "unintentional_broken": 13,
                "intentional_missing": 89,
            },
        )
        self.assertEqual(sum(result["target_category_counts"].values()), 15137)
        self.assertEqual(result["unresolved_pool_count"], 3331)
        self.assertNotIn("review_required", result["target_category_order"])
        self.assertNotIn("uncertain", result["target_category_order"])
        self.assertTrue(
            all(
                row["target_class"]
                in {
                    "present",
                    "unintentional_missing",
                    "unintentional_broken",
                    "intentional_missing",
                }
                for row in result["association_rows"]
            )
        )
        self.assertTrue(
            all(
                row["resolved_neighbor_count"] + row["unresolved_neighbor_count"]
                == row["k"]
                for row in result["neighbor_rows"]
            )
        )
        self.assertEqual(
            result["source_counts"],
            {"unintentional_missing": 215, "unintentional_broken": 13},
        )


class SyntheticAnalysisTests(unittest.TestCase):
    def test_separate_groups_and_stable_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            config_path = make_synthetic_case(root)
            config = load_config(config_path)
            records, _ = load_records(config)
            membership, _, metrics = analyze_data(records, config)
            self.assertEqual(metrics["main"]["record_count"], 2)
            self.assertEqual(metrics["review_required"]["record_count"], 1)
            self.assertEqual(metrics["low_priority_uncertain"]["record_count"], 1)
            self.assertEqual(metrics["intentional"]["record_count"], 1)
            main = [row for row in membership if row["analysis_group"] == "main"]
            self.assertEqual({row["graph_cluster_id"] for row in main}, {"G0001"})

    def test_baselines_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            config_path = make_synthetic_case(root, permutations=25)
            config = load_config(config_path)
            records, _ = load_records(config)
            first = compare_random_baseline_data(records, config)
            second = compare_random_baseline_data(records, config)
            self.assertEqual(first, second)
            self.assertEqual(
                set(first["models"]),
                {"graph_opportunity", "boundary_orientation_stratified", "uniform_3d"},
            )

    def test_knn_detects_cross_type_neighbor_association(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            config = replace(
                load_config(make_synthetic_case(root, permutations=199)),
                knn_k_values=(1, 3),
            )
            records = []
            for pair in range(10):
                for offset, defect_class in enumerate(("missing", "broken")):
                    index = 2 * pair + offset
                    records.append(
                        {
                            "automated_group": "main",
                            "automated_defect_class": defect_class,
                            "edge_id": f"E{index:03d}",
                            "source_strut_id": index,
                            "midpoint_lattice_xyz_mm": [
                                pair * 10.0 + 0.1 * offset,
                                0.0,
                                0.0,
                            ],
                            "source_boundary_bin": "interior",
                            "source_orientation_key": "ori110",
                        }
                    )
            first = knn_association_data(records, config)
            second = knn_association_data(records, config)
            self.assertEqual(first, second)
            row = next(
                value
                for value in first["association_rows"]
                if value["model"] == "all_strut_label_permutation"
                and value["k"] == 1
                and value["source_class"] == "unintentional_missing"
                and value["target_class"] == "unintentional_broken"
                and value["metric"] == "mean_target_neighbor_fraction"
            )
            self.assertEqual(row["observed"], 1.0)
            self.assertGreater(row["observed"], row["null_mean"])
            self.assertLess(row["one_sided_attraction_p_value"], 0.05)
            self.assertEqual(len(first["neighbor_rows"]), 40)

    def test_complete_run_preserves_inputs_and_refuses_changed_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            config_path = make_synthetic_case(root, permutations=10)
            before = {
                path.name: file_hash(path)
                for path in root.iterdir()
                if path.is_file()
            }
            result = run_complete_analysis(config_path, "test_run")
            self.assertEqual(result["status"], "ok")
            output = Path(result["output_dir"])
            for expected in (
                "cluster_membership.csv",
                "cluster_summary.csv",
                "boundary_orientation_summary.csv",
                "random_baseline.json",
                "knn_neighbors.csv",
                "knn_association.csv",
                "knn_random_baseline.json",
                "knn_viewer_data.js",
                "cluster_scene.json",
                "REPORT.md",
                "run_config.json",
                "run_manifest.json",
            ):
                self.assertTrue((output / expected).exists(), expected)
            manifest_before = file_hash(output / "run_manifest.json")
            second = run_complete_analysis(config_path, "test_run")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(manifest_before, file_hash(output / "run_manifest.json"))
            manifest = json.loads((output / "run_manifest.json").read_text())
            self.assertIn("run_manifest.json", manifest["artifacts"])
            after = {
                path.name: file_hash(path)
                for path in root.iterdir()
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_scene_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            config_path = make_synthetic_case(root, permutations=5)
            first = prepare_cluster_scene(config_path, "scene_run", offset=0, limit=2)
            self.assertEqual(first["page_edge_count"], 2)
            self.assertIsNotNone(first["next_offset"])


class MCPAndAgentConfigurationTests(unittest.TestCase):
    def test_agent_configurations_parse_and_are_anthony_local(self) -> None:
        project_config = ANTHONY_ROOT / ".codex" / "config.toml"
        with project_config.open("rb") as handle:
            parsed = tomllib.load(handle)
        self.assertIn("defect_workflow_coordinator", parsed["agents"])
        self.assertIn("spatial_clustering_agent", parsed["agents"])
        for config in (AGENTS_ROOT / "agents").glob("*.toml"):
            with config.open("rb") as handle:
                agent = tomllib.load(handle)
            self.assertIn("name", agent)
            self.assertIn("developer_instructions", agent)
            self.assertTrue(config.resolve().is_relative_to(ANTHONY_ROOT.resolve()))

    def test_live_mcp_registration_and_annotations(self) -> None:
        async def check() -> None:
            async with Client(mcp) as client:
                tools = await client.list_tools()
                by_name = {tool.name: tool for tool in tools}
                expected = {
                    "analyze_spatial_clusters",
                    "compare_random_baseline",
                    "analyze_knn_association",
                    "summarize_boundary_distribution",
                    "prepare_cluster_scene",
                }
                self.assertEqual(set(by_name), expected)
                for tool in by_name.values():
                    self.assertFalse(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.destructiveHint)
                    self.assertTrue(tool.annotations.idempotentHint)
                    self.assertFalse(tool.annotations.openWorldHint)

        asyncio.run(check())

    def test_live_mcp_tool_call(self) -> None:
        async def check(config_path: Path) -> None:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "analyze_spatial_clusters",
                    {"config_path": str(config_path), "run_id": "mcp_run"},
                )
                self.assertFalse(result.is_error)
                self.assertEqual(result.data["status"], "ok")
                self.assertTrue(Path(result.data["outputs"]["cluster_membership_csv"]).exists())
                knn = await client.call_tool(
                    "analyze_knn_association",
                    {"config_path": str(config_path), "run_id": "mcp_run"},
                )
                self.assertFalse(knn.is_error)
                self.assertTrue(
                    Path(knn.data["outputs"]["knn_association_csv"]).exists()
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Anthony"
            root.mkdir()
            asyncio.run(check(make_synthetic_case(root, permutations=5)))


if __name__ == "__main__":
    unittest.main()
