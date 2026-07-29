"""Fixed, derived unit-cell scenes for the visualization-only dashboard.

The browser receives only compact triangle meshes, registered strut geometry,
and PNG evidence panels. Raw CT voxels never leave this deterministic builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from skimage.measure import marching_cubes
from skimage.morphology import skeletonize

from .alignment import neighborhood_offsets
from .colors import CANDIDATE_COLORS, SEGMENTATION_COLOR, SKELETON_COLOR
from .config import DEFAULT_CONFIG, DefectConfig
from .geometry import endpoints_for_struts, line_points, registered_junctions
from .io import load_graph, open_ct_memmap, read_json, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402


UNIT_CELL_SCHEMA_VERSION = 2
UNIT_CELL_STRUT_COUNT = 24
UNIT_CELL_DIRNAME = "unit_cells"


@dataclass(frozen=True)
class UnitCellExample:
    """One approved fixed unit-cell example."""

    key: str
    title: str
    cell_id: int
    target_strut_id: int
    expected_label: str


FIXED_UNIT_CELL_EXAMPLES = (
    UnitCellExample(
        key="broken",
        title="Broken example",
        cell_id=521,
        target_strut_id=12958,
        expected_label="broken",
    ),
    UnitCellExample(
        key="missing",
        title="Missing example",
        cell_id=646,
        target_strut_id=16082,
        expected_label="missing",
    ),
    UnitCellExample(
        key="thin",
        title="Thin example",
        cell_id=605,
        target_strut_id=15040,
        expected_label="thin",
    ),
    UnitCellExample(
        key="intact",
        title="Intact example",
        cell_id=362,
        target_strut_id=9000,
        expected_label="intact",
    ),
)

SEMANTIC_COLORS = {
    label: CANDIDATE_COLORS[label]
    for label in ("broken", "missing", "thin", "intact")
}


def _fixed_example(key: str) -> UnitCellExample:
    try:
        return next(item for item in FIXED_UNIT_CELL_EXAMPLES if item.key == key)
    except StopIteration as exc:
        allowed = ", ".join(item.key for item in FIXED_UNIT_CELL_EXAMPLES)
        raise KeyError(f"Unknown fixed unit-cell example {key!r}; expected {allowed}") from exc


def _cell_record(graph: dict[str, Any], cell_id: int) -> dict[str, Any]:
    matches = [cell for cell in graph["unit_cells"] if int(cell["id"]) == cell_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one unit cell {cell_id}, found {len(matches)}")
    return matches[0]


def _select_display_struts(
    graph: dict[str, Any],
    *,
    cell_id: int,
    target_strut_id: int,
    permutation: tuple[int, int, int],
    residual_transform: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Select the canonical 24 ordered struts for one registered unit cell.

    Interior cell records contain exactly 24 struts. Boundary cell records append
    four neighboring/boundary segments after those canonical entries; those
    appended segments previously distorted the displayed cell and camera bounds.
    """

    cell = _cell_record(graph, cell_id)
    graph_ids = np.asarray(cell["struts"], dtype=np.int64)
    if target_strut_id not in graph_ids:
        raise ValueError(
            f"Target strut {target_strut_id} is not listed in unit cell {cell_id}"
        )
    canonical_ids = graph_ids[:UNIT_CELL_STRUT_COUNT]
    if len(canonical_ids) != UNIT_CELL_STRUT_COUNT:
        raise ValueError(
            f"Unit cell {cell_id} has only {len(canonical_ids)} graph struts"
        )
    if target_strut_id not in canonical_ids:
        raise ValueError(
            f"Target strut {target_strut_id} is not in the canonical 24 struts "
            f"for unit cell {cell_id}"
        )
    ids, starts, ends = endpoints_for_struts(
        graph,
        strut_ids=canonical_ids,
        permutation=permutation,
        residual_transform=residual_transform,
    )
    return ids, starts, ends, int(len(graph_ids))


def _longest_false_bounds(values: np.ndarray) -> tuple[int, int]:
    best_start = best_end = current_start = 0
    in_gap = False
    for index, value in enumerate(np.asarray(values, dtype=bool)):
        if not value and not in_gap:
            current_start = index
            in_gap = True
        if value and in_gap:
            if index - current_start > best_end - best_start:
                best_start, best_end = current_start, index
            in_gap = False
    if in_gap and len(values) - current_start > best_end - best_start:
        best_start, best_end = current_start, len(values)
    return best_start, best_end


def _support_along_target(
    crop: np.ndarray,
    origin: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    *,
    threshold: float,
    search_radius: int,
) -> tuple[np.ndarray, np.ndarray]:
    points, _ = line_points(start, end, spacing_vox=0.5, trim_fraction=0.1)
    local = np.rint(points - origin[None, :]).astype(np.int64)
    offsets, _ = neighborhood_offsets(search_radius)
    shape = np.asarray(crop.shape)
    support = np.zeros(len(local), dtype=bool)
    for index, point in enumerate(local):
        candidates = point[None, :] + offsets
        valid = np.all((candidates >= 0) & (candidates < shape), axis=1)
        candidates = candidates[valid]
        if len(candidates):
            support[index] = bool(
                np.any(crop[tuple(candidates.T)] >= threshold)
            )
    return points, support


def _bounded_mesh(
    crop: np.ndarray,
    origin: np.ndarray,
    *,
    threshold: float,
    maximum_faces: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    smoothed = gaussian_filter(np.asarray(crop, dtype=np.float32), sigma=0.65)
    vertices, faces, _, _ = marching_cubes(
        smoothed,
        level=float(threshold),
        step_size=1,
        allow_degenerate=False,
    )
    vertex_intensity = map_coordinates(
        np.asarray(crop, dtype=np.float32),
        vertices.T,
        order=1,
        mode="nearest",
        prefilter=False,
    )
    low, high = np.quantile(vertex_intensity, [0.02, 0.98])
    vertex_texture = np.clip(
        (vertex_intensity - low) / max(float(high - low), 1.0),
        0.0,
        1.0,
    )
    if len(faces) > maximum_faces:
        chosen = np.linspace(0, len(faces) - 1, maximum_faces, dtype=np.int64)
        faces = faces[chosen]
        used, inverse = np.unique(faces.reshape(-1), return_inverse=True)
        vertices = vertices[used]
        vertex_texture = vertex_texture[used]
        faces = inverse.reshape(-1, 3)
    return (
        (vertices + origin[None, :]).astype(np.float32),
        faces.astype(np.int32),
        vertex_texture.astype(np.float32),
    )


def _slice_arrays(
    crop: np.ndarray,
    mask: np.ndarray,
    skeleton: np.ndarray,
    local_focus: np.ndarray,
    axis: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    index = int(np.clip(np.rint(local_focus[axis]), 0, crop.shape[axis] - 1))
    return (
        np.take(crop, index, axis=axis),
        np.take(mask, index, axis=axis),
        np.take(skeleton, index, axis=axis),
        index,
    )


def _render_contours(
    path: Path,
    *,
    crop: np.ndarray,
    mask: np.ndarray,
    skeleton: np.ndarray,
    origin: np.ndarray,
    focus_zyx: np.ndarray,
    target_segment: np.ndarray,
    example: UnitCellExample,
) -> None:
    axes_metadata = (
        (0, "Axial", 1, 2, "CT x (voxels)", "CT y (voxels)"),
        (1, "Coronal", 0, 2, "CT x (voxels)", "CT z (voxels)"),
        (2, "Sagittal", 0, 1, "CT y (voxels)", "CT z (voxels)"),
    )
    target_color = SEMANTIC_COLORS[example.expected_label]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5.6))
    figure.subplots_adjust(left=0.05, right=0.99, top=0.86, bottom=0.18, wspace=0.24)
    local_focus = focus_zyx - origin
    vmin, vmax = np.quantile(crop, [0.02, 0.998])
    for plot_axis, (axis, title, row_axis, col_axis, xlabel, ylabel) in zip(
        axes, axes_metadata
    ):
        image, mask_slice, skeleton_slice, local_index = _slice_arrays(
            crop, mask, skeleton, local_focus, axis
        )
        row_values = origin[row_axis] + np.arange(image.shape[0])
        column_values = origin[col_axis] + np.arange(image.shape[1])
        plot_axis.imshow(
            image,
            cmap="gray",
            vmin=float(vmin),
            vmax=float(vmax),
            extent=(
                float(column_values[0]),
                float(column_values[-1]),
                float(row_values[-1]),
                float(row_values[0]),
            ),
            interpolation="nearest",
        )
        if np.any(mask_slice) and np.any(~mask_slice):
            plot_axis.contour(
                column_values,
                row_values,
                mask_slice.astype(np.uint8),
                levels=[0.5],
                colors=[SEGMENTATION_COLOR],
                linewidths=1.0,
            )
        skeleton_points = np.argwhere(skeleton_slice)
        if len(skeleton_points):
            plot_axis.scatter(
                origin[col_axis] + skeleton_points[:, 1],
                origin[row_axis] + skeleton_points[:, 0],
                s=4,
                c=SKELETON_COLOR,
                alpha=0.8,
                linewidths=0,
            )
        plot_axis.plot(
            target_segment[:, col_axis],
            target_segment[:, row_axis],
            color=target_color,
            linewidth=2.6,
            linestyle="--",
        )
        plot_axis.scatter(
            [focus_zyx[col_axis]],
            [focus_zyx[row_axis]],
            c=target_color,
            s=35,
            edgecolors="white",
            linewidths=0.8,
            zorder=5,
        )
        global_index = int(origin[axis] + local_index)
        plot_axis.set_title(f"{title} · {('z', 'y', 'x')[axis]}={global_index}")
        plot_axis.set_xlabel(xlabel)
        plot_axis.set_ylabel(ylabel)
        plot_axis.set_aspect("equal")
        plot_axis.invert_yaxis()

    figure.suptitle(
        f"{example.title} · unit cell {example.cell_id} · strut {example.target_strut_id}",
        fontsize=15,
        fontweight=600,
    )
    figure.legend(
        handles=[
            Line2D([0], [0], color=SEGMENTATION_COLOR, label="Segmentation boundary"),
            Line2D([0], [0], color=target_color, linestyle="--", label="Expected strut"),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=SKELETON_COLOR,
                label="Deterministic skeleton",
            ),
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.015),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def build_fixed_unit_cell_example(
    key: str,
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    maximum_faces: int = 60_000,
) -> dict[str, Any]:
    """Build one approved unit-cell example and its derived visual evidence."""

    example = _fixed_example(key)
    graph = load_graph(config.graph_path)
    alignment = read_json(config.alignment_path)
    if not alignment.get("reliable", False):
        raise RuntimeError("Saved registration is not reliable")
    permutation = tuple(int(value) for value in alignment["selected_permutation"])
    residual = np.asarray(alignment["residual_transform"], dtype=np.float64)
    ids, starts, ends, graph_strut_count = _select_display_struts(
        graph,
        cell_id=example.cell_id,
        target_strut_id=example.target_strut_id,
        permutation=permutation,
        residual_transform=residual,
    )
    if len(ids) != UNIT_CELL_STRUT_COUNT:
        raise RuntimeError("Unit-cell display selection did not produce 24 struts")

    target_index = int(np.flatnonzero(ids == example.target_strut_id)[0])
    target_segment = np.stack((starts[target_index], ends[target_index]))
    strut_by_id = {int(item["id"]): item for item in graph["struts"]}
    nominal_junction_ids = np.asarray(
        [
            [
                int(strut_by_id[int(strut_id)]["junction0"]),
                int(strut_by_id[int(strut_id)]["junction1"]),
            ]
            for strut_id in ids
        ],
        dtype=np.int32,
    )
    local_junction_ids = np.unique(nominal_junction_ids)
    all_junction_ids, all_junction_positions = registered_junctions(
        graph,
        permutation=permutation,
        residual_transform=residual,
    )
    junction_position_by_id = {
        int(junction_id): all_junction_positions[index]
        for index, junction_id in enumerate(all_junction_ids)
    }
    local_junction_positions = np.asarray(
        [junction_position_by_id[int(junction_id)] for junction_id in local_junction_ids],
        dtype=np.float32,
    )
    lower = np.maximum(np.floor(np.minimum(starts.min(0), ends.min(0))).astype(int) - 8, 0)
    volume = open_ct_memmap(config.ct_path)
    upper = np.minimum(
        np.ceil(np.maximum(starts.max(0), ends.max(0))).astype(int) + 9,
        np.asarray(volume.shape),
    )
    crop_slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper))
    crop = np.asarray(volume[crop_slices])
    threshold = float(alignment["threshold_otsu"])
    mask = crop >= threshold
    deterministic_skeleton = skeletonize(mask)

    sampled_points, support = _support_along_target(
        crop,
        lower,
        target_segment[0],
        target_segment[1],
        threshold=threshold,
        search_radius=config.analysis_search_radius_vox,
    )
    if example.expected_label == "broken":
        gap_start, gap_end = _longest_false_bounds(support)
        if gap_end <= gap_start:
            raise RuntimeError("Broken example has no unsupported centerline gap")
        focus = sampled_points[(gap_start + gap_end - 1) // 2]
        focus_method = "center of largest unsupported centerline run"
    else:
        focus = target_segment.mean(axis=0)
        focus_method = "expected target-strut midpoint"

    vertices, faces, vertex_texture = _bounded_mesh(
        crop,
        lower,
        threshold=threshold,
        maximum_faces=maximum_faces,
    )
    output_dir = config.output_dir / UNIT_CELL_DIRNAME
    scene_path = output_dir / f"{example.key}_cell_{example.cell_id}.npz"
    contour_path = output_dir / f"{example.key}_cell_{example.cell_id}_contours.png"
    metadata_path = output_dir / f"{example.key}_cell_{example.cell_id}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        scene_path,
        schema_version=np.asarray(UNIT_CELL_SCHEMA_VERSION, dtype=np.int16),
        scene_kind=np.asarray("unit_cell"),
        coordinate_order=np.asarray("zyx"),
        selected_mapping=np.asarray(str(alignment["selected_mapping"])),
        cell_id=np.asarray(example.cell_id, dtype=np.int32),
        cell_indices=np.asarray(_cell_record(graph, example.cell_id)["indices"], dtype=np.int16),
        target_strut_id=np.asarray(example.target_strut_id, dtype=np.int32),
        target_label=np.asarray(example.expected_label),
        nominal_strut_ids=ids.astype(np.int32),
        nominal_segments_zyx=np.stack((starts, ends), axis=1).astype(np.float32),
        junction_ids=local_junction_ids.astype(np.int32),
        junction_positions_zyx=local_junction_positions,
        nominal_junction_ids=nominal_junction_ids,
        analyzed_strut_ids=np.asarray([example.target_strut_id], dtype=np.int32),
        analyzed_segments_zyx=target_segment[None, ...].astype(np.float32),
        analyzed_label_codes=np.asarray([0], dtype=np.uint8),
        label_names=np.asarray([example.expected_label]),
        xray_vertices_zyx=vertices,
        xray_faces=faces,
        xray_vertex_texture=vertex_texture,
        focus_zyx=np.asarray(focus, dtype=np.float32),
    )
    _render_contours(
        contour_path,
        crop=crop,
        mask=mask,
        skeleton=deterministic_skeleton,
        origin=lower,
        focus_zyx=focus,
        target_segment=target_segment,
        example=example,
    )
    metadata = {
        "schema_version": UNIT_CELL_SCHEMA_VERSION,
        "scene_kind": "unit_cell",
        "example_key": example.key,
        "title": example.title,
        "cell_id": example.cell_id,
        "cell_indices": [int(value) for value in _cell_record(graph, example.cell_id)["indices"]],
        "target_strut_id": example.target_strut_id,
        "target_label": example.expected_label,
        "classification_scope": "exploratory candidate; visual evidence only",
        "coordinate_order": "zyx",
        "selected_mapping": str(alignment["selected_mapping"]),
        "specimen_tilt_preserved": not bool(alignment["residual_correction_applied"]),
        "graph_cell_strut_count": graph_strut_count,
        "display_strut_count": int(len(ids)),
        "display_selection_rule": "canonical first 24 ordered graph struts",
        "display_strut_ids": [int(value) for value in ids],
        "threshold_otsu": threshold,
        "crop_bounds_zyx": {
            "lower_inclusive": [int(value) for value in lower],
            "upper_exclusive": [int(value) for value in upper],
        },
        "focus_zyx": [float(value) for value in focus],
        "focus_method": focus_method,
        "target_support_fraction": float(support.mean()),
        "target_gap_fraction": float(
            (_longest_false_bounds(support)[1] - _longest_false_bounds(support)[0])
            / len(support)
        ),
        "mesh_vertex_count": int(len(vertices)),
        "mesh_face_count": int(len(faces)),
        "surface_texture": (
            "CT-intensity shading on the registered segmented isosurface; "
            "qualitative visualization, not calibrated roughness measurement"
        ),
        "scene_artifact": scene_path.name,
        "contour_artifact": contour_path.name,
        "raw_ct_embedded": False,
    }
    write_json(metadata_path, metadata)
    return metadata


def build_all_fixed_unit_cell_examples(
    config: DefectConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """Build the four fixed exploratory examples approved for the dashboard."""

    return [
        build_fixed_unit_cell_example(example.key, config)
        for example in FIXED_UNIT_CELL_EXAMPLES
    ]


def load_unit_cell_scene(path: Path | str) -> dict[str, np.ndarray]:
    """Load and validate a derived fixed unit-cell scene."""

    with np.load(Path(path), allow_pickle=False) as payload:
        required = {
            "schema_version",
            "scene_kind",
            "coordinate_order",
            "selected_mapping",
            "cell_id",
            "cell_indices",
            "target_strut_id",
            "target_label",
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
            "xray_vertex_texture",
            "focus_zyx",
        }
        missing = required.difference(payload.files)
        if missing:
            raise ValueError(f"Unit-cell scene is missing fields: {sorted(missing)}")
        scene = {name: np.asarray(payload[name]) for name in required}
    if int(scene["schema_version"]) != UNIT_CELL_SCHEMA_VERSION:
        raise ValueError("Unsupported unit-cell scene schema version")
    if str(scene["scene_kind"]) != "unit_cell":
        raise ValueError("Expected a unit-cell scene")
    if str(scene["coordinate_order"]) != "zyx":
        raise ValueError("Unit-cell coordinates must use CT z,y,x order")
    if scene["nominal_segments_zyx"].shape != (UNIT_CELL_STRUT_COUNT, 2, 3):
        raise ValueError("Unit-cell scene must contain exactly 24 nominal struts")
    if len(scene["nominal_strut_ids"]) != UNIT_CELL_STRUT_COUNT:
        raise ValueError("Unit-cell scene must contain exactly 24 nominal IDs")
    if scene["junction_positions_zyx"].ndim != 2 or scene[
        "junction_positions_zyx"
    ].shape[1] != 3:
        raise ValueError("Unit-cell junction positions must have shape (n, 3)")
    if len(scene["junction_ids"]) != len(scene["junction_positions_zyx"]):
        raise ValueError("Unit-cell junction IDs and positions have different lengths")
    if scene["nominal_junction_ids"].shape != (UNIT_CELL_STRUT_COUNT, 2):
        raise ValueError("Unit-cell nominal junction IDs must have shape (24, 2)")
    if int(scene["target_strut_id"]) not in scene["nominal_strut_ids"]:
        raise ValueError("Target strut is absent from unit-cell geometry")
    if scene["xray_vertices_zyx"].ndim != 2 or scene["xray_vertices_zyx"].shape[1] != 3:
        raise ValueError("Unit-cell CT surface vertices must have shape (n, 3)")
    if scene["xray_faces"].ndim != 2 or scene["xray_faces"].shape[1] != 3:
        raise ValueError("Unit-cell CT surface faces must have shape (n, 3)")
    if scene["xray_vertex_texture"].shape != (len(scene["xray_vertices_zyx"]),):
        raise ValueError("Unit-cell CT surface texture must match its vertices")
    return scene


if __name__ == "__main__":
    built = build_all_fixed_unit_cell_examples()
    for item in built:
        print(
            f"Built {item['title']}: unit cell {item['cell_id']}, "
            f"target strut {item['target_strut_id']}, "
            f"{item['display_strut_count']} displayed struts"
        )
