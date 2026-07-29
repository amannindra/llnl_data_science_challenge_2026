"""Python boundary for the compiled Three.js Streamlit component."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

from ...core.colors import browser_palette
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
        "junctionIds": _flatten(scene.get("junction_ids", np.asarray([])), int),
        "junctionPositionsZyx": _flatten(
            scene.get("junction_positions_zyx", np.empty((0, 3))), float
        ),
        "nominalJunctionIds": _flatten(
            scene.get("nominal_junction_ids", np.empty((0, 2))), int
        ),
        "analyzedStrutIds": _flatten(scene["analyzed_strut_ids"], int),
        "analyzedPositionsZyx": _flatten(scene["analyzed_segments_zyx"], float),
        "analyzedLabelCodes": _flatten(scene["analyzed_label_codes"], int),
        "labelNames": [str(value) for value in scene["label_names"].tolist()],
        "xrayVerticesZyx": _flatten(scene["xray_vertices_zyx"], float),
        "xrayFaces": _flatten(scene["xray_faces"], int),
        "xrayVertexTexture": _flatten(
            scene.get("xray_vertex_texture", np.asarray([])), float
        ),
    }


@lru_cache(maxsize=4)
def scene_payload(scene_path: str) -> dict[str, Any]:
    """Serialize the compact scene into a browser-safe, raw-CT-free payload."""

    scene = load_lattice_scene(scene_path)
    payload = _scene_geometry_payload(scene)
    path = Path(scene_path)
    payload.update(
        {
            "sceneKind": "lattice",
            "viewerTitle": "Interactive Full-Lattice Inspector (Three.js)",
            "sceneRevision": f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}",
            "palette": browser_palette(),
        }
    )
    return payload


@lru_cache(maxsize=2)
def unit_cell_scene_payload(scene_path: str) -> dict[str, Any]:
    """Serialize one approved derived unit-cell scene without CT voxels."""

    scene = load_unit_cell_scene(scene_path)
    label = str(scene["target_label"])
    payload = _scene_geometry_payload(scene)
    path = Path(scene_path)
    payload.update(
        {
            "sceneKind": "unit_cell",
            "viewerTitle": "Interactive Unit Cell Inspector (Three.js)",
            "sceneRevision": f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}",
            "palette": browser_palette(),
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
    selected_strut_id: int | None = None,
    slice_evidence: dict[str, Any] | None = None,
    key: str = "lattice-threejs-viewer",
    height: int | str = "content",
) -> Any:
    """Render the registered lattice scene and return component state."""

    renderer = _component_renderer()
    payload = dict(scene_payload(str(Path(scene_path).resolve())))
    payload["selectedStrutId"] = selected_strut_id
    payload["sliceEvidence"] = slice_evidence
    return renderer(
        key=key,
        data=payload,
        default={"selected_strut_id": selected_strut_id},
        on_selected_strut_id_change=lambda: None,
        height=height,
    )


def unit_cell_threejs_viewer(
    scene_path: Path | str,
    *,
    slice_evidence: dict[str, Any] | None = None,
    key: str,
    height: int | str = "content",
) -> Any:
    """Render one fixed derived unit-cell scene and return component state."""

    renderer = _component_renderer()
    payload = dict(unit_cell_scene_payload(str(Path(scene_path).resolve())))
    target_id = int(payload["targetStrutId"])
    payload["selectedStrutId"] = target_id
    payload["sliceEvidence"] = slice_evidence
    return renderer(
        key=key,
        data=payload,
        default={"selected_strut_id": target_id},
        on_selected_strut_id_change=lambda: None,
        height=height,
    )
