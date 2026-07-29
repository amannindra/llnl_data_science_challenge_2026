"""Compact, validated scene geometry for browser-native lattice rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, DefectConfig
from .geometry import endpoints_for_struts, registered_junctions
from .io import load_graph, read_json
from .xray_context import load_xray_context


SCENE_SCHEMA_VERSION = 2
LABEL_NAMES = ("intact", "missing", "broken", "thin", "uncertain")
LABEL_TO_CODE = {name: index for index, name in enumerate(LABEL_NAMES)}


def build_lattice_scene(
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    sample_table: pd.DataFrame | None = None,
    xray_context: dict[str, Any] | None = None,
) -> dict[str, np.ndarray]:
    """Build registered full-lattice and analyzed-overlay browser geometry."""

    graph = load_graph(config.graph_path)
    alignment = read_json(config.alignment_path)
    if not alignment.get("reliable", False):
        raise RuntimeError("Saved alignment is not reliable; refusing to build scene")

    permutation = tuple(int(value) for value in alignment["selected_permutation"])
    residual = np.asarray(alignment["residual_transform"], dtype=np.float64)
    nominal_ids, nominal_starts, nominal_ends = endpoints_for_struts(
        graph,
        permutation=permutation,
        residual_transform=residual,
    )
    junction_ids, junction_positions = registered_junctions(
        graph,
        permutation=permutation,
        residual_transform=residual,
    )
    strut_by_id = {int(item["id"]): item for item in graph["struts"]}
    nominal_junction_ids = np.asarray(
        [
            [
                int(strut_by_id[int(strut_id)]["junction0"]),
                int(strut_by_id[int(strut_id)]["junction1"]),
            ]
            for strut_id in nominal_ids
        ],
        dtype=np.int32,
    )

    table = (
        pd.read_csv(config.sample_path)
        if sample_table is None
        else sample_table.copy()
    )
    required = {
        "strut_id",
        "start_z",
        "start_y",
        "start_x",
        "end_z",
        "end_y",
        "end_x",
        "prediction",
    }
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Sample table is missing scene columns: {sorted(missing)}")
    if table["strut_id"].duplicated().any():
        raise ValueError("Sample table contains duplicate strut IDs")

    labels = table["prediction"].astype(str)
    invalid = sorted(set(labels).difference(LABEL_TO_CODE))
    if invalid:
        raise ValueError(f"Sample table contains unsupported labels: {invalid}")

    analyzed_ids = table["strut_id"].to_numpy(dtype=np.int32)
    nominal_lookup = {
        int(strut_id): index for index, strut_id in enumerate(nominal_ids)
    }
    unknown = [int(value) for value in analyzed_ids if int(value) not in nominal_lookup]
    if unknown:
        raise ValueError(f"Analyzed strut IDs are absent from nominal graph: {unknown[:10]}")

    nominal_segments = np.stack((nominal_starts, nominal_ends), axis=1)
    analyzed_indices = np.asarray(
        [nominal_lookup[int(value)] for value in analyzed_ids], dtype=np.int64
    )
    analyzed_segments = nominal_segments[analyzed_indices]
    saved_segments = np.stack(
        (
            table[["start_z", "start_y", "start_x"]].to_numpy(dtype=float),
            table[["end_z", "end_y", "end_x"]].to_numpy(dtype=float),
        ),
        axis=1,
    )
    if not np.allclose(analyzed_segments, saved_segments, rtol=0.0, atol=1e-4):
        raise ValueError(
            "Saved analyzed coordinates do not match the registered nominal graph"
        )

    context = (
        load_xray_context(config.output_dir / "xray_context.npz")
        if xray_context is None
        else xray_context
    )
    return {
        "schema_version": np.asarray(SCENE_SCHEMA_VERSION, dtype=np.int16),
        "coordinate_order": np.asarray("zyx"),
        "selected_mapping": np.asarray(str(alignment["selected_mapping"])),
        "nominal_strut_ids": nominal_ids.astype(np.int32),
        "nominal_segments_zyx": nominal_segments.astype(np.float32),
        "junction_ids": junction_ids.astype(np.int32),
        "junction_positions_zyx": junction_positions.astype(np.float32),
        "nominal_junction_ids": nominal_junction_ids,
        "analyzed_strut_ids": analyzed_ids,
        "analyzed_segments_zyx": analyzed_segments.astype(np.float32),
        "analyzed_label_codes": np.asarray(
            [LABEL_TO_CODE[value] for value in labels], dtype=np.uint8
        ),
        "label_names": np.asarray(LABEL_NAMES),
        "xray_vertices_zyx": np.asarray(
            context["vertices_zyx"], dtype=np.float32
        ),
        "xray_faces": np.asarray(context["faces"], dtype=np.int32),
    }


def save_lattice_scene(
    output_path: Path | str,
    config: DefectConfig = DEFAULT_CONFIG,
) -> Path:
    """Write a compressed browser scene without copying raw CT voxels."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **build_lattice_scene(config))
    return path


def load_lattice_scene(path: Path | str) -> dict[str, np.ndarray]:
    """Load and validate a compact browser scene artifact."""

    with np.load(Path(path), allow_pickle=False) as payload:
        required = {
            "schema_version",
            "coordinate_order",
            "selected_mapping",
            "nominal_strut_ids",
            "nominal_segments_zyx",
            "junction_ids",
            "junction_positions_zyx",
            "nominal_junction_ids",
            "analyzed_strut_ids",
            "analyzed_segments_zyx",
            "analyzed_label_codes",
            "label_names",
            "xray_vertices_zyx",
            "xray_faces",
        }
        missing = required.difference(payload.files)
        if missing:
            raise ValueError(f"Lattice scene is missing fields: {sorted(missing)}")
        scene = {name: np.asarray(payload[name]) for name in required}

    if int(scene["schema_version"]) != SCENE_SCHEMA_VERSION:
        raise ValueError("Unsupported lattice scene schema version")
    if str(scene["coordinate_order"]) != "zyx":
        raise ValueError("Lattice scene coordinates must be in CT z,y,x order")
    nominal = scene["nominal_segments_zyx"]
    analyzed = scene["analyzed_segments_zyx"]
    if nominal.ndim != 3 or nominal.shape[1:] != (2, 3):
        raise ValueError("nominal_segments_zyx must have shape (n, 2, 3)")
    if analyzed.ndim != 3 or analyzed.shape[1:] != (2, 3):
        raise ValueError("analyzed_segments_zyx must have shape (n, 2, 3)")
    if len(scene["nominal_strut_ids"]) != len(nominal):
        raise ValueError("Nominal IDs and segments have different lengths")
    if scene["junction_positions_zyx"].ndim != 2 or scene[
        "junction_positions_zyx"
    ].shape[1] != 3:
        raise ValueError("junction_positions_zyx must have shape (n, 3)")
    if len(scene["junction_ids"]) != len(scene["junction_positions_zyx"]):
        raise ValueError("Junction IDs and positions have different lengths")
    if scene["nominal_junction_ids"].shape != (len(nominal), 2):
        raise ValueError("nominal_junction_ids must have shape (n_struts, 2)")
    known_junctions = set(int(value) for value in scene["junction_ids"])
    referenced_junctions = set(
        int(value) for value in scene["nominal_junction_ids"].reshape(-1)
    )
    if not referenced_junctions.issubset(known_junctions):
        raise ValueError("Nominal struts reference unknown junction IDs")
    if not (
        len(scene["analyzed_strut_ids"])
        == len(analyzed)
        == len(scene["analyzed_label_codes"])
    ):
        raise ValueError("Analyzed IDs, segments, and labels have different lengths")
    if scene["xray_vertices_zyx"].ndim != 2 or scene[
        "xray_vertices_zyx"
    ].shape[1] != 3:
        raise ValueError("xray_vertices_zyx must have shape (n, 3)")
    if scene["xray_faces"].ndim != 2 or scene["xray_faces"].shape[1] != 3:
        raise ValueError("xray_faces must have shape (n, 3)")
    label_count = len(scene["label_names"])
    if np.any(scene["analyzed_label_codes"] >= label_count):
        raise ValueError("Analyzed label code is outside label_names")
    return scene
