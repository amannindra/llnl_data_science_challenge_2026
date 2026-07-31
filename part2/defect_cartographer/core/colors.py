"""Shared visualization colors for Python and browser payloads."""

from __future__ import annotations


NOMINAL_LATTICE_COLOR = "#FFD60A"
NODE_COLOR = "#FFE66D"
CT_CONTEXT_COLOR = "#5A5A5F"

CANDIDATE_COLORS = {
    "intact": "#FFD60A",
    "missing": "#FF453A",
    "broken": "#0A84FF",
    "uncertain": "#30D158",
}

SEGMENTATION_COLOR = "#00C2D7"
EXPECTED_CENTERLINE_COLOR = "#FFD60A"
OBSERVED_CENTERLINE_COLOR = "#FF2D92"
# Retained for bounded CT evidence overlays.
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
