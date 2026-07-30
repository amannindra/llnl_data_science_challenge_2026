"""Python boundary for the compiled Three.js Streamlit component."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import streamlit as st

from ...core.scene import load_lattice_scene
from ...core.unit_cell import load_unit_cell_scene


BUILD_DIR = Path(__file__).parent / "frontend" / "build"


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


def _scene_geometry_payload(scene: dict[str, np.ndarray]) -> dict[str, Any]:
    return {
        "schemaVersion": int(scene["schema_version"]),
        "coordinateOrder": str(scene["coordinate_order"]),
        "selectedMapping": str(scene["selected_mapping"]),
        "nominalStrutIds": _flatten(scene["nominal_strut_ids"], int),
        "nominalPositionsZyx": _flatten(scene["nominal_segments_zyx"], float),
        "analyzedStrutIds": _flatten(scene["analyzed_strut_ids"], int),
        "analyzedPositionsZyx": _flatten(scene["analyzed_segments_zyx"], float),
        "analyzedLabelCodes": _flatten(scene["analyzed_label_codes"], int),
        "labelNames": [str(value) for value in scene["label_names"].tolist()],
        "xrayVerticesZyx": _flatten(scene["xray_vertices_zyx"], float),
        "xrayFaces": _flatten(scene["xray_faces"], int),
    }


@lru_cache(maxsize=4)
def scene_payload(scene_path: str) -> dict[str, Any]:
    """Serialize the compact scene into a browser-safe, raw-CT-free payload."""

    scene = load_lattice_scene(scene_path)
    payload = _scene_geometry_payload(scene)
    payload.update(
        {
            "sceneKind": "lattice",
            "viewerTitle": "Interactive Full-Lattice Inspector (Three.js)",
        }
    )
    return payload


@lru_cache(maxsize=2)
def unit_cell_scene_payload(scene_path: str) -> dict[str, Any]:
    """Serialize one approved derived unit-cell scene without CT voxels."""

    scene = load_unit_cell_scene(scene_path)
    label = str(scene["target_label"])
    payload = _scene_geometry_payload(scene)
    payload.update(
        {
            "sceneKind": "unit_cell",
            "viewerTitle": "Interactive Unit Cell Inspector (Three.js)",
            "cellId": int(scene["cell_id"]),
            "targetStrutId": int(scene["target_strut_id"]),
            "targetLabel": label,
            "focusZyx": _flatten(scene["focus_zyx"], float),
        }
    )
    return payload


def lattice_threejs_viewer(
    scene_path: Path | str,
    *,
    key: str = "lattice-threejs-viewer",
    height: int | Literal["content", "stretch"] = "content",
) -> Any:
    """Render the registered lattice scene and return component state."""

    # "content" lets the wrapper grow with the viewport-relative canvas height in
    # styles.css; a fixed pixel height would clip it on tall displays.
    renderer = _component_renderer()
    current_state = st.session_state.get(key, {})
    selected_strut_id = (
        current_state.get("selected_strut_id")
        if isinstance(current_state, dict)
        else None
    )
    payload = dict(scene_payload(str(Path(scene_path).resolve())))
    payload["selectedStrutId"] = selected_strut_id
    return renderer(
        key=key,
        data=payload,
        default={"selected_strut_id": None},
        on_selected_strut_id_change=lambda: None,
        height=height,
    )


def unit_cell_threejs_viewer(
    scene_path: Path | str,
    *,
    key: str,
    height: int = 680,
) -> Any:
    """Render one fixed derived unit-cell scene and return component state."""

    renderer = _component_renderer()
    payload = dict(unit_cell_scene_payload(str(Path(scene_path).resolve())))
    target_id = int(payload["targetStrutId"])
    payload["selectedStrutId"] = target_id
    return renderer(
        key=key,
        data=payload,
        default={"selected_strut_id": target_id},
        on_selected_strut_id_change=lambda: None,
        height=height,
    )
