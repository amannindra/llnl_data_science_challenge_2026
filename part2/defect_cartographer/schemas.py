"""Validated schemas shared by the read-only MCP and agent boundaries."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CandidateLabel(str, Enum):
    """Exploratory candidate labels emitted by the deterministic core."""

    INTACT = "intact"
    MISSING = "missing"
    BROKEN = "broken"
    THIN = "thin"
    UNCERTAIN = "uncertain"


class ArtifactFilter(BaseModel):
    """Bounded filters over the saved per-strut feature table."""

    model_config = ConfigDict(extra="forbid")

    classes: list[CandidateLabel] | None = None
    regions: list[str] | None = None
    height_bands: list[str] | None = None
    orientations: list[str] | None = None
    min_occupancy: float | None = Field(default=None, ge=0.0, le=1.0)
    max_occupancy: float | None = Field(default=None, ge=0.0, le=1.0)
    min_gap_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    max_gap_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    min_diameter_um: float | None = Field(default=None, ge=0.0)
    max_diameter_um: float | None = Field(default=None, ge=0.0)
    min_confidence_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    max_confidence_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    min_x: float | None = None
    max_x: float | None = None
    min_y: float | None = None
    max_y: float | None = None
    min_z: float | None = None
    max_z: float | None = None
    limit: int = Field(default=60, ge=1, le=200)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ArtifactFilter":
        """Reject inverted numeric ranges before they reach pandas."""

        for lower_name, upper_name in (
            ("min_occupancy", "max_occupancy"),
            ("min_gap_fraction", "max_gap_fraction"),
            ("min_diameter_um", "max_diameter_um"),
            ("min_confidence_percent", "max_confidence_percent"),
            ("min_x", "max_x"),
            ("min_y", "max_y"),
            ("min_z", "max_z"),
        ):
            lower = getattr(self, lower_name)
            upper = getattr(self, upper_name)
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{lower_name} cannot exceed {upper_name}")
        return self


class SceneBounds(BaseModel):
    """Optional inclusive spatial bounds in registered CT z,y,x coordinates."""

    model_config = ConfigDict(extra="forbid")

    start_zyx: tuple[float, float, float]
    stop_zyx: tuple[float, float, float]

    @model_validator(mode="after")
    def validate_bounds(self) -> "SceneBounds":
        """Require a positive spatial extent along every registered CT axis."""

        if any(start >= stop for start, stop in zip(self.start_zyx, self.stop_zyx)):
            raise ValueError(
                "Each start_zyx coordinate must be less than its stop_zyx coordinate"
            )
        return self


class ThreeJSSceneRequest(BaseModel):
    """A bounded request describing how the dashboard should display a scene."""

    model_config = ConfigDict(extra="forbid")

    classes: list[CandidateLabel] = Field(
        default_factory=lambda: [
            CandidateLabel.INTACT,
            CandidateLabel.MISSING,
            CandidateLabel.BROKEN,
            CandidateLabel.THIN,
            CandidateLabel.UNCERTAIN,
        ]
    )
    include_nominal_lattice: bool = True
    include_ct_context: bool = True
    selected_strut_id: int | None = Field(default=None, ge=0)
    bounds_zyx: SceneBounds | None = None
    max_overlays: int = Field(default=60, ge=1, le=200)

    @model_validator(mode="after")
    def require_classes(self) -> "ThreeJSSceneRequest":
        """Reject empty or duplicate class filters."""

        if not self.classes:
            raise ValueError("At least one candidate class is required")
        if len(set(self.classes)) != len(self.classes):
            raise ValueError("Candidate classes must not contain duplicates")
        return self


class ThreeJSSceneSpec(BaseModel):
    """Small read-only scene specification returned through MCP."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["scene_spec_ready", "no_matching_overlays"]
    read_only: Literal[True] = True
    viewer_launched: Literal[False] = False
    raw_ct_included: Literal[False] = False
    geometry_included_in_response: Literal[False] = False
    scene_artifact: str
    scene_schema_version: int
    coordinate_order: Literal["zyx"] = "zyx"
    coordinate_mapping: str
    registered_coordinates_include_specimen_tilt: Literal[True] = True
    nominal_strut_count: int = Field(ge=0)
    analyzed_overlay_count: int = Field(ge=0)
    matching_overlay_count: int = Field(ge=0)
    returned_overlay_count: int = Field(ge=0)
    overlay_strut_ids: list[int]
    classes: list[CandidateLabel]
    include_nominal_lattice: bool
    include_ct_context: bool
    selected_strut_id: int | None = None
    bounds_zyx: SceneBounds | None = None
    geometry_delivery: Literal["dashboard_loads_compact_artifact_directly"] = (
        "dashboard_loads_compact_artifact_directly"
    )
    classification_status: Literal["exploratory_candidates_not_validated"] = (
        "exploratory_candidates_not_validated"
    )
    warning: str


class CopilotResponse(BaseModel):
    """Structured response returned by the dashboard coordinator."""

    answer: str
    evidence: list[str] = Field(default_factory=list)
    filter_updates: dict[str, Any] = Field(default_factory=dict)
    selected_strut_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    status: str = "ok"
