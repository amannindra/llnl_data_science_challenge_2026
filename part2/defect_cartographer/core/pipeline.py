"""Reproducible Checkpoint 1 orchestration for the 60-strut sample."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

from .alignment import diagnose_alignment
from .analysis import RuleSettings, analyze_sample
from .config import DEFAULT_CONFIG, REPO_ROOT, DefectConfig
from .geometry import build_strut_table, stratified_sample
from .io import (
    load_graph,
    open_ct_memmap,
    read_json,
    sampled_voxels,
    write_json,
)
from .metrics import pipeline_metrics
from .reporting import plot_spatial_distribution, plot_thickness, render_report
from .scene import save_lattice_scene
from .xray_context import save_xray_context


EXPECTED_TOTAL_STRUTS = 18_468
LEGACY_COLUMNS = {"split", "manual_label", "manual_notes"}


def _portable_path(path: Path) -> str:
    """Return a repository-relative path without leaking a local home path."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _file_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": _portable_path(path),
        "size_bytes": int(stat.st_size),
        "modified_time_ns": int(stat.st_mtime_ns),
    }


def _sample_hash(table: pd.DataFrame) -> str:
    identifiers = ",".join(str(int(value)) for value in table["strut_id"])
    return hashlib.sha256(identifiers.encode("utf-8")).hexdigest()


def _metadata(
    metrics: dict[str, Any],
    table: pd.DataFrame,
    config: DefectConfig,
    rules: RuleSettings,
) -> dict[str, Any]:
    result = dict(metrics)
    result.update(
        {
            "random_seed": config.random_seed,
            "sample_strut_id_sha256": _sample_hash(table),
            "voxel_spacing_um": list(config.voxel_spacing_um),
            "threshold_factors": list(config.threshold_factors),
            "provisional_rules": asdict(rules),
        }
    )
    return result


def run_alignment(config: DefectConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """Run the mandatory alignment stop gate and write traceable evidence."""

    graph = load_graph(config.graph_path)
    volume = open_ct_memmap(config.ct_path)
    result = diagnose_alignment(
        volume,
        graph,
        sampled_voxels(config.ct_path),
        seed=config.random_seed,
        sample_struts=config.alignment_struts,
        search_radius=config.alignment_search_radius_vox,
        voxel_spacing_um=config.voxel_spacing_um,
    )
    payload = result.to_dict()
    payload.update(
        {
            "ct_file": _file_metadata(config.ct_path),
            "graph_file": _file_metadata(config.graph_path),
            "ct_shape": list(volume.shape),
            "ct_dtype": str(volume.dtype),
            "voxel_spacing_um": list(config.voxel_spacing_um),
        }
    )
    write_json(config.alignment_path, payload)
    if not result.reliable:
        raise RuntimeError(
            "Registered JSON-to-CT alignment failed the reliability gate. "
            "Analysis stopped before candidate classification."
        )
    return payload


def build_sample(
    config: DefectConfig,
    graph: dict[str, Any],
    alignment: dict[str, Any],
) -> pd.DataFrame:
    """Build the same deterministic spatial/orientation-stratified sample."""

    residual = np.asarray(alignment["residual_transform"], dtype=float)
    permutation = tuple(int(item) for item in alignment["selected_permutation"])
    all_struts = build_strut_table(graph, permutation, residual)
    if len(all_struts) != EXPECTED_TOTAL_STRUTS:
        raise ValueError(
            f"Expected {EXPECTED_TOTAL_STRUTS:,} graph struts, found {len(all_struts):,}"
        )
    return stratified_sample(
        all_struts,
        sample_size=config.sample_size,
        seed=config.random_seed,
    )


def run_analysis(
    config: DefectConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, Any]]:
    """Measure and classify the sample after a reliable alignment result."""

    alignment = read_json(config.alignment_path)
    if not alignment.get("reliable", False):
        raise RuntimeError("Saved alignment is not reliable; refusing to analyze struts")

    graph = load_graph(config.graph_path)
    sample = build_sample(config, graph, alignment)
    rules = RuleSettings()
    table, thickness_reference = analyze_sample(
        open_ct_memmap(config.ct_path),
        sample,
        base_threshold=float(alignment["threshold_otsu"]),
        threshold_factors=config.threshold_factors,
        voxel_spacing_um=config.voxel_spacing_um,
        search_radius=config.analysis_search_radius_vox,
        design_diameter_um=config.design_diameter_um,
        rules=rules,
    )
    unexpected = LEGACY_COLUMNS.intersection(table.columns)
    if unexpected:
        raise RuntimeError(f"Legacy review columns leaked into output: {sorted(unexpected)}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    temporary = config.sample_path.with_suffix(".csv.tmp")
    table.to_csv(temporary, index=False)
    temporary.replace(config.sample_path)
    write_json(config.output_dir / "thickness_reference.json", thickness_reference)

    metrics = _metadata(pipeline_metrics(table), table, config, rules)
    write_json(config.metrics_path, metrics)
    plot_thickness(
        table,
        config.output_dir / "thickness_histogram.png",
        config.design_diameter_um,
    )
    plot_spatial_distribution(
        table,
        config.output_dir / "spatial_distribution.png",
    )
    return table, thickness_reference, metrics


def run_report(config: DefectConfig = DEFAULT_CONFIG) -> Path:
    """Generate the report solely from deterministic saved artifacts."""

    alignment = read_json(config.alignment_path)
    metrics = read_json(config.metrics_path)
    thickness_reference = read_json(config.output_dir / "thickness_reference.json")
    table = pd.read_csv(config.sample_path)
    report_path = config.output_dir / "defect_cartographer_report.md"
    render_report(report_path, alignment, metrics, table, thickness_reference)
    return report_path


def write_manifest(config: DefectConfig = DEFAULT_CONFIG) -> Path:
    """Record the inputs, configuration, artifacts, and scientific boundary."""

    artifact_names = (
        "alignment.json",
        "sampled_struts.csv",
        "pipeline_metrics.json",
        "thickness_reference.json",
        "thickness_histogram.png",
        "spatial_distribution.png",
        "defect_cartographer_report.md",
        "xray_context.npz",
        "lattice_scene.npz",
    )
    payload = {
        "schema_version": 1,
        "status": "complete",
        "pipeline_scope": "deterministic_60_strut_mvp",
        "candidate_labels_validated": False,
        "ground_truth_available": False,
        "registered_coordinates_include_specimen_tilt": True,
        "config": {
            key: _portable_path(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        "inputs": {
            "ct": _file_metadata(config.ct_path),
            "graph": _file_metadata(config.graph_path),
        },
        "artifacts": {
            name: _file_metadata(config.output_dir / name)
            for name in artifact_names
        },
    }
    path = config.output_dir / "run_manifest.json"
    write_json(path, payload)
    return path


def run_all(config: DefectConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    alignment = run_alignment(config)
    table, _, metrics = run_analysis(config)
    report = run_report(config)
    xray_context = save_xray_context(config.output_dir / "xray_context.npz", config)
    lattice_scene = save_lattice_scene(
        config.output_dir / "lattice_scene.npz", config
    )
    manifest = write_manifest(config)
    return {
        "alignment_reliable": bool(alignment["reliable"]),
        "sample_size": int(len(table)),
        "prediction_counts": metrics["prediction_counts"],
        "report": str(report),
        "xray_context": str(xray_context),
        "lattice_scene": str(lattice_scene),
        "manifest": str(manifest),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("align", "analyze", "report", "all"),
        help="Checkpoint 1 stage to execute",
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_CONFIG.sample_size)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = DefectConfig(sample_size=args.sample_size)
    try:
        if args.command == "align":
            result: Any = run_alignment(config)
        elif args.command == "analyze":
            table, reference, metrics = run_analysis(config)
            result = {
                "sample_size": len(table),
                "thickness_reference": reference,
                "metrics": metrics,
            }
        elif args.command == "report":
            result = {"report": str(run_report(config))}
        else:
            result = run_all(config)
        print(json.dumps(result, indent=2, default=str))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
