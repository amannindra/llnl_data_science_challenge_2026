"""Shared visualization colors for Python and browser payloads."""

from __future__ import annotations


NOMINAL_LATTICE_COLOR = "#215290"
NODE_COLOR = "#8FB9E3"
CT_CONTEXT_COLOR = "#B8C0C8"

CANDIDATE_COLORS = {
    "intact": "#2E7D32",
    "missing": "#D81B60",
    "broken": "#FFC107",
    "thin": "#7B2CBF",
    "uncertain": "#E76F00",
}

SEGMENTATION_COLOR = "#00C2D7"
EXPECTED_CENTERLINE_COLOR = "#FFD60A"
OBSERVED_CENTERLINE_COLOR = "#FF2D92"
# Retained for the fixed unit-cell contour artifact.
SKELETON_COLOR = OBSERVED_CENTERLINE_COLOR


def browser_palette() -> dict[str, object]:
    """Return the single color contract consumed by the Three.js component."""

    return {
        "nominal": NOMINAL_LATTICE_COLOR,
        "nodes": NODE_COLOR,
        "ctContext": CT_CONTEXT_COLOR,
        "segmentation": SEGMENTATION_COLOR,
        "expectedCenterline": EXPECTED_CENTERLINE_COLOR,
        "observedCenterline": OBSERVED_CENTERLINE_COLOR,
        "candidates": dict(CANDIDATE_COLORS),
    }
