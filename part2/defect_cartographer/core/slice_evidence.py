"""Read-only, on-demand CT slice evidence for analyzed struts.

This module is dashboard-only. It reads a bounded registered CT crop and returns
small PNG layers; it never exposes the raw volume to agents, MCP, or the browser.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
import json
import math
import os
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from scipy.ndimage import map_coordinates
from skimage.morphology import skeletonize
from skimage.segmentation import find_boundaries

from .alignment import neighborhood_offsets
from .colors import (
    CANDIDATE_COLORS,
    OBSERVED_CENTERLINE_COLOR,
    SEGMENTATION_COLOR,
)
from .config import DEFAULT_CONFIG, DefectConfig
from .geometry import line_points
from .io import open_ct_memmap, read_json

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402


SLICE_EVIDENCE_SCHEMA_VERSION = 3
SLICE_CROP_SIZE = 96
SLAB_THICKNESS_VOX = 9
SLICE_POSITION_OFFSETS_VOX = (-4, -2, 0, 2, 4)
AXIS_METADATA = (
    (0, "Axial", "z", 1, 2, "x", "y"),
    (1, "Coronal", "y", 0, 2, "x", "z"),
    (2, "Sagittal", "x", 0, 1, "y", "z"),
)


def _canonical_label(value: object) -> str:
    """Map main-agent review states to the dashboard's conservative palette."""

    aliases = {
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
    return aliases.get(str(value).strip().lower(), "uncertain")


def _artifact_file(directory: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        path = directory / name
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"No saved artifact found in {directory}; expected one of {names}"
    )


def _hex_rgb(value: str) -> tuple[float, float, float]:
    normalized = value.lstrip("#")
    return tuple(int(normalized[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _png_data_url(image: np.ndarray) -> str:
    buffer = BytesIO()
    mpimg.imsave(buffer, image, format="png")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _raw_png(
    image: np.ndarray,
    *,
    lower_percentile: float,
    upper_percentile: float,
    gamma: float,
) -> str:
    finite = np.asarray(image, dtype=np.float32)
    vmin, vmax = np.quantile(finite, [lower_percentile, upper_percentile])
    scale = max(vmax - vmin, 1.0)
    normalized = np.clip((finite - vmin) / scale, 0.0, 1.0)
    normalized = np.power(normalized, gamma)
    return _png_data_url(np.repeat(normalized[..., None], 3, axis=2))


def _overlay_png(mask: np.ndarray, color: str, alpha: float) -> str:
    rgba = np.zeros((*mask.shape, 4), dtype=np.float32)
    rgba[..., :3] = _hex_rgb(color)
    rgba[..., 3] = np.asarray(mask, dtype=np.float32) * alpha
    return _png_data_url(rgba)


def _strict_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return str(value)


def _longest_false_bounds(values: np.ndarray) -> tuple[int, int]:
    best_start = best_end = current_start = 0
    in_gap = False
    for index, value in enumerate(np.asarray(values, dtype=bool)):
        if not value and not in_gap:
            current_start = index
            in_gap = True
        elif value and in_gap:
            if index - current_start > best_end - best_start:
                best_start, best_end = current_start, index
            in_gap = False
    if in_gap and len(values) - current_start > best_end - best_start:
        best_start, best_end = current_start, len(values)
    return best_start, best_end


def _support_focus(
    volume: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    *,
    threshold: float,
    search_radius: int,
) -> tuple[np.ndarray, bool]:
    points, _ = line_points(start, end, spacing_vox=0.5, trim_fraction=0.1)
    integer_points = np.rint(points).astype(np.int64)
    offsets, _ = neighborhood_offsets(search_radius)
    shape = np.asarray(volume.shape)
    support = np.zeros(len(points), dtype=bool)
    for index, point in enumerate(integer_points):
        candidates = point[None, :] + offsets
        valid = np.all((candidates >= 0) & (candidates < shape), axis=1)
        candidates = candidates[valid]
        if len(candidates):
            support[index] = bool(np.any(volume[tuple(candidates.T)] >= threshold))
    gap_start, gap_end = _longest_false_bounds(support)
    if gap_end > gap_start:
        return points[(gap_start + gap_end - 1) // 2], True
    return (start + end) / 2.0, False


def _fixed_crop_bounds(
    focus: np.ndarray,
    shape: tuple[int, int, int],
    size: int,
) -> tuple[np.ndarray, np.ndarray]:
    shape_array = np.asarray(shape, dtype=np.int64)
    width = np.minimum(shape_array, int(size))
    lower = np.rint(focus).astype(np.int64) - width // 2
    lower = np.minimum(np.maximum(lower, 0), shape_array - width)
    return lower, lower + width


def _projected_line(
    segment: np.ndarray,
    *,
    lower: np.ndarray,
    image_shape: tuple[int, int],
    row_axis: int,
    column_axis: int,
) -> list[float]:
    denominator_x = max(image_shape[1] - 1, 1)
    denominator_y = max(image_shape[0] - 1, 1)
    return [
        float((segment[0, column_axis] - lower[column_axis]) / denominator_x),
        float((segment[0, row_axis] - lower[row_axis]) / denominator_y),
        float((segment[1, column_axis] - lower[column_axis]) / denominator_x),
        float((segment[1, row_axis] - lower[row_axis]) / denominator_y),
    ]


def _projected_point(
    point: np.ndarray,
    *,
    lower: np.ndarray,
    image_shape: tuple[int, int],
    row_axis: int,
    column_axis: int,
) -> list[float]:
    """Project a registered z,y,x point into normalized image coordinates."""

    denominator_x = max(image_shape[1] - 1, 1)
    denominator_y = max(image_shape[0] - 1, 1)
    return [
        float((point[column_axis] - lower[column_axis]) / denominator_x),
        float((point[row_axis] - lower[row_axis]) / denominator_y),
    ]


def _target_corridor(
    shape: tuple[int, int, int],
    segment: np.ndarray,
    lower: np.ndarray,
    radius: int,
) -> np.ndarray:
    """Return a deterministic tubular ROI surrounding the expected strut."""

    points, _ = line_points(
        segment[0] - lower,
        segment[1] - lower,
        spacing_vox=0.75,
        trim_fraction=0.0,
    )
    offsets, distances = neighborhood_offsets(radius)
    offsets = offsets[distances <= float(radius)]
    corridor = np.zeros(shape, dtype=bool)
    shape_array = np.asarray(shape)
    for point in np.rint(points).astype(np.int64):
        candidates = point[None, :] + offsets
        valid = np.all((candidates >= 0) & (candidates < shape_array), axis=1)
        candidates = candidates[valid]
        corridor[tuple(candidates.T)] = True
    return corridor


def _axis_slab(
    array: np.ndarray,
    *,
    axis: int,
    index: int,
    thickness: int,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Return a centered maximum projection and its half-open local bounds."""

    half = thickness // 2
    start = max(0, index - half)
    stop = min(array.shape[axis], index + half + 1)
    slab = np.take(array, np.arange(start, stop), axis=axis)
    return np.max(slab, axis=axis), (start, stop)


def _strut_aligned_view(
    crop: np.ndarray,
    *,
    lower: np.ndarray,
    segment: np.ndarray,
    threshold: float,
    corridor_radius: int,
    size: int,
    focus: np.ndarray,
) -> dict[str, Any]:
    """Return a longitudinal CT plane aligned with the expected strut axis."""

    direction = segment[1] - segment[0]
    length = float(np.linalg.norm(direction))
    if length <= 0:
        raise ValueError("Cannot construct a longitudinal view for a zero-length strut")
    direction /= length
    reference = np.eye(3)[int(np.argmin(np.abs(direction)))]
    across_vector = np.cross(direction, reference)
    across_vector /= np.linalg.norm(across_vector)
    normal_vector = np.cross(direction, across_vector)
    normal_vector /= np.linalg.norm(normal_vector)

    along = np.linspace(-0.15 * length, 1.15 * length, size)
    half_width = min(32.0, max(18.0, length * 0.55))
    across = np.linspace(-half_width, half_width, size)
    base = (
        segment[0][None, None, :]
        + along[None, :, None] * direction[None, None, :]
        + across[:, None, None] * across_vector[None, None, :]
    )

    def sample(offset: float) -> np.ndarray:
        coordinates = base + offset * normal_vector[None, None, :]
        local = coordinates - lower[None, None, :]
        return map_coordinates(
            np.asarray(crop, dtype=np.float32),
            [local[..., axis] for axis in range(3)],
            order=1,
            mode="constant",
            cval=float(np.min(crop)),
            prefilter=False,
        )

    target_band = np.abs(across)[:, None] <= float(corridor_radius)
    expected_start = 0.15 / 1.30
    expected_end = 1.15 / 1.30
    focus_along = float(np.dot(focus - segment[0], direction))
    focus_across = float(np.dot(focus - segment[0], across_vector))
    frames: list[dict[str, Any]] = []
    slab_half = SLAB_THICKNESS_VOX // 2
    for offset in SLICE_POSITION_OFFSETS_VOX:
        exact_raw = sample(float(offset))
        slab_offsets = np.arange(
            int(offset) - slab_half,
            int(offset) + slab_half + 1,
            dtype=np.float64,
        )
        slab_raw = np.max(
            np.stack([sample(float(item)) for item in slab_offsets]),
            axis=0,
        )
        exact_mask = exact_raw >= threshold
        slab_mask = slab_raw >= threshold
        exact_centerline = skeletonize(exact_mask & target_band)
        slab_centerline = skeletonize(slab_mask & target_band)
        frames.append(
            {
                "offsetVox": int(offset),
                "globalIndex": int(offset),
                "indexLabel": (
                    "center plane"
                    if offset == 0
                    else f"{offset:+d} vox from center plane"
                ),
                "modes": {
                    "exact": {
                        "rawDataUrl": _raw_png(
                            exact_raw,
                            lower_percentile=0.02,
                            upper_percentile=0.998,
                            gamma=1.0,
                        ),
                        "segmentationBoundaryDataUrl": _overlay_png(
                            find_boundaries(exact_mask, mode="inner"),
                            SEGMENTATION_COLOR,
                            0.96,
                        ),
                        "observedCenterlineDataUrl": _overlay_png(
                            exact_centerline,
                            OBSERVED_CENTERLINE_COLOR,
                            0.98,
                        ),
                    },
                    "slab": {
                        "rawDataUrl": _raw_png(
                            slab_raw,
                            lower_percentile=0.01,
                            upper_percentile=0.995,
                            gamma=0.68,
                        ),
                        "segmentationBoundaryDataUrl": _overlay_png(
                            find_boundaries(slab_mask, mode="inner"),
                            SEGMENTATION_COLOR,
                            0.96,
                        ),
                        "observedCenterlineDataUrl": _overlay_png(
                            slab_centerline,
                            OBSERVED_CENTERLINE_COLOR,
                            0.98,
                        ),
                    },
                },
                "slabBoundsGlobal": [
                    int(offset) - slab_half,
                    int(offset) + slab_half + 1,
                ],
            }
        )
    return {
        "axis": "longitudinal",
        "title": "Along strut",
        "xAxis": "Distance along expected strut",
        "yAxis": "Cross-strut distance",
        "frames": frames,
        "expectedLine": [
            float(expected_start),
            0.5,
            float(expected_end),
            0.5,
        ],
        "focusPoint": [
            float(np.clip((focus_along / length + 0.15) / 1.30, 0.0, 1.0)),
            float(np.clip((focus_across + half_width) / (2.0 * half_width), 0.0, 1.0)),
        ],
    }


@lru_cache(maxsize=8)
def _cached_slice_evidence(
    strut_id: int,
    ct_path: str,
    sample_path: str,
    alignment_path: str,
    crop_size: int,
    search_radius: int,
) -> dict[str, Any]:
    table = pd.read_csv(sample_path)
    rows = table.loc[table["strut_id"] == int(strut_id)]
    if rows.empty:
        raise ValueError(f"Strut {strut_id} is not present in the saved analysis")
    if len(rows) != 1:
        raise ValueError(f"Strut {strut_id} appears more than once")
    row = rows.iloc[0].copy()
    automated_prediction = str(row["prediction"])
    alignment = read_json(Path(alignment_path))
    if not alignment.get("reliable", False):
        raise RuntimeError("Saved alignment is not reliable")

    segment = np.asarray(
        [
            [row["start_z"], row["start_y"], row["start_x"]],
            [row["end_z"], row["end_y"], row["end_x"]],
        ],
        dtype=np.float64,
    )
    volume = open_ct_memmap(Path(ct_path))
    threshold = float(alignment["threshold_otsu"])
    focus_method = "expected target-strut midpoint"
    focus = segment.mean(axis=0)
    saved_focus = row.get("evidence_focus_zyx")
    if isinstance(saved_focus, str) and saved_focus.strip():
        parsed_focus = np.asarray(json.loads(saved_focus), dtype=np.float64)
        if parsed_focus.shape == (3,) and np.all(np.isfinite(parsed_focus)):
            focus = parsed_focus
            if str(row.get("label_source", "")).startswith("detector"):
                focus_method = "saved detector evidence coordinate"
            elif _canonical_label(row["prediction"]) == "broken":
                focus_method = "center of largest unsupported centerline run"
            else:
                focus_method = "expected target-strut midpoint"
    elif _canonical_label(row["prediction"]) == "broken":
        focus, gap_found = _support_focus(
            volume,
            segment[0],
            segment[1],
            threshold=threshold,
            search_radius=search_radius,
        )
        if gap_found:
            focus_method = "center of largest unsupported centerline run"

    lower, upper = _fixed_crop_bounds(focus, volume.shape, crop_size)
    crop_slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(lower, upper))
    crop = np.asarray(volume[crop_slices])
    mask = crop >= threshold
    corridor_radius = max(int(search_radius) + 2, 6)
    corridor = _target_corridor(
        crop.shape,
        segment,
        lower,
        corridor_radius,
    )
    observed_centerline = skeletonize(mask & corridor)
    local_focus = focus - lower
    preferred_view = "longitudinal"
    views: list[dict[str, Any]] = []
    for axis, title, axis_name, row_axis, column_axis, x_name, y_name in AXIS_METADATA:
        local_index = int(
            np.clip(np.rint(local_focus[axis]), 0, crop.shape[axis] - 1)
        )
        frames: list[dict[str, Any]] = []
        for offset in SLICE_POSITION_OFFSETS_VOX:
            frame_index = int(
                np.clip(local_index + offset, 0, crop.shape[axis] - 1)
            )
            exact_raw = np.take(crop, frame_index, axis=axis)
            exact_mask = np.take(mask, frame_index, axis=axis)
            exact_observed = np.take(observed_centerline, frame_index, axis=axis)
            slab_raw, slab_bounds = _axis_slab(
                crop,
                axis=axis,
                index=frame_index,
                thickness=SLAB_THICKNESS_VOX,
            )
            slab_mask, _ = _axis_slab(
                mask,
                axis=axis,
                index=frame_index,
                thickness=SLAB_THICKNESS_VOX,
            )
            slab_observed, _ = _axis_slab(
                observed_centerline,
                axis=axis,
                index=frame_index,
                thickness=SLAB_THICKNESS_VOX,
            )
            global_index = int(lower[axis] + frame_index)
            frames.append(
                {
                    "offsetVox": int(frame_index - local_index),
                    "globalIndex": global_index,
                    "indexLabel": f"{axis_name}={global_index}",
                    "modes": {
                        "exact": {
                            "rawDataUrl": _raw_png(
                                exact_raw,
                                lower_percentile=0.02,
                                upper_percentile=0.998,
                                gamma=1.0,
                            ),
                            "segmentationBoundaryDataUrl": _overlay_png(
                                find_boundaries(exact_mask, mode="inner"),
                                SEGMENTATION_COLOR,
                                0.96,
                            ),
                            "observedCenterlineDataUrl": _overlay_png(
                                exact_observed,
                                OBSERVED_CENTERLINE_COLOR,
                                0.98,
                            ),
                        },
                        "slab": {
                            "rawDataUrl": _raw_png(
                                slab_raw,
                                lower_percentile=0.01,
                                upper_percentile=0.995,
                                gamma=0.68,
                            ),
                            "segmentationBoundaryDataUrl": _overlay_png(
                                find_boundaries(slab_mask, mode="inner"),
                                SEGMENTATION_COLOR,
                                0.96,
                            ),
                            "observedCenterlineDataUrl": _overlay_png(
                                slab_observed,
                                OBSERVED_CENTERLINE_COLOR,
                                0.98,
                            ),
                        },
                    },
                    "slabBoundsGlobal": [
                        int(lower[axis] + slab_bounds[0]),
                        int(lower[axis] + slab_bounds[1]),
                    ],
                }
            )
        views.append(
            {
                "axis": axis_name,
                "title": title,
                "xAxis": f"CT {x_name} (voxels)",
                "yAxis": f"CT {y_name} (voxels)",
                "frames": frames,
                "expectedLine": _projected_line(
                    segment,
                    lower=lower,
                    image_shape=exact_raw.shape,
                    row_axis=row_axis,
                    column_axis=column_axis,
                ),
                "focusPoint": _projected_point(
                    focus,
                    lower=lower,
                    image_shape=exact_raw.shape,
                    row_axis=row_axis,
                    column_axis=column_axis,
                ),
            }
        )
    views.insert(
        0,
        _strut_aligned_view(
            crop,
            lower=lower,
            segment=segment,
            threshold=threshold,
            corridor_radius=corridor_radius,
            size=int(crop_size),
            focus=focus,
        ),
    )

    measurement_fields = (
        "occupancy",
        "gap_fraction",
        "alignment_error_vox",
        "diameter_median_um",
        "threshold_stability",
        "prediction_reason",
        "region",
        "orientation",
    )
    return {
        "schemaVersion": SLICE_EVIDENCE_SCHEMA_VERSION,
        "strutId": int(strut_id),
        "candidateLabel": _canonical_label(row["prediction"]),
        "candidateColor": CANDIDATE_COLORS[_canonical_label(row["prediction"])],
        "classificationStatus": "exploratory candidate; not validated",
        "rawAgentLabel": automated_prediction,
        "coordinateOrder": "zyx",
        "selectedMapping": str(alignment["selected_mapping"]),
        "focusZyx": [float(value) for value in focus],
        "focusMethod": focus_method,
        "preferredView": preferred_view,
        "slabThicknessVox": SLAB_THICKNESS_VOX,
        "positionOffsetsVox": list(SLICE_POSITION_OFFSETS_VOX),
        "cropSizeVox": int(crop_size),
        "contrast": {
            "exact": "view-local 2.0-99.8 percentile linear scaling",
            "slab": "view-local 1.0-99.5 percentile scaling with gamma 0.68",
        },
        "observedCenterlineScope": (
            f"thresholded material within {corridor_radius} voxels of the "
            "expected strut"
        ),
        "cropBoundsZyx": {
            "lowerInclusive": [int(value) for value in lower],
            "upperExclusive": [int(value) for value in upper],
        },
        "measurements": {
            field: _strict_json_value(row[field]) for field in measurement_fields
        },
        "views": views,
        "rawCtVolumeEmbedded": False,
    }


def get_strut_slice_evidence(
    strut_id: int,
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    crop_size: int = SLICE_CROP_SIZE,
    sample_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Return cached, browser-safe CT slice evidence for one saved strut.

    ``sample_dir`` selects the same artifact run used by the dashboard.  The CT
    path remains configuration-driven (or can be overridden with
    ``LATTICE_CT_RAW_PATH``) and only bounded PNG crops are returned.
    """

    if crop_size < 32 or crop_size > 192:
        raise ValueError("crop_size must be in 32..192 voxels")
    directory = Path(sample_dir) if sample_dir is not None else Path(config.output_dir)
    sample_path = _artifact_file(
        directory,
        (
            "full_strut_classification.csv",
            "sampled_struts.csv",
        ),
    )
    alignment_path = _artifact_file(
        directory,
        (
            "full_alignment.json",
            "alignment.json",
        ),
    )
    ct_path = Path(os.getenv("LATTICE_CT_RAW_PATH", config.ct_path)).expanduser()
    return _cached_slice_evidence(
        int(strut_id),
        str(ct_path.resolve()),
        str(sample_path.resolve()),
        str(alignment_path.resolve()),
        int(crop_size),
        int(config.analysis_search_radius_vox),
    )
