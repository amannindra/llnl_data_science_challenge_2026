"""Read-only access to deterministic lattice CT artifacts.

This service is the single boundary used by both FastMCP and the agent tools.
It never reads raw CT voxel values, changes candidate labels, or writes files.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .core.config import DEFAULT_CONFIG
from .core.clustering import clustering_record, clustering_summary
from .core.io import read_json
from .core.scene import load_lattice_scene
from .schemas import (
    ArtifactFilter,
    CandidateLabel,
    ThreeJSSceneRequest,
    ThreeJSSceneSpec,
)


REQUIRED_COLUMNS = {
    "strut_id",
    "start_z",
    "start_y",
    "start_x",
    "end_z",
    "end_y",
    "end_x",
    "mid_z",
    "mid_y",
    "mid_x",
    "region",
    "height_band",
    "orientation",
    "occupancy",
    "gap_fraction",
    "alignment_error_vox",
    "diameter_median_um",
    "threshold_stability",
    "prediction",
    "confidence_percent_uncalibrated",
    "prediction_reason",
}

ALLOWED_GROUPS = {"prediction", "region", "height_band", "orientation"}
ALLOWED_METRICS = {
    "count",
    "occupancy",
    "gap_fraction",
    "alignment_error_vox",
    "diameter_median_um",
    "confidence_percent_uncalibrated",
    "threshold_stability",
}


def _json_safe(value: Any) -> Any:
    """Convert pandas/NumPy values into strict JSON-compatible values."""

    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class ArtifactService:
    """Validated, bounded queries over one saved deterministic sample run."""

    def __init__(self, sample_dir: Path | str = DEFAULT_CONFIG.output_dir) -> None:
        self.sample_dir = Path(sample_dir)

    @property
    def table_path(self) -> Path:
        return self.sample_dir / "full_strut_classification.csv"

    def _table(self) -> pd.DataFrame:
        if not self.table_path.is_file():
            raise FileNotFoundError(f"Required sample table is missing: {self.table_path}")
        table = pd.read_csv(self.table_path)
        missing = REQUIRED_COLUMNS.difference(table.columns)
        if missing:
            raise ValueError(f"Sample table is missing columns: {sorted(missing)}")
        invalid = set(table["prediction"].dropna().unique()).difference(
            label.value for label in CandidateLabel
        )
        if invalid:
            raise ValueError(f"Sample table contains unsupported labels: {sorted(invalid)}")
        return table

    def _artifact_json(self, name: str) -> dict[str, Any]:
        return read_json(self.sample_dir / name)

    @staticmethod
    def _apply_filters(table: pd.DataFrame, filters: ArtifactFilter) -> pd.DataFrame:
        selected = table
        categorical = (
            ("prediction", filters.classes),
            ("region", filters.regions),
            ("height_band", filters.height_bands),
            ("orientation", filters.orientations),
        )
        for column, values in categorical:
            if values:
                normalized = [
                    value.value if isinstance(value, CandidateLabel) else str(value)
                    for value in values
                ]
                selected = selected[selected[column].isin(normalized)]

        numeric = (
            ("occupancy", filters.min_occupancy, filters.max_occupancy),
            ("gap_fraction", filters.min_gap_fraction, filters.max_gap_fraction),
            ("diameter_median_um", filters.min_diameter_um, filters.max_diameter_um),
            (
                "confidence_percent_uncalibrated",
                filters.min_confidence_percent,
                filters.max_confidence_percent,
            ),
            ("mid_x", filters.min_x, filters.max_x),
            ("mid_y", filters.min_y, filters.max_y),
            ("mid_z", filters.min_z, filters.max_z),
        )
        for column, lower, upper in numeric:
            if lower is not None:
                selected = selected[selected[column] >= lower]
            if upper is not None:
                selected = selected[selected[column] <= upper]
        return selected

    def get_pipeline_summary(self) -> dict[str, Any]:
        """Return aggregate evidence without exposing raw CT or local paths."""

        metrics = self._artifact_json("full_pipeline_metrics.json")
        alignment = self._artifact_json("full_alignment.json")
        table = self._table()
        return _json_safe(
            {
                "scope": "full_18_468_strut_automated_classification",
                "sample_size": len(table),
                "candidate_counts": table["prediction"].value_counts().to_dict(),
                "classification_coverage": metrics.get("classification_coverage"),
                "uncertain_fraction": metrics.get("uncertain_fraction"),
                "median_threshold_stability": metrics.get("median_threshold_stability"),
                "valid_thickness_measurement_count": metrics.get(
                    "valid_thickness_measurement_count"
                ),
                "median_diameter_um": metrics.get("median_diameter_um"),
                "alignment": {
                    "reliable": alignment.get("reliable"),
                    "selected_mapping": alignment.get("selected_mapping"),
                    "registered_coordinates_include_specimen_tilt": True,
                    "residual_correction_applied": alignment.get(
                        "residual_correction_applied"
                    ),
                    "material_found_fraction": alignment.get("material_found_fraction"),
                    "median_material_distance_vox": alignment.get(
                        "median_material_distance_vox"
                    ),
                    "p90_material_distance_vox": alignment.get(
                        "p90_material_distance_vox"
                    ),
                },
                "clustering": clustering_summary(self.sample_dir),
                "warnings": [
                    "Candidate labels are exploratory and have not been validated.",
                    "Labels include automated review states and are not validated ground truth.",
                    "No defect ground truth exists; accuracy, precision, recall, and F1 are unavailable.",
                    "Confidence values are uncalibrated rule-strength scores, not probabilities.",
                ],
            }
        )

    def get_strut_details(self, strut_id: int) -> dict[str, Any]:
        """Return the saved measurements for exactly one sampled strut."""

        table = self._table()
        rows = table.loc[table["strut_id"] == int(strut_id)]
        if rows.empty:
            raise ValueError(
                f"Strut {strut_id} is not present in the full classified lattice"
            )
        if len(rows) != 1:
            raise ValueError(f"Strut {strut_id} appears more than once")
        record = _json_safe(rows.iloc[0].to_dict())
        return {
            "record": record,
            "clustering": _json_safe(
                clustering_record(self.sample_dir, int(strut_id))
            ),
            "classification_status": "exploratory_candidate_not_validated",
            "confidence_interpretation": (
                "Uncalibrated rule strength; not a correctness probability."
            ),
        }

    def filter_defect_candidates(
        self, filters: ArtifactFilter | dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Filter saved rows and cap the response at 200 records."""

        query = (
            filters
            if isinstance(filters, ArtifactFilter)
            else ArtifactFilter.model_validate(filters or {})
        )
        table = self._apply_filters(self._table(), query)
        records = table.sort_values("sample_order").head(query.limit)
        return _json_safe(
            {
                "matching_count": len(table),
                "returned_count": len(records),
                "limit": query.limit,
                "filters": query.model_dump(mode="json"),
                "records": records.to_dict(orient="records"),
                "warning": (
                    "Results are automated evidence classifications; review states are not validated defects."
                ),
            }
        )

    def compare_defect_groups(
        self,
        group_by: str = "prediction",
        metric: str = "count",
        filters: ArtifactFilter | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compare an allow-listed saved metric across categorical groups."""

        if group_by not in ALLOWED_GROUPS:
            raise ValueError(f"group_by must be one of {sorted(ALLOWED_GROUPS)}")
        if metric not in ALLOWED_METRICS:
            raise ValueError(f"metric must be one of {sorted(ALLOWED_METRICS)}")
        query = (
            filters
            if isinstance(filters, ArtifactFilter)
            else ArtifactFilter.model_validate(filters or {})
        )
        table = self._apply_filters(self._table(), query)
        rows: list[dict[str, Any]] = []
        denominator = len(table)
        for group_name, group in table.groupby(group_by, dropna=False):
            row: dict[str, Any] = {
                "group": str(group_name),
                "count": len(group),
                "sample_fraction": len(group) / denominator if denominator else None,
            }
            if metric != "count":
                values = pd.to_numeric(group[metric], errors="coerce").dropna()
                row.update(
                    {
                        "metric": metric,
                        "mean": values.mean() if not values.empty else None,
                        "median": values.median() if not values.empty else None,
                        "minimum": values.min() if not values.empty else None,
                        "maximum": values.max() if not values.empty else None,
                    }
                )
            rows.append(row)
        return _json_safe(
            {
                "group_by": group_by,
                "metric": metric,
                "filtered_sample_size": denominator,
                "groups": sorted(rows, key=lambda item: item["group"]),
                "warning": "Group fractions describe only the saved exploratory sample.",
            }
        )

    def get_methodology(self, section: str = "overview") -> dict[str, Any]:
        """Return a bounded section of the generated methodology report."""

        report_path = self.sample_dir / "full_defect_report.md"
        if not report_path.is_file():
            raise FileNotFoundError(f"Required methodology report is missing: {report_path}")
        report = report_path.read_text(encoding="utf-8")
        headings = {
            "overview": "# Full-lattice CT defect classification",
            "alignment": "## Alignment evidence",
            "detection": "## How the prototype detects defect candidates",
            "features": "### Feature definitions",
            "rules": "### Provisional classification rules",
            "confidence": "### What “confidence” means here",
            "thickness": "## Thickness",
            "limitations": "## Limitations and next decision",
        }
        if section == "full":
            excerpt = report[:12_000]
        else:
            if section not in headings:
                raise ValueError(
                    f"section must be one of {sorted([*headings, 'full'])}"
                )
            excerpt = self._extract_heading(report, headings[section])
        return {
            "section": section,
            "markdown": excerpt[:12_000],
            "classification_status": "exploratory_candidates_not_validated",
        }

    @staticmethod
    def _extract_heading(report: str, heading: str) -> str:
        start = report.find(heading)
        if start < 0:
            raise ValueError(f"Methodology heading not found: {heading}")
        level = len(heading) - len(heading.lstrip("#"))
        search_from = start + len(heading)
        candidates: list[int] = []
        for index, line in enumerate(report[search_from:].splitlines(keepends=True)):
            if line.startswith("#"):
                next_level = len(line) - len(line.lstrip("#"))
                if next_level <= level:
                    offset = sum(
                        len(item)
                        for item in report[search_from:].splitlines(keepends=True)[:index]
                    )
                    candidates.append(search_from + offset)
                    break
        end = candidates[0] if candidates else len(report)
        return report[start:end].strip()

    def prepare_threejs_scene(
        self, request: ThreeJSSceneRequest | dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build a small read-only browser scene spec without returning geometry."""

        query = (
            request
            if isinstance(request, ThreeJSSceneRequest)
            else ThreeJSSceneRequest.model_validate(request or {})
        )
        filter_kwargs: dict[str, Any] = {
            "classes": query.classes,
            "limit": query.max_overlays,
        }
        if query.bounds_zyx is not None:
            lower = query.bounds_zyx.start_zyx
            upper = query.bounds_zyx.stop_zyx
            filter_kwargs.update(
                {
                    "min_z": lower[0],
                    "min_y": lower[1],
                    "min_x": lower[2],
                    "max_z": upper[0],
                    "max_y": upper[1],
                    "max_x": upper[2],
                }
            )

        table = self._apply_filters(self._table(), ArtifactFilter(**filter_kwargs))
        if query.selected_strut_id is not None:
            selected = table.loc[table["strut_id"] == query.selected_strut_id]
            if selected.empty:
                raise ValueError(
                    f"Selected strut {query.selected_strut_id} is not present in "
                    "the requested class and spatial filters"
                )

        returned = table.sort_values("sample_order").head(query.max_overlays)
        scene_path = self.sample_dir / "full_lattice_scene.npz"
        if not scene_path.is_file():
            raise FileNotFoundError(f"Required browser scene is missing: {scene_path}")
        scene = load_lattice_scene(scene_path)

        scene_mapping = str(scene["selected_mapping"])
        alignment_mapping = str(
            self._artifact_json("full_alignment.json").get("selected_mapping")
        )
        if scene_mapping != alignment_mapping:
            raise ValueError(
                "Browser scene coordinate mapping does not match saved alignment"
            )

        spec = ThreeJSSceneSpec(
            status=(
                "scene_spec_ready" if not returned.empty else "no_matching_overlays"
            ),
            scene_artifact=scene_path.name,
            scene_schema_version=int(scene["schema_version"]),
            coordinate_mapping=scene_mapping,
            nominal_strut_count=len(scene["nominal_strut_ids"]),
            analyzed_overlay_count=len(scene["analyzed_strut_ids"]),
            matching_overlay_count=len(table),
            returned_overlay_count=len(returned),
            overlay_strut_ids=[
                int(value) for value in returned["strut_id"].tolist()
            ],
            classes=query.classes,
            include_nominal_lattice=query.include_nominal_lattice,
            include_ct_context=query.include_ct_context,
            selected_strut_id=query.selected_strut_id,
            bounds_zyx=query.bounds_zyx,
            warning=(
                "Candidate labels are exploratory and unvalidated. The dashboard "
                "loads compact geometry directly from the named artifact; MCP returns "
                "only bounded filters and IDs, never raw CT voxels or geometry arrays."
            ),
        )
        return spec.model_dump(mode="json")


DEFAULT_SERVICE = ArtifactService()
