"""Aman-only deterministic stage callbacks for one identity-assisted run."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .models import StageContext, StageResult


def _required(config: Mapping[str, Any], key: str) -> Path:
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"config.{key} is required for an executable run")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_callbacks(config: Mapping[str, Any], raw_module: Any) -> dict[str, Any]:
    """Build stage callbacks around the existing Aman MCP implementations."""

    tiff = _required(config, "tiff_filepath")
    registered_json = _required(config, "registered_json_filepath")
    pitch = float(config.get("voxel_pitch_um", 58.1))
    radius = float(config.get("expected_radius_voxels", 3.65))

    def validated(context: StageContext) -> StageResult:
        manifest = _write_json(
            context.artifact_root / context.run_id / "input_manifest.json",
            {
                "tiff_filepath": str(tiff),
                "registered_json_filepath": str(registered_json),
                "tiff_sha256": _sha256(tiff),
                "registered_json_sha256": _sha256(registered_json),
                "coordinate_convention": {"tiff": "ZYX", "json": "XYZ"},
                "voxel_pitch_um": pitch,
                "expected_radius_voxels": radius,
            },
        )
        return StageResult((manifest,), {"inputs_validated": True})

    def registered(context: StageContext) -> StageResult:
        report = _write_json(
            context.artifact_root / context.run_id / "registration_manifest.json",
            {
                "registered_json": str(registered_json),
                "status": "supplied_registered_identity",
                "identity_source": "registered_json",
                "measurement_source": "raw_tiff",
                "registration_validation": "not_recomputed_by_agentic_wrapper",
            },
        )
        return StageResult((report,), {"identity_source": "registered_json"})

    def segmented(context: StageContext) -> StageResult:
        output = context.artifact_root / context.run_id / "otsu_mask.tif"
        status = raw_module.segment_tiff_otsu(str(tiff), str(output))
        if str(status).startswith("Error:"):
            raise RuntimeError(status)
        return StageResult((output,), {"status": str(status)})

    def skeletonized(context: StageContext) -> StageResult:
        mask_tif = context.artifact_root / context.run_id / "otsu_mask.tif"
        mask_npy = context.artifact_root / context.run_id / "otsu_mask.npy"
        skeleton = context.artifact_root / context.run_id / "skeleton.npy"
        status = raw_module.read_tiff(str(mask_tif), str(mask_npy))
        if str(status).startswith("Error:"):
            raise RuntimeError(status)
        status = raw_module.skeletonize(str(mask_npy), str(skeleton))
        if str(status).startswith("Error:"):
            raise RuntimeError(status)
        return StageResult((mask_npy, skeleton), {"status": str(status)})

    def measured(context: StageContext) -> StageResult:
        output = context.artifact_root / context.run_id / "strut_measurements.csv"
        status = raw_module.measure_tiff_struts(
            str(tiff), str(registered_json), str(output), pitch, radius
        )
        if str(status).startswith("Error:"):
            raise RuntimeError(status)
        companions = [
            output,
            output.with_name(output.stem + ".otsu_mask.tif"),
            output.with_name(output.stem + ".otsu_mask.npy"),
            output.with_name(output.stem + ".skeleton.npy"),
            output.with_name(output.stem + ".centerline_labels.npz"),
        ]
        return StageResult(tuple(path for path in companions if path.is_file()), {"status": str(status)})

    def reconciled(context: StageContext) -> StageResult:
        source = context.artifact_root / context.run_id / "strut_measurements.csv"
        with source.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        ids = [row.get("strut_id") for row in rows]
        unique = {value for value in ids if value is not None}
        if len(rows) != 18_468 or len(unique) != len(rows):
            raise ValueError(f"expected 18,468 unique struts, found rows={len(rows)} unique={len(unique)}")
        report = _write_json(
            context.artifact_root / context.run_id / "reconciliation.json",
            {"row_count": len(rows), "unique_strut_ids": len(unique), "status": "reconciled"},
        )
        return StageResult((report,), {"row_count": len(rows)})

    def qa(context: StageContext) -> StageResult:
        source = context.artifact_root / context.run_id / "strut_measurements.csv"
        with source.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        thickness = [float(row["thickness_um_median"]) for row in rows if row.get("thickness_um_median")]
        report = _write_json(
            context.artifact_root / context.run_id / "qa_metrics.json",
            {
                "row_count": len(rows),
                "valid_thickness_count": len(thickness),
                "average_thickness_um": sum(thickness) / len(thickness) if thickness else None,
                "ground_truth_available": False,
                "warning": "Measurements are evidence, not validated ground truth.",
            },
        )
        return StageResult((report,), {"valid_thickness_count": len(thickness)})

    def reported(context: StageContext) -> StageResult:
        report = context.artifact_root / context.run_id / "agentic_report.md"
        report.write_text(
            "# Aman Agentic Lattice Run\n\n"
            "This report was produced by the isolated Aman-only orchestrator. "
            "Registered JSON supplies identity/topology and TIFF supplies measurements.\n",
            encoding="utf-8",
        )
        return StageResult((report,), {"report": str(report)})

    return {
        "validated": validated,
        "registered": registered,
        "segmented": segmented,
        "skeletonized": skeletonized,
        "measured": measured,
        "reconciled": reconciled,
        "qa": qa,
        "reported": reported,
    }
