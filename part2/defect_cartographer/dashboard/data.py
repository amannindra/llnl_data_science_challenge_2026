"""Read-only dashboard artifact loading and the main-branch adapter.

The deterministic agents write a few different artifact naming conventions as
the workflow evolves.  The dashboard deliberately resolves those conventions
at its boundary instead of changing the agent outputs or duplicating files.
``LATTICE_CT_ARTIFACT_DIR`` can point at another saved run for local review.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..core.config import DEFAULT_CONFIG
from ..core.clustering import clustering_summary
from ..core.io import read_json
from ..core.xray_context import load_xray_context


CANONICAL_LABELS = ("intact", "missing", "broken", "uncertain")
LABEL_ALIASES = {
    "healthy": "intact",
    "intact": "intact",
    "missing": "missing",
    "broken": "broken",
    # Preserve every detailed agent label in ``raw_prediction`` while the
    # current presentation intentionally exposes four stable classes.
    "thin": "uncertain",
    "thick": "uncertain",
    "bent_or_misaligned": "uncertain",
    "uncertain": "uncertain",
    "not_applicable": "uncertain",
}

CSV_NAMES = (
    "full_strut_classification.csv",
    "defect_results.csv",
    "validated_struts.csv",
    "sampled_struts.csv",
)
REPORT_NAMES = ("full_defect_report.md", "defect_cartographer_report.md")
METRICS_NAMES = ("full_pipeline_metrics.json", "pipeline_metrics.json")
ALIGNMENT_NAMES = ("full_alignment.json", "alignment.json")
THICKNESS_NAMES = ("full_thickness_reference.json", "thickness_reference.json")
SCENE_NAMES = ("full_lattice_scene.npz", "lattice_scene.npz")


@dataclass(frozen=True)
class DashboardArtifacts:
    """Saved evidence required by the dashboard."""

    table: pd.DataFrame
    metrics: dict
    alignment: dict
    thickness_reference: dict
    report_markdown: str
    xray_context: dict | None
    sample_dir: Path
    scene_path: Path | None
    clustering: dict


def resolve_artifact_dir(sample_dir: Path | str | None = None) -> Path:
    """Resolve one saved run without changing the repository or agent config."""

    value = sample_dir if sample_dir is not None else os.getenv("LATTICE_CT_ARTIFACT_DIR")
    return Path(value).expanduser() if value else Path(DEFAULT_CONFIG.output_dir)


def _first_file(directory: Path, names: Iterable[str]) -> Path | None:
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    return None


def _resolve_csv(directory: Path) -> Path:
    explicit = os.getenv("LATTICE_CT_RESULTS_CSV")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = directory / path
        if path.is_file():
            return path
        raise FileNotFoundError(f"LATTICE_CT_RESULTS_CSV is missing: {path}")
    path = _first_file(directory, CSV_NAMES)
    if path is not None:
        return path
    candidates = sorted(directory.glob("*.csv"))
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(
        f"No dashboard result CSV found in {directory}; expected one of {CSV_NAMES}"
    )


def _copy_first(table: pd.DataFrame, target: str, alternatives: Iterable[str]) -> None:
    if target in table.columns:
        return
    for source in alternatives:
        if source in table.columns:
            table[target] = table[source]
            return
    table[target] = pd.NA


def _normalise_table(source: pd.DataFrame) -> pd.DataFrame:
    """Adapt main-agent columns while retaining every source column."""

    table = source.copy()
    if "strut_id" not in table.columns:
        raise ValueError("Dashboard result CSV must contain a strut_id column")
    source_label = next(
        (name for name in ("prediction", "defect_type", "label", "classification") if name in table.columns),
        None,
    )
    if source_label is None:
        raise ValueError("Dashboard result CSV must contain a prediction/label column")
    table["automated_prediction"] = table[source_label].astype(str)
    table["raw_prediction"] = table["automated_prediction"]
    table["prediction"] = table["raw_prediction"].map(
        lambda value: LABEL_ALIASES.get(value.strip().lower(), "uncertain")
    )

    for axis in ("z", "y", "x"):
        _copy_first(table, f"start_{axis}", (f"start_{axis}",))
        _copy_first(table, f"end_{axis}", (f"end_{axis}",))
        _copy_first(table, f"mid_{axis}", (f"mid_{axis}",))
    _copy_first(table, "region", ("region",))
    _copy_first(table, "height_band", ("height_band", "height"))
    _copy_first(table, "orientation", ("orientation",))
    _copy_first(table, "sample_order", ("sample_order", "strut_id"))
    _copy_first(table, "occupancy", ("occupancy", "observed_axial_fraction", "material_coverage"))
    if "gap_fraction" not in table.columns:
        gap_source = table.get("longest_unsupported_gap_voxels", pd.Series(index=table.index, dtype=float))
        length_source = table.get("length_voxels", table.get("length_vox", pd.Series(index=table.index, dtype=float)))
        gap = pd.to_numeric(gap_source, errors="coerce")
        length = pd.to_numeric(length_source, errors="coerce")
        table["gap_fraction"] = gap.div(length.where(length != 0))
    _copy_first(table, "alignment_error_vox", ("alignment_error_vox", "p90_centerline_displacement_voxels", "alignment_offset"))
    _copy_first(table, "diameter_median_um", ("diameter_median_um", "thickness_um_median", "diameter_um"))
    _copy_first(table, "thickness_measurement_valid", ("thickness_measurement_valid", "measurement_valid", "tiff_measurement_valid"))
    if "threshold_stability" not in table.columns:
        table["threshold_stability"] = 1.0
    _copy_first(table, "confidence_percent_uncalibrated", ("confidence_percent_uncalibrated", "confidence_percent", "confidence"))
    _copy_first(table, "prediction_reason", ("prediction_reason", "classification_reason", "reason"))
    _copy_first(table, "evidence_focus_zyx", ("evidence_focus_zyx", "focus_zyx"))

    # Streamlit filters should operate on numeric values even when a teammate's
    # CSV contains empty strings or textual review states.
    numeric = (
        "strut_id", "start_z", "start_y", "start_x", "end_z", "end_y", "end_x",
        "mid_z", "mid_y", "mid_x", "occupancy", "gap_fraction",
        "alignment_error_vox", "diameter_median_um", "threshold_stability",
        "confidence_percent_uncalibrated", "sample_order",
    )
    for column in numeric:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table["strut_id"] = table["strut_id"].astype("Int64")
    table["sample_order"] = table["sample_order"].fillna(table["strut_id"]).fillna(0)
    table["region"] = table["region"].fillna("unknown").astype(str)
    table["height_band"] = table["height_band"].fillna("unknown").astype(str)
    table["orientation"] = table["orientation"].fillna("unknown").astype(str)
    table["prediction_reason"] = table["prediction_reason"].fillna(table["raw_prediction"]).astype(str)
    table["thickness_measurement_valid"] = table["thickness_measurement_valid"].fillna(
        table["diameter_median_um"].notna()
    ).astype(bool)
    table["threshold_stability"] = table["threshold_stability"].fillna(0.0)
    table["confidence_percent_uncalibrated"] = table["confidence_percent_uncalibrated"].fillna(0.0)
    if table["strut_id"].isna().any() or table["strut_id"].duplicated().any():
        raise ValueError("Dashboard result CSV must contain unique numeric strut IDs")
    return table.sort_values("sample_order").reset_index(drop=True)


def _read_optional(directory: Path, names: Iterable[str]) -> dict:
    path = _first_file(directory, names)
    return read_json(path) if path is not None else {}


def _normalise_metrics(source: dict, table: pd.DataFrame) -> dict:
    counts = table["prediction"].value_counts().to_dict()
    valid = table.loc[table["thickness_measurement_valid"], "diameter_median_um"].dropna()
    known = table["prediction"].isin(("intact", "missing", "broken"))
    return {
        **source,
        "sample_size": int(source.get("sample_size", len(table))),
        "classification_coverage": float(source.get("classification_coverage", known.mean())),
        "prediction_counts": {label: int(counts.get(label, 0)) for label in CANONICAL_LABELS},
        "median_diameter_um": float(source.get("median_diameter_um", valid.median())) if not valid.empty else None,
        "valid_thickness_measurement_count": int(source.get("valid_thickness_measurement_count", len(valid))),
        "uncertain_fraction": float(source.get("uncertain_fraction", (~known).mean())),
    }


def load_dashboard_artifacts(
    sample_dir: Path | str | None = None,
) -> DashboardArtifacts:
    """Load saved artifacts only; raw CT is never loaded by this adapter."""

    directory = resolve_artifact_dir(sample_dir)
    table = _normalise_table(pd.read_csv(_resolve_csv(directory)))
    report_path = _first_file(directory, REPORT_NAMES)
    scene_path = _first_file(directory, SCENE_NAMES)
    return DashboardArtifacts(
        table=table,
        metrics=_normalise_metrics(_read_optional(directory, METRICS_NAMES), table),
        alignment=_read_optional(directory, ALIGNMENT_NAMES),
        thickness_reference=_read_optional(directory, THICKNESS_NAMES),
        report_markdown=(
            report_path.read_text(encoding="utf-8")
            if report_path is not None
            else "No saved methodology report was supplied for this run."
        ),
        xray_context=(
            load_xray_context(directory / "xray_context.npz")
            if (directory / "xray_context.npz").is_file()
            else None
        ),
        sample_dir=directory,
        scene_path=scene_path,
        clustering=clustering_summary(directory),
    )


def filter_table(
    table: pd.DataFrame,
    *,
    classes: Iterable[str] | None = None,
    regions: Iterable[str] | None = None,
    height_bands: Iterable[str] | None = None,
    orientations: Iterable[str] | None = None,
    occupancy_range: tuple[float, float] = (0.0, 1.0),
    gap_range: tuple[float, float] = (0.0, 1.0),
) -> pd.DataFrame:
    """Apply deterministic UI filters without mutating the source table."""

    selected = table.copy()
    for column, values in (
        ("prediction", classes),
        ("region", regions),
        ("height_band", height_bands),
        ("orientation", orientations),
    ):
        normalized = list(values or [])
        if normalized:
            selected = selected[selected[column].isin(normalized)]
    selected = selected[selected["occupancy"].between(*occupancy_range, inclusive="both")]
    selected = selected[selected["gap_fraction"].between(*gap_range, inclusive="both")]
    return selected.sort_values("sample_order").reset_index(drop=True)
