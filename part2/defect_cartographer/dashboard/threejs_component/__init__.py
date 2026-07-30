"""Python boundary for the compiled Three.js Streamlit component."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

from ...core.colors import browser_palette
from ...core.scene import load_lattice_scene


BUILD_DIR = Path(__file__).parent / "frontend" / "build"
CANONICAL_LABELS = ("intact", "missing", "broken", "uncertain")
LABEL_ALIASES = {
    "healthy": "intact",
    "intact": "intact",
    "missing": "missing",
    "broken": "broken",
    "thin": "uncertain",
    "uncertain": "uncertain",
    "thick": "uncertain",
    "bent_or_misaligned": "uncertain",
    "not_applicable": "uncertain",
}


@lru_cache(maxsize=1)
def _component_renderer() -> Any:
    scripts = sorted(BUILD_DIR.glob("index-*.js"))
    if len(scripts) != 1:
        raise RuntimeError(
            "Three.js component assets are missing or ambiguous. "
            "Run `npm run build` in the component frontend directory."
        )
    styles = sorted(BUILD_DIR.glob("*.css"))
    css = (
        "/* compiled component styles */\n"
        + styles[0].read_text(encoding="utf-8")
        if len(styles) == 1
        else None
    )
    return st.components.v2.component(
        "lattice_threejs_viewer",
        html='<div class="lattice-viewer-root"></div>',
        css=css,
        js=scripts[0].read_text(encoding="utf-8"),
    )


def _flatten(values: np.ndarray, dtype: type) -> list[Any]:
    return np.asarray(values).reshape(-1).astype(dtype).tolist()


def _scene_geometry_payload(
    scene: dict[str, np.ndarray],
) -> dict[str, Any]:
    raw_label_names = [str(value) for value in scene["label_names"].tolist()]
    raw_codes = np.asarray(scene["analyzed_label_codes"]).reshape(-1)
    canonical_codes = [
        CANONICAL_LABELS.index(
            LABEL_ALIASES.get(raw_label_names[int(code)], "uncertain")
        )
        for code in raw_codes
    ]
    return {
        # Browser schema v3 references analyzed labels by nominal strut ID and
        # intentionally omits duplicate endpoint arrays.
        "schemaVersion": 3,
        "coordinateOrder": str(scene["coordinate_order"]),
        "selectedMapping": str(scene["selected_mapping"]),
        "nominalStrutIds": _flatten(scene["nominal_strut_ids"], int),
        "nominalPositionsZyx": _flatten(scene["nominal_segments_zyx"], float),
        "junctionIds": _flatten(scene.get("junction_ids", np.asarray([])), int),
        "junctionPositionsZyx": _flatten(
            scene.get("junction_positions_zyx", np.empty((0, 3))), float
        ),
        "nominalJunctionIds": _flatten(
            scene.get("nominal_junction_ids", np.empty((0, 2))), int
        ),
        "analyzedStrutIds": _flatten(scene["analyzed_strut_ids"], int),
        "analyzedLabelCodes": canonical_codes,
        "analyzedRawLabelCodes": _flatten(raw_codes, int),
        "labelNames": list(CANONICAL_LABELS),
        "rawLabelNames": raw_label_names,
        "xrayVerticesZyx": _flatten(scene["xray_vertices_zyx"], float),
        "xrayFaces": _flatten(scene["xray_faces"], int),
        "xrayVertexTexture": _flatten(
            scene.get("xray_vertex_texture", np.asarray([])), float
        ),
    }


@lru_cache(maxsize=4)
def scene_payload(scene_path: str) -> dict[str, Any]:
    """Serialize the compact scene into a browser-safe, raw-CT-free payload."""

    path = Path(scene_path)
    scene = load_lattice_scene(scene_path)
    payload = _scene_geometry_payload(scene)
    payload.update(
        {
            "viewerTitle": "Interactive Full-Lattice Inspector (Three.js)",
            "sceneRevision": f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}",
            "palette": browser_palette(),
        }
    )
    return payload


def lattice_threejs_viewer(
    scene_path: Path | str,
    *,
    selected_strut_id: int | None = None,
    slice_evidence: dict[str, Any] | None = None,
    key: str = "lattice-threejs-viewer",
    height: int | str = "content",
) -> Any:
    """Render the registered lattice scene and return component state."""

    renderer = _component_renderer()
    resolved_scene = Path(scene_path).resolve()
    payload = dict(scene_payload(str(resolved_scene)))
    payload["selectedStrutId"] = selected_strut_id
    payload["sliceEvidence"] = slice_evidence
    return renderer(
        key=key,
        data=payload,
        default={"selected_strut_id": selected_strut_id},
        on_selected_strut_id_change=lambda: None,
        height=height,
    )
