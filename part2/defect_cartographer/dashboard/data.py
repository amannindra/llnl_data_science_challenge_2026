"""Read-only dashboard data loading and filtering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..core.config import DEFAULT_CONFIG
from ..core.io import read_json
from ..core.xray_context import load_xray_context
from ..service import REQUIRED_COLUMNS


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


def load_dashboard_artifacts(
    sample_dir: Path | str = DEFAULT_CONFIG.output_dir,
) -> DashboardArtifacts:
    """Load and validate only saved sample artifacts; never load raw CT data."""

    directory = Path(sample_dir)
    table_path = directory / "full_strut_classification.csv"
    report_path = directory / "full_defect_report.md"
    if not table_path.is_file():
        raise FileNotFoundError(f"Dashboard table is missing: {table_path}")
    if not report_path.is_file():
        raise FileNotFoundError(f"Dashboard report is missing: {report_path}")
    table = pd.read_csv(table_path)
    missing = REQUIRED_COLUMNS.difference(table.columns)
    if missing:
        raise ValueError(f"Dashboard table is missing columns: {sorted(missing)}")
    return DashboardArtifacts(
        table=table,
        metrics=read_json(directory / "full_pipeline_metrics.json"),
        alignment=read_json(directory / "full_alignment.json"),
        thickness_reference=read_json(directory / "full_thickness_reference.json"),
        report_markdown=report_path.read_text(encoding="utf-8"),
        xray_context=(
            load_xray_context(directory / "xray_context.npz")
            if (directory / "xray_context.npz").is_file()
            else None
        ),
        sample_dir=directory,
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
    selected = selected[
        selected["occupancy"].between(*occupancy_range, inclusive="both")
    ]
    selected = selected[
        selected["gap_fraction"].between(*gap_range, inclusive="both")
    ]
    return selected.sort_values("sample_order").reset_index(drop=True)
