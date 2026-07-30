"""Import the validated full-lattice defect classification into dashboard artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, DefectConfig, REPO_ROOT
from .geometry import build_strut_table
from .io import load_graph, read_json, write_json
from .scene import build_lattice_scene


EXPECTED_STRUTS = 18_468
CLASSIFICATION_LABELS = (
    "healthy",
    "missing",
    "broken",
    "thin",
    "thick",
    "bent_or_misaligned",
    "uncertain",
    "not_applicable",
)


def _source_path(value: Path, fallback: Path) -> Path:
    path = value if value.is_absolute() else REPO_ROOT / value
    return path if path.is_file() else fallback


def _confidence(status: pd.Series) -> pd.Series:
    return status.map(
        {"accepted": 100.0, "confirmed": 75.0, "review": 30.0, "excluded": 0.0}
    ).fillna(0.0)


def build_full_results_table(
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    classification_path: Path | str | None = None,
    measurements_path: Path | str | None = None,
    metrology_path: Path | str | None = None,
) -> pd.DataFrame:
    """Join classification, registered geometry, and measurement evidence."""

    classification_file = _source_path(
        Path(classification_path or config.classification_path),
        config.dashboard_table_path,
    )
    if not classification_file.is_file():
        raise FileNotFoundError(f"Full classification CSV is missing: {classification_file}")
    classification = pd.read_csv(classification_file)
    if len(classification) != EXPECTED_STRUTS:
        raise ValueError(
            f"Expected {EXPECTED_STRUTS:,} classifications, found {len(classification):,}"
        )
    if classification["strut_id"].duplicated().any():
        raise ValueError("Full classification contains duplicate strut IDs")
    invalid = sorted(set(classification["defect_type"].astype(str)) - set(CLASSIFICATION_LABELS))
    if invalid:
        raise ValueError(f"Unsupported full classification labels: {invalid}")

    graph = load_graph(config.graph_path)
    alignment = read_json(config.alignment_path)
    permutation = tuple(int(value) for value in alignment["selected_permutation"])
    residual = np.asarray(alignment["residual_transform"], dtype=np.float64)
    geometry = build_strut_table(graph, permutation, residual)

    merged = geometry.merge(classification, on="strut_id", how="left", validate="one_to_one")
    if merged["defect_type"].isna().any():
        raise ValueError("Some registered struts have no classification record")

    measurement_file = Path(measurements_path or config.measurements_path)
    measurement_file = _source_path(measurement_file, Path(""))
    if measurement_file.is_file():
        measurements = pd.read_csv(measurement_file)
        measurement_columns = [
            "strut_id", "measurement_valid", "thickness_um_median",
            "diameter_voxels_median", "diameter_voxels_p10", "diameter_voxels_p90",
        ]
        measurements = measurements[[column for column in measurement_columns if column in measurements]]
        measurements = measurements.rename(columns={"measurement_valid": "tiff_measurement_valid"})
        merged = merged.merge(measurements, on="strut_id", how="left", validate="one_to_one")
    else:
        merged["tiff_measurement_valid"] = False

    metrology_file = Path(metrology_path or config.metrology_path)
    metrology_file = _source_path(metrology_file, Path(""))
    if metrology_file.is_file():
        payload = json.loads(metrology_file.read_text(encoding="utf-8"))
        records = pd.DataFrame.from_records(payload.get("struts", []))
        if not records.empty and "id" in records:
            fields = [
                "id", "length_voxels", "longest_unsupported_gap_voxels",
                "p90_centerline_displacement_voxels", "expected_radius_median_voxels",
            ]
            records = records[[field for field in fields if field in records]].rename(
                columns={"id": "strut_id"}
            )
            merged = merged.drop(
                columns=[
                    "length_voxels", "longest_unsupported_gap_voxels",
                    "p90_centerline_displacement_voxels", "expected_radius_median_voxels",
                ],
                errors="ignore",
            ).merge(records, on="strut_id", how="left", validate="one_to_one")

    merged["prediction"] = merged["defect_type"].astype(str)
    merged["gap_fraction"] = (
        pd.to_numeric(merged["longest_unsupported_gap_voxels"], errors="coerce")
        / pd.to_numeric(merged["length_voxels"], errors="coerce")
    ).clip(0.0, 1.0)
    merged["occupancy"] = pd.to_numeric(merged["observed_axial_fraction"], errors="coerce")
    merged["alignment_error_vox"] = pd.to_numeric(
        merged["p90_centerline_displacement_voxels"], errors="coerce"
    )
    merged["diameter_median_um"] = pd.to_numeric(
        merged.get("thickness_um_median", pd.Series(np.nan, index=merged.index)),
        errors="coerce",
    )
    merged["thickness_measurement_valid"] = (
        merged["tiff_measurement_valid"].fillna(False).astype(bool)
        & merged["diameter_median_um"].notna()
    )
    merged["threshold_stability"] = np.where(
        merged["tiff_measurement_valid"].fillna(False), 1.0, 0.0
    )
    merged["confidence_percent_uncalibrated"] = _confidence(
        merged["classification_status"].astype(str)
    )
    merged["prediction_reason"] = merged["classification_reason"].astype(str)
    merged["sample_order"] = np.arange(len(merged), dtype=np.int64)
    return merged.sort_values("sample_order").reset_index(drop=True)


def build_full_dashboard_artifacts(config: DefectConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    """Write the full table, metrics, report, and compact Three.js scene."""

    table = build_full_results_table(config)
    output = config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.dashboard_table_path, index=False)

    counts = table["prediction"].value_counts().reindex(CLASSIFICATION_LABELS, fill_value=0)
    valid_diameters = table.loc[table["thickness_measurement_valid"], "diameter_median_um"]
    thickness_reference = {
        "thin_candidate_cutoff_um": float(valid_diameters.quantile(0.10)) if len(valid_diameters) else None,
        "design_reference_um_unconfirmed": float(config.design_diameter_um),
        "valid_thickness_measurement_count": int(len(valid_diameters)),
        "median_um": float(valid_diameters.median()) if len(valid_diameters) else None,
    }
    write_json(config.dashboard_thickness_reference_path, thickness_reference)
    metrics = {
        "sample_size": int(len(table)),
        "expected_total_struts": EXPECTED_STRUTS,
        "prediction_counts": {str(key): int(value) for key, value in counts.items()},
        "classification_coverage": float(
            (~table["prediction"].isin(["uncertain", "bent_or_misaligned", "not_applicable"])).mean()
        ),
        "uncertain_fraction": float((table["prediction"] == "uncertain").mean()),
        "valid_thickness_measurement_count": int(table["thickness_measurement_valid"].sum()),
        "median_diameter_um": thickness_reference["median_um"],
        "evaluation_scope": "full_18_468_strut_automated_classification",
        "ground_truth_available": False,
        "warning": "Labels are automated evidence classifications and include review states; they are not validated ground truth.",
        "source_classification_sha256": hashlib.sha256(
            Path(config.classification_path if config.classification_path.is_file() else config.dashboard_table_path).read_bytes()
        ).hexdigest(),
    }
    write_json(config.dashboard_metrics_path, metrics)
    write_json(config.dashboard_alignment_path, read_json(config.alignment_path))
    report = (
        "# Full-lattice CT defect classification\n\n"
        f"The dashboard displays all **{len(table):,}** registered expected struts.\n\n"
        "## Alignment evidence\n\n"
        "The registered JSON geometry is mapped into CT array coordinates using the saved alignment "
        "artifact. Nominal centerlines and the native-TIFF measurement joins retain the specimen tilt.\n\n"
        "## How the prototype detects defect candidates\n\n"
        "This dashboard consumes deterministic saved measurements from the automated native-TIFF "
        "metrology pipeline; it does not re-threshold the raw TIFF in the browser.\n\n"
        "### Feature definitions\n\n"
        "Occupancy is observed axial support. The gap fraction is the longest unsupported centerline "
        "gap divided by expected length. Diameter and radial deviation come from valid cross-section "
        "measurements.\n\n"
        "### Provisional classification rules\n\n"
        "Missing indicates low axial support with a large unsupported gap. Broken indicates a disconnected "
        "internal gap with more remaining support. Thin and thick are signed radial deviations beyond the "
        "effective tolerance. Bent-or-misaligned and uncertain remain review states. Healthy means all "
        "available checks were within declared tolerances.\n\n"
        "### What “confidence” means here\n\n"
        "Displayed confidence is an uncalibrated rule-strength/status score, not a probability.\n\n"
        "## Thickness\n\n"
        "Thickness statistics are reported only for rows with valid measurements and are not ground truth.\n\n"
        "## Limitations and next decision\n\n"
        "The labels are automated evidence classifications, not validated manufacturing defects. Anchor "
        "independent validation is recommended for ambiguous missing-versus-broken "
        "and bent-versus-registration decisions.\n"
    )
    config.dashboard_report_path.write_text(report, encoding="utf-8")

    scene = build_lattice_scene(config, sample_table=table)
    np.savez_compressed(config.dashboard_scene_path, **scene)
    return {"table": str(config.dashboard_table_path), "scene": str(config.dashboard_scene_path), "metrics": metrics}


if __name__ == "__main__":
    print(json.dumps(build_full_dashboard_artifacts(), indent=2, default=str))
