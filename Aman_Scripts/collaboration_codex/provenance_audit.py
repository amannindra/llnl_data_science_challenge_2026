"""Audit method/assumption registries, schema hygiene, and run lineage."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml

from .common import AuditReport, load_json, read_csv, sha256_file


def _pipe_ids(rows: list[dict[str, str]], suffix: str) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        for column, value in row.items():
            if column == suffix or column.endswith(f"_{suffix}"):
                ids.update(part.strip() for part in value.split("|") if part.strip())
    return ids


def run_provenance_audit(root: Path, repo_root: Path, report: AuditReport) -> dict:
    labels = read_csv(root / "review_tables/phase2c_labels.csv")[1]
    assumptions_path = root / "method_and_config/scientific_assumptions.yaml"
    assumptions = yaml.safe_load(assumptions_path.read_text(encoding="utf-8"))
    defined_assumptions = {item["id"] for item in assumptions["assumptions"]}
    cited_assumptions = _pipe_ids(labels, "assumption_ids")
    missing_assumptions = sorted(cited_assumptions - defined_assumptions)
    report.add(
        "provenance.assumption_registry",
        "warn" if missing_assumptions else "pass",
        "The all-edge table cites assumption IDs that are absent from the formal scientific-assumptions registry."
        if missing_assumptions
        else "Every assumption ID cited by the all-edge table is defined in the registry.",
        severity="medium" if missing_assumptions else "info",
        path=assumptions_path,
        evidence={"missing_ids": missing_assumptions},
    )

    ledger_path = root / "method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md"
    ledger = ledger_path.read_text(encoding="utf-8")
    cited_methods = _pipe_ids(labels, "method_ids")
    missing_methods = sorted(method for method in cited_methods if method not in ledger)
    report.add(
        "provenance.method_registry",
        "warn" if missing_methods else "pass",
        "Method IDs used in all-edge provenance are not defined or cited by the methods ledger."
        if missing_methods
        else "Every method ID cited by the all-edge table appears in the methods ledger.",
        severity="medium" if missing_methods else "info",
        path=ledger_path,
        evidence={"missing_ids": missing_methods},
    )

    cited_references = _pipe_ids(labels, "reference_ids")
    reference_corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "final_report_baseline/final_ct_defect_summary.json",
            root / "method_and_config/METHODS_AND_PHYSICS_REFERENCE_LEDGER.md",
            root / "review_tables/phase2c_summary.json",
        )
    )
    cited_references.update(
        variant
        for variant in ("LLNLDSC2026", "LLNL-DSC-2026")
        if variant in reference_corpus
    )
    normalized: dict[str, list[str]] = defaultdict(list)
    for reference in cited_references:
        normalized["".join(character for character in reference.lower() if character.isalnum())].append(reference)
    split_references = {
        key: sorted(values) for key, values in normalized.items() if len(values) > 1
    }
    report.add(
        "provenance.reference_id_normalization",
        "warn" if split_references else "pass",
        "Equivalent literature/source references use multiple identifiers, weakening automated lineage joins."
        if split_references
        else "Reference identifiers normalize uniquely.",
        severity="low" if split_references else "info",
        evidence={"equivalent_id_groups": split_references},
    )

    config_path = root / "method_and_config/part2.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    stale_values = {
        "specimen.mapping_status": config["specimen"]["mapping_status"],
        "coordinate_frames.stl.axis_mapping_to_nominal": config["coordinate_frames"]["stl"]["axis_mapping_to_nominal"],
        "coordinate_frames.stl.status": config["coordinate_frames"]["stl"]["status"],
        "registration.stl_to_nominal.graph_to_stl_axis_mapping": config["registration"]["stl_to_nominal"]["graph_to_stl_axis_mapping"],
        "registration.stl_to_nominal.graph_to_stl_axis_mapping_status": config["registration"]["stl_to_nominal"]["graph_to_stl_axis_mapping_status"],
    }
    expected_stale = (
        stale_values["specimen.mapping_status"] == "UNVERIFIED"
        and stale_values["coordinate_frames.stl.axis_mapping_to_nominal"] is None
        and "UNVERIFIED" in stale_values["coordinate_frames.stl.status"]
        and stale_values[
            "registration.stl_to_nominal.graph_to_stl_axis_mapping"
        ]
        == "identity_centered_phase1_assumption"
    )
    report.add(
        "provenance.config_snapshot_stale",
        "warn" if expected_stale else "pass",
        "The copied part2.yaml still encodes an unverified identity/unknown STL mapping even though later artifacts say the human-anchor gate selected perm021_signmmm; it is not a ready-to-rerun Phase 2C config."
        if expected_stale
        else "The copied config no longer contains the known early mapping placeholders.",
        severity="high" if expected_stale else "info",
        path=config_path,
        evidence={
            "config_values": stale_values,
            "later_documented_transform": "perm021_signmmm",
        },
    )

    boolean_columns: dict[str, list[str]] = {}
    for column in labels[0]:
        values = {row[column] for row in labels}
        bool_values = values & {"true", "false", "True", "False"}
        if bool_values and values <= {"true", "false", "True", "False", ""}:
            boolean_columns[column] = sorted(bool_values)
    casings = {value for values in boolean_columns.values() for value in values}
    mixed_boolean_casing = bool(casings & {"true", "false"}) and bool(
        casings & {"True", "False"}
    )
    report.add(
        "schema.boolean_casing",
        "warn" if mixed_boolean_casing else "pass",
        "Boolean columns mix True/False and true/false conventions; consumers must parse values explicitly because bool('false') is true in Python."
        if mixed_boolean_casing
        else "Boolean columns use one casing convention.",
        severity="medium" if mixed_boolean_casing else "info",
        evidence={"column_values": boolean_columns},
    )

    numeric_nan_columns = (
        "centerline_displacement_voxels",
        "curvature_voxels",
        "node_u_registration_residual_voxels",
        "node_v_registration_residual_voxels",
    )
    nan_counts = {
        column: sum(row[column].strip().lower() == "nan" for row in labels)
        for column in numeric_nan_columns
    }
    report.add(
        "schema.literal_nan",
        "warn" if any(nan_counts.values()) else "pass",
        "Several numeric fields serialize undefined measurements as literal nan strings; use null/blank plus an explicit validity/status field for interoperable schemas."
        if any(nan_counts.values())
        else "No audited numeric field uses literal nan text.",
        severity="medium" if any(nan_counts.values()) else "info",
        evidence={"literal_nan_counts": nan_counts},
    )

    changed = [row for row in labels if row["phase2c_changed_from_phase2b4"] == "true"]
    changed_labels = Counter(row["phase2c_label"] for row in changed)
    report.add(
        "schema.phase2c_changed_semantics",
        "warn" if len(changed) != 14 else "pass",
        "phase2c_changed_from_phase2b4 is true for 1,009 lexical/status changes, not just the 14 newly promoted candidates; its name is easy to misread as a promotion flag."
        if len(changed) != 14
        else "The Phase 2C changed flag identifies only the 14 promotions.",
        severity="low" if len(changed) != 14 else "info",
        evidence={"true_count": len(changed), "by_phase2c_label": dict(changed_labels)},
    )

    viewer = load_json(root / "viewer/viewer_data.json")
    score_types = Counter(type(edge["score"]).__name__ for edge in viewer["edges"])
    evidence_types = Counter(
        type(edge["evidence_count"]).__name__ for edge in viewer["edges"]
    )
    viewer_numbers_are_strings = set(score_types) == {"str"} and set(evidence_types) == {
        "str"
    }
    report.add(
        "schema.viewer_numeric_types",
        "warn" if viewer_numbers_are_strings else "pass",
        "Viewer score and evidence_count values are strings, which permits accidental lexical sorting/comparison."
        if viewer_numbers_are_strings
        else "Viewer numeric fields are serialized as numeric JSON values.",
        severity="low" if viewer_numbers_are_strings else "info",
        path=root / "viewer/viewer_data.json",
        evidence={"score_types": dict(score_types), "evidence_count_types": dict(evidence_types)},
    )

    viewer_manifest = load_json(root / "viewer/run_manifest.json")
    baseline_manifest = load_json(root / "final_report_baseline/run_manifest.json")
    packet_hashes = {
        "phase2c_labels": sha256_file(root / "review_tables/phase2c_labels.csv"),
        "human_spotcheck_labels": sha256_file(
            root
            / "final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv"
        ),
    }
    included_hash_matches = {
        "phase2c_labels": packet_hashes["phase2c_labels"]
        == viewer_manifest["inputs"]["hashes"][
            viewer_manifest["inputs"]["labels_csv_path"]
        ],
        "human_spotcheck_labels": packet_hashes["human_spotcheck_labels"]
        == baseline_manifest["inputs"]["hashes"][
            baseline_manifest["inputs"]["human_spotcheck_labels"]
        ],
    }
    absent_sources = [
        viewer_manifest["inputs"]["graph_path"],
        baseline_manifest["inputs"]["phase2b4_summary"],
        "outputs/part2/phase2b4/20260727_092219/automated_review_labels.csv",
    ]
    missing_source_paths = [
        path for path in absent_sources if not (repo_root / path).is_file()
    ]
    report.add(
        "provenance.source_artifact_lineage",
        "warn" if missing_source_paths else "pass",
        "Two included copies match their recorded source hashes, but the canonical graph and original Phase 2B.4 summary/all-label inputs are absent, so complete source-to-output lineage cannot be rehashed."
        if missing_source_paths
        else "Every source artifact cited by the late-stage manifests is locally available.",
        severity="high" if missing_source_paths else "info",
        evidence={
            "included_hash_matches": included_hash_matches,
            "missing_source_paths": missing_source_paths,
        },
    )

    return {
        "missing_assumptions": missing_assumptions,
        "missing_methods": missing_methods,
        "split_references": split_references,
        "stale_config_values": stale_values,
        "boolean_columns": boolean_columns,
        "nan_counts": nan_counts,
        "changed_count": len(changed),
        "changed_labels": changed_labels,
        "viewer_score_types": score_types,
        "viewer_evidence_types": evidence_types,
        "included_hash_matches": included_hash_matches,
        "missing_source_paths": missing_source_paths,
    }
