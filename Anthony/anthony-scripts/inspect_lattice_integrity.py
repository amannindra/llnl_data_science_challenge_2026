"""Manually inspect registered lattice struts and junctions in an X-ray CT TIFF.

The results are provisional CT-integrity assessments. They do not determine
whether absent material was intentional or caused by manufacturing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import tifffile
from scipy import ndimage
from skimage.filters import threshold_otsu


DEFAULT_VOXEL_SIZE_UM = 57.74
DESIGN_DIAMETER_UM = 350.0
DESIGN_DIAMETER_VOXELS = DESIGN_DIAMETER_UM / DEFAULT_VOXEL_SIZE_UM
THRESHOLD_FACTORS = (0.95, 1.0, 1.05)
STRUT_STATES = {
    "good",
    "thin_continuous",
    "likely_discontinuous",
    "endpoint_disconnected",
    "uncertain",
}
JUNCTION_STATES = {
    "good",
    "junction_under_fused",
    "junction_enlarged_or_malformed",
    "uncertain",
}


def xyz_to_zyx(points: np.ndarray | Sequence[float]) -> np.ndarray:
    """Convert graph XYZ coordinates to TIFF ZYX coordinate order."""
    return np.asarray(points)[..., ::-1]


def zyx_to_xyz(points: np.ndarray | Sequence[float]) -> np.ndarray:
    """Convert TIFF ZYX coordinates to graph XYZ coordinate order."""
    return np.asarray(points)[..., ::-1]


def validate_requested_ids(
    graph: dict, strut_ids: Iterable[int], junction_ids: Iterable[int]
) -> tuple[list[int], list[int]]:
    """Validate IDs and include both endpoint junctions of requested struts."""
    available_struts = {int(item["id"]): item for item in graph["struts"]}
    available_junctions = {int(item["id"]): item for item in graph["junctions"]}
    requested_struts = sorted(set(map(int, strut_ids)))
    requested_junctions = set(map(int, junction_ids))
    if not requested_struts and not requested_junctions:
        raise ValueError("Supply at least one --strut-ids or --junction-ids value")
    unknown_struts = sorted(set(requested_struts) - set(available_struts))
    unknown_junctions = sorted(requested_junctions - set(available_junctions))
    if unknown_struts:
        raise ValueError(f"Unknown strut IDs: {unknown_struts}")
    if unknown_junctions:
        raise ValueError(f"Unknown junction IDs: {unknown_junctions}")
    for strut_id in requested_struts:
        strut = available_struts[strut_id]
        requested_junctions.update(
            (int(strut["junction0"]), int(strut["junction1"]))
        )
    return requested_struts, sorted(requested_junctions)


def estimate_global_threshold(volume_zyx: np.ndarray, stride: int = 8) -> float:
    """Estimate a material threshold from a bounded, strided volume sample."""
    sample = np.asarray(volume_zyx[::stride, ::stride, ::stride])
    low, high = np.percentile(sample, [0.5, 99.5])
    clipped = sample[(sample >= low) & (sample <= high)]
    if clipped.size == 0 or np.all(clipped == clipped.flat[0]):
        raise ValueError("Cannot estimate a threshold from a constant CT sample")
    return float(threshold_otsu(clipped))


def _orthonormal_basis(direction_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    direction = np.asarray(direction_xyz, dtype=float)
    direction /= np.linalg.norm(direction)
    helper = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(direction, helper))) > 0.85:
        helper = np.array([0.0, 1.0, 0.0])
    first = np.cross(direction, helper)
    first /= np.linalg.norm(first)
    second = np.cross(direction, first)
    return first, second


def _sample_values(volume_zyx: np.ndarray, points_xyz: np.ndarray) -> np.ndarray:
    return ndimage.map_coordinates(
        volume_zyx,
        xyz_to_zyx(points_xyz).reshape(-1, 3).T,
        order=1,
        mode="nearest",
    )


def _ball_offsets(radius: int) -> np.ndarray:
    return np.asarray(
        [
            (x, y, z)
            for z in range(-radius, radius + 1)
            for y in range(-radius, radius + 1)
            for x in range(-radius, radius + 1)
            if x * x + y * y + z * z <= radius * radius
        ],
        dtype=float,
    )


def _centerline_profiles(
    volume_zyx: np.ndarray,
    start_xyz: np.ndarray,
    end_xyz: np.ndarray,
    thresholds: Sequence[float],
    search_radius: int = 2,
) -> dict:
    vector = end_xyz - start_xyz
    length = float(np.linalg.norm(vector))
    count = max(3, int(math.ceil(length * 2.0)) + 1)
    fractions = np.linspace(0.0, 1.0, count)
    points = start_xyz + fractions[:, None] * vector
    offsets = _ball_offsets(search_radius)
    samples = points[:, None, :] + offsets[None, :, :]
    maxima = _sample_values(volume_zyx, samples).reshape(count, len(offsets)).max(1)
    step = length / max(count - 1, 1)
    profiles = {}
    for threshold in thresholds:
        supported = maxima >= threshold
        gap_samples, gap_start = _longest_false_run(supported)
        profiles[float(threshold)] = {
            "supported": supported,
            "continuity": float(supported.mean()),
            "longest_gap_voxels": float(gap_samples * step),
            "gap_center_fraction": (
                float((gap_start + gap_samples / 2) / max(count - 1, 1))
                if gap_samples
                else None
            ),
            "endpoint_0_support": float(supported[: max(3, count // 7)].mean()),
            "endpoint_1_support": float(supported[-max(3, count // 7) :].mean()),
        }
    return {
        "length_voxels": length,
        "fractions": fractions,
        "local_maxima": maxima,
        "threshold_profiles": profiles,
    }


def _longest_false_run(values: np.ndarray) -> tuple[int, int]:
    best_length = current_length = 0
    best_start = current_start = 0
    for index, value in enumerate(values):
        if value:
            current_length = 0
        else:
            if current_length == 0:
                current_start = index
            current_length += 1
            if current_length > best_length:
                best_length = current_length
                best_start = current_start
    return best_length, best_start


def _component_area_near_center(binary_plane: np.ndarray, max_offset: float = 3.0) -> int:
    labels, count = ndimage.label(binary_plane)
    if count == 0:
        return 0
    center = (np.asarray(binary_plane.shape) - 1) / 2
    foreground = np.argwhere(binary_plane)
    distances = np.linalg.norm(foreground - center, axis=1)
    closest = foreground[int(np.argmin(distances))]
    if float(distances.min()) > max_offset:
        return 0
    label = labels[tuple(closest)]
    return int(np.count_nonzero(labels == label))


def sample_strut_cross_sections(
    volume_zyx: np.ndarray,
    start_xyz: Sequence[float],
    end_xyz: Sequence[float],
    threshold: float,
    fractions: np.ndarray | None = None,
    half_width: int = 10,
) -> dict:
    """Measure equivalent diameters on planes normal to a registered strut."""
    start, end = np.asarray(start_xyz, float), np.asarray(end_xyz, float)
    vector = end - start
    direction = vector / np.linalg.norm(vector)
    basis_u, basis_v = _orthonormal_basis(direction)
    if fractions is None:
        fractions = np.linspace(0.1, 0.9, 17)
    grid = np.arange(-half_width, half_width + 1, dtype=float)
    uu, vv = np.meshgrid(grid, grid, indexing="ij")
    centers = start + fractions[:, None] * vector
    planes_xyz = (
        centers[:, None, None, :]
        + uu[None, :, :, None] * basis_u[None, None, None, :]
        + vv[None, :, :, None] * basis_v[None, None, None, :]
    )
    values = _sample_values(volume_zyx, planes_xyz).reshape(
        len(fractions), len(grid), len(grid)
    )
    areas = np.asarray(
        [_component_area_near_center(plane >= threshold) for plane in values]
    )
    diameters = 2.0 * np.sqrt(areas / math.pi)
    return {
        "fractions": np.asarray(fractions),
        "diameters_voxels": diameters,
        "plane_values": values,
        "basis_u": basis_u,
        "basis_v": basis_v,
    }


def classify_strut(
    metrics: dict,
    comparison_median_voxels: float,
    design_diameter_voxels: float = DESIGN_DIAMETER_VOXELS,
) -> tuple[str, float, str]:
    """Assign a provisional strut integrity state from measured evidence."""
    baseline = metrics["threshold_metrics"]["baseline"]
    min_continuity = min(
        item["continuity"] for item in metrics["threshold_metrics"].values()
    )
    gap_persistent = all(
        item["longest_gap_voxels"] >= 2.0
        for item in metrics["threshold_metrics"].values()
    )
    endpoint_0 = min(
        item["endpoint_0_support"] for item in metrics["threshold_metrics"].values()
    )
    endpoint_1 = min(
        item["endpoint_1_support"] for item in metrics["threshold_metrics"].values()
    )
    middle_continuity = float(metrics["middle_continuity"])
    thin_limit = min(0.8 * design_diameter_voxels, 0.8 * comparison_median_voxels)

    if middle_continuity >= 0.85 and (endpoint_0 < 0.70 or endpoint_1 < 0.70):
        confidence = min(0.95, 0.55 + 0.4 * (1.0 - min(endpoint_0, endpoint_1)))
        return (
            "endpoint_disconnected",
            confidence,
            "interior material is present but at least one endpoint has weak persistent support",
        )
    if gap_persistent and baseline["continuity"] < 0.95:
        confidence = min(0.98, 0.65 + baseline["longest_gap_voxels"] / 20.0)
        return (
            "likely_discontinuous",
            confidence,
            "a spatial gap of at least 2 voxels persists across all thresholds",
        )
    if (
        min_continuity >= 0.90
        and endpoint_0 >= 0.70
        and endpoint_1 >= 0.70
        and metrics["median_diameter_voxels"] < thin_limit
    ):
        return (
            "thin_continuous",
            0.75,
            "continuous endpoint-connected material is thinner than the selected and design references",
        )
    if (
        min_continuity >= 0.90
        and baseline["longest_gap_voxels"] < 2.0
        and endpoint_0 >= 0.70
        and endpoint_1 >= 0.70
    ):
        return (
            "good",
            0.80,
            "continuity, thickness, and both endpoint connections are stable",
        )
    return (
        "uncertain",
        0.40,
        "measurements do not meet a stable provisional-state rule",
    )


def analyze_strut(
    volume_zyx: np.ndarray,
    strut: dict,
    positions_by_id: dict[int, np.ndarray],
    baseline_threshold: float,
    voxel_size_um: float,
) -> dict:
    """Measure one registered strut at three thresholds."""
    start = positions_by_id[int(strut["junction0"])]
    end = positions_by_id[int(strut["junction1"])]
    thresholds = [baseline_threshold * factor for factor in THRESHOLD_FACTORS]
    profiles = _centerline_profiles(volume_zyx, start, end, thresholds)
    sections = sample_strut_cross_sections(
        volume_zyx, start, end, baseline_threshold
    )
    diameters = sections["diameters_voxels"]
    baseline_profile = profiles["threshold_profiles"][float(baseline_threshold)]
    count = len(baseline_profile["supported"])
    middle = baseline_profile["supported"][count // 5 : -count // 5]
    threshold_metrics = {}
    for factor, threshold in zip(THRESHOLD_FACTORS, thresholds):
        name = {0.95: "low", 1.0: "baseline", 1.05: "high"}[factor]
        profile = profiles["threshold_profiles"][float(threshold)]
        threshold_metrics[name] = {
            key: value for key, value in profile.items() if key != "supported"
        }
    metrics = {
        "strut_id": int(strut["id"]),
        "junction_0": int(strut["junction0"]),
        "junction_1": int(strut["junction1"]),
        "length_voxels": profiles["length_voxels"],
        "median_diameter_voxels": float(np.median(diameters)),
        "minimum_diameter_voxels": float(np.min(diameters)),
        "maximum_diameter_voxels": float(np.max(diameters)),
        "diameter_std_voxels": float(np.std(diameters)),
        "median_diameter_estimated_um": float(np.median(diameters) * voxel_size_um),
        "minimum_diameter_estimated_um": float(np.min(diameters) * voxel_size_um),
        "middle_continuity": float(middle.mean()) if middle.size else 0.0,
        "threshold_metrics": threshold_metrics,
        "_profile_fractions": profiles["fractions"],
        "_profile_intensities": profiles["local_maxima"],
        "_section_fractions": sections["fractions"],
        "_section_diameters": diameters,
        "_section_values": sections["plane_values"],
        "_start_xyz": start,
        "_end_xyz": end,
    }
    return metrics


def _junction_component_metrics(
    volume_zyx: np.ndarray,
    center_xyz: np.ndarray,
    threshold: float,
    radius: int = 12,
) -> dict:
    shape_xyz = np.asarray(volume_zyx.shape)[::-1]
    low = np.maximum(np.floor(center_xyz - radius).astype(int), 0)
    high = np.minimum(np.ceil(center_xyz + radius + 1).astype(int), shape_xyz)
    low_zyx, high_zyx = xyz_to_zyx(low), xyz_to_zyx(high)
    crop = np.asarray(
        volume_zyx[
            low_zyx[0] : high_zyx[0],
            low_zyx[1] : high_zyx[1],
            low_zyx[2] : high_zyx[2],
        ]
    )
    mask = crop >= threshold
    labels, count = ndimage.label(mask)
    local_center_xyz = center_xyz - low
    foreground_zyx = np.argwhere(mask)
    component = np.zeros_like(mask, dtype=bool)
    if count and foreground_zyx.size:
        local_center_zyx = xyz_to_zyx(local_center_xyz)
        nearest = foreground_zyx[
            np.argmin(np.linalg.norm(foreground_zyx - local_center_zyx, axis=1))
        ]
        component = labels == labels[tuple(nearest)]
    volume_voxels = int(component.sum())
    if volume_voxels:
        coordinates_xyz = zyx_to_xyz(np.argwhere(component)).astype(float)
        centroid = coordinates_xyz.mean(0)
        radii = np.linalg.norm(coordinates_xyz - centroid, axis=1)
        radial_asymmetry = float(np.std(radii) / max(np.mean(radii), 1e-6))
        bbox = np.ptp(coordinates_xyz, axis=0) + 1
        compactness = float(volume_voxels / np.prod(bbox))
    else:
        radial_asymmetry = 1.0
        compactness = 0.0
    equivalent_diameter = (
        2.0 * (3.0 * volume_voxels / (4.0 * math.pi)) ** (1.0 / 3.0)
        if volume_voxels
        else 0.0
    )
    return {
        "crop": crop,
        "component": component,
        "crop_origin_xyz": low,
        "component_volume_voxels": volume_voxels,
        "equivalent_diameter_voxels": float(equivalent_diameter),
        "compactness": compactness,
        "radial_asymmetry": radial_asymmetry,
    }


def analyze_junction(
    volume_zyx: np.ndarray,
    junction_id: int,
    positions_by_id: dict[int, np.ndarray],
    struts_by_id: dict[int, dict],
    incident_by_junction: dict[int, list[int]],
    baseline_threshold: float,
    voxel_size_um: float,
) -> dict:
    """Measure branch support and local morphology for one junction."""
    center = positions_by_id[junction_id]
    incident_ids = sorted(incident_by_junction[junction_id])
    thresholds = [baseline_threshold * factor for factor in THRESHOLD_FACTORS]
    branch_support: dict[int, dict[str, float]] = {}
    for strut_id in incident_ids:
        strut = struts_by_id[strut_id]
        other_id = (
            int(strut["junction1"])
            if int(strut["junction0"]) == junction_id
            else int(strut["junction0"])
        )
        other = positions_by_id[other_id]
        near_end = center + 0.22 * (other - center)
        profile = _centerline_profiles(
            volume_zyx, center, near_end, thresholds, search_radius=2
        )
        branch_support[strut_id] = {
            name: profile["threshold_profiles"][float(threshold)]["continuity"]
            for name, threshold in zip(("low", "baseline", "high"), thresholds)
        }
    supported = sum(
        min(values.values()) >= 0.70 for values in branch_support.values()
    )
    component = _junction_component_metrics(
        volume_zyx, center, baseline_threshold
    )
    return {
        "junction_id": junction_id,
        "expected_degree": len(incident_ids),
        "incident_strut_ids": incident_ids,
        "supported_branches": int(supported),
        "branch_support": branch_support,
        "component_volume_voxels": component["component_volume_voxels"],
        "equivalent_diameter_voxels": component["equivalent_diameter_voxels"],
        "equivalent_diameter_estimated_um": (
            component["equivalent_diameter_voxels"] * voxel_size_um
        ),
        "compactness": component["compactness"],
        "radial_asymmetry": component["radial_asymmetry"],
        "_center_xyz": center,
        "_crop": component["crop"],
        "_component": component["component"],
        "_crop_origin_xyz": component["crop_origin_xyz"],
    }


def assign_junction_states(rows: list[dict]) -> None:
    """Assign provisional junction states using selected same-degree peers."""
    peers: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        peers[int(row["expected_degree"])].append(row)
    for row in rows:
        if row["supported_branches"] < row["expected_degree"]:
            missing = row["expected_degree"] - row["supported_branches"]
            row["integrity_state"] = "junction_under_fused"
            row["confidence"] = min(0.95, 0.65 + 0.08 * missing)
            row["state_reason"] = (
                f"{missing} of {row['expected_degree']} expected branches lack stable support"
            )
            row["morphology_comparison_available"] = len(
                peers[row["expected_degree"]]
            ) >= 3
            continue
        same_degree = peers[row["expected_degree"]]
        comparison_available = len(same_degree) >= 3
        row["morphology_comparison_available"] = comparison_available
        malformed = False
        if comparison_available:
            for key in (
                "component_volume_voxels",
                "equivalent_diameter_voxels",
                "radial_asymmetry",
            ):
                values = np.asarray([item[key] for item in same_degree], float)
                median = float(np.median(values))
                mad = float(np.median(np.abs(values - median)))
                scale = 1.4826 * mad
                if scale <= 1e-6:
                    scale = max(float(np.std(values)), 1e-6)
                if (row[key] - median) / scale > 2.5:
                    malformed = True
        if malformed:
            row["integrity_state"] = "junction_enlarged_or_malformed"
            row["confidence"] = 0.70
            row["state_reason"] = (
                "size or asymmetry is a high outlier among selected same-degree junctions"
            )
        else:
            row["integrity_state"] = "good"
            row["confidence"] = 0.75 if comparison_available else 0.60
            row["state_reason"] = (
                "all expected branches have stable support; morphology comparison "
                + ("was available" if comparison_available else "was unavailable")
            )


def _public_strut_row(metrics: dict) -> dict:
    baseline = metrics["threshold_metrics"]["baseline"]
    return {
        "strut_id": metrics["strut_id"],
        "junction_0": metrics["junction_0"],
        "junction_1": metrics["junction_1"],
        "integrity_state": metrics["integrity_state"],
        "confidence": metrics["confidence"],
        "state_reason": metrics["state_reason"],
        "length_voxels": metrics["length_voxels"],
        "median_diameter_voxels": metrics["median_diameter_voxels"],
        "minimum_diameter_voxels": metrics["minimum_diameter_voxels"],
        "maximum_diameter_voxels": metrics["maximum_diameter_voxels"],
        "diameter_std_voxels": metrics["diameter_std_voxels"],
        "median_diameter_estimated_um": metrics["median_diameter_estimated_um"],
        "minimum_diameter_estimated_um": metrics["minimum_diameter_estimated_um"],
        "continuity": baseline["continuity"],
        "longest_gap_voxels": baseline["longest_gap_voxels"],
        "gap_center_fraction": baseline["gap_center_fraction"],
        "endpoint_0_support": baseline["endpoint_0_support"],
        "endpoint_1_support": baseline["endpoint_1_support"],
        "low_threshold_continuity": metrics["threshold_metrics"]["low"]["continuity"],
        "high_threshold_continuity": metrics["threshold_metrics"]["high"]["continuity"],
        "uncertainty": (
            "provisional CT-integrity state; micron values use design-derived calibration"
        ),
    }


def _public_junction_row(row: dict) -> dict:
    return {
        "junction_id": row["junction_id"],
        "expected_degree": row["expected_degree"],
        "incident_strut_ids": ";".join(map(str, row["incident_strut_ids"])),
        "supported_branches": row["supported_branches"],
        "integrity_state": row["integrity_state"],
        "confidence": row["confidence"],
        "state_reason": row["state_reason"],
        "component_volume_voxels": row["component_volume_voxels"],
        "equivalent_diameter_voxels": row["equivalent_diameter_voxels"],
        "equivalent_diameter_estimated_um": row[
            "equivalent_diameter_estimated_um"
        ],
        "compactness": row["compactness"],
        "radial_asymmetry": row["radial_asymmetry"],
        "morphology_comparison_available": row[
            "morphology_comparison_available"
        ],
        "branch_support": json.dumps(row["branch_support"], sort_keys=True),
        "uncertainty": (
            "provisional CT-integrity state; morphology is relative to selected same-degree IDs"
        ),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _save_strut_panel(
    path: Path,
    volume_zyx: np.ndarray,
    metrics: dict,
    threshold: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    start, end = metrics["_start_xyz"], metrics["_end_xyz"]
    vector = end - start
    direction = vector / np.linalg.norm(vector)
    basis_u, basis_v = _orthonormal_basis(direction)
    along = np.linspace(-5, np.linalg.norm(vector) + 5, 160)
    lateral = np.linspace(-12, 12, 61)
    longitudinal_xyz = (
        start[None, None, :]
        + along[:, None, None] * direction
        + lateral[None, :, None] * basis_u
    )
    longitudinal = _sample_values(volume_zyx, longitudinal_xyz).reshape(
        len(along), len(lateral)
    )
    midpoint = (start + end) / 2
    half = 18
    low = np.maximum(np.floor(midpoint - half).astype(int), 0)
    high = np.minimum(
        np.ceil(midpoint + half + 1).astype(int), np.asarray(volume_zyx.shape)[::-1]
    )
    lo, hi = xyz_to_zyx(low), xyz_to_zyx(high)
    crop = np.asarray(volume_zyx[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]])

    fig = plt.figure(figsize=(15, 9))
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.imshow(longitudinal.T, cmap="gray", aspect="auto")
    ax1.contour((longitudinal >= threshold).T, levels=[0.5], colors="red", linewidths=0.5)
    ax1.set_title("Longitudinal CT view")
    ax1.set_xlabel("Position along registered strut")
    ax1.set_ylabel("Perpendicular offset")

    ax2 = fig.add_subplot(2, 3, 2)
    indexes = [3, len(metrics["_section_values"]) // 2, -4]
    combined = np.concatenate([metrics["_section_values"][index] for index in indexes], axis=1)
    ax2.imshow(combined, cmap="gray")
    ax2.contour(combined >= threshold, levels=[0.5], colors="cyan", linewidths=0.6)
    ax2.set_title("Cross-sections at 25%, 50%, 75%")
    ax2.axis("off")

    ax3 = fig.add_subplot(2, 3, 3)
    ax3.plot(
        metrics["_section_fractions"],
        metrics["_section_diameters"],
        marker="o",
        label="measured",
    )
    ax3.axhline(DESIGN_DIAMETER_VOXELS, color="black", linestyle="--", label="350 µm design")
    ax3.set_xlabel("Position along strut")
    ax3.set_ylabel("Equivalent diameter (voxels)")
    ax3.legend()
    ax3.set_title("Thickness profile")

    ax4 = fig.add_subplot(2, 3, 4)
    ax4.plot(metrics["_profile_fractions"], metrics["_profile_intensities"])
    for factor in THRESHOLD_FACTORS:
        ax4.axhline(threshold * factor, linestyle="--", label=f"{factor:.2f}× threshold")
    ax4.set_xlabel("Position along strut")
    ax4.set_ylabel("Local maximum CT intensity")
    ax4.legend(fontsize=8)
    ax4.set_title("Continuity evidence")

    ax5 = fig.add_subplot(2, 3, 5)
    ax5.imshow(crop.max(axis=0), cmap="gray")
    ax5.set_title("Local Z maximum projection")
    ax5.axis("off")

    ax6 = fig.add_subplot(2, 3, 6, projection="3d")
    points_zyx = np.argwhere(crop >= threshold)
    if len(points_zyx) > 5000:
        points_zyx = points_zyx[:: max(1, len(points_zyx) // 5000)]
    if len(points_zyx):
        points_xyz = zyx_to_xyz(points_zyx)
        ax6.scatter(*points_xyz.T, s=1, alpha=0.12)
    ax6.set_title("Local thresholded CT material")
    ax6.set_axis_off()

    fig.suptitle(
        f"Strut {metrics['strut_id']}: {metrics['integrity_state']} "
        f"(confidence {metrics['confidence']:.2f})\n{metrics['state_reason']}"
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_junction_panel(
    path: Path, row: dict, positions_by_id: dict[int, np.ndarray]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    crop = row["_crop"]
    component = row["_component"]
    centers = np.asarray(crop.shape) // 2
    fig = plt.figure(figsize=(14, 8))
    views = [
        (crop[centers[0]], component[centers[0]], "XY slice"),
        (crop[:, centers[1], :], component[:, centers[1], :], "XZ slice"),
        (crop[:, :, centers[2]], component[:, :, centers[2]], "YZ slice"),
    ]
    for index, (image, mask, title) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 3, index)
        ax.imshow(image, cmap="gray")
        ax.contour(mask, levels=[0.5], colors="orange", linewidths=0.7)
        ax.set_title(title)
        ax.axis("off")

    ax4 = fig.add_subplot(2, 3, 4)
    ids = list(row["branch_support"])
    support = [row["branch_support"][item]["baseline"] for item in ids]
    ax4.bar(range(len(ids)), support)
    ax4.axhline(0.70, color="red", linestyle="--")
    ax4.set_xticks(range(len(ids)), ids, rotation=70, fontsize=7)
    ax4.set_ylim(0, 1.05)
    ax4.set_title("Incident branch support")
    ax4.set_ylabel("Continuity")

    ax5 = fig.add_subplot(2, 3, 5)
    ax5.axis("off")
    ax5.text(
        0,
        1,
        "\n".join(
            [
                f"Expected degree: {row['expected_degree']}",
                f"Supported branches: {row['supported_branches']}",
                f"Component volume: {row['component_volume_voxels']} voxels",
                f"Equivalent size: {row['equivalent_diameter_voxels']:.2f} voxels",
                f"Compactness: {row['compactness']:.3f}",
                f"Radial asymmetry: {row['radial_asymmetry']:.3f}",
                f"Peer comparison: {row['morphology_comparison_available']}",
            ]
        ),
        va="top",
        family="monospace",
    )

    ax6 = fig.add_subplot(2, 3, 6, projection="3d")
    points = np.argwhere(component)
    if len(points) > 5000:
        points = points[:: max(1, len(points) // 5000)]
    if len(points):
        xyz = zyx_to_xyz(points)
        ax6.scatter(*xyz.T, s=2, alpha=0.2)
    ax6.set_title("Connected local junction material")
    ax6.set_axis_off()

    fig.suptitle(
        f"Junction {row['junction_id']}: {row['integrity_state']} "
        f"(confidence {row['confidence']:.2f})\n{row['state_reason']}"
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _write_report(
    path: Path,
    config: dict,
    strut_rows: list[dict],
    junction_rows: list[dict],
) -> None:
    strut_counts = defaultdict(int)
    junction_counts = defaultdict(int)
    for row in strut_rows:
        strut_counts[row["integrity_state"]] += 1
    for row in junction_rows:
        junction_counts[row["integrity_state"]] += 1
    lines = [
        "# Manual Strut and Junction Integrity Report",
        "",
        "## Inputs and calibration",
        "",
        f"- TIFF: `{config['tiff_path']}`",
        f"- Registered graph: `{config['registered_json_path']}`",
        f"- CT material threshold: {config['baseline_threshold']:.3f}",
        f"- Estimated voxel size: {config['voxel_size_um']:.3f} µm/voxel",
        f"- Design diameter reference: {config['design_diameter_voxels']:.3f} voxels (350 µm)",
        "- Micron values are design-derived estimates, not independently calibrated TIFF metadata.",
        "",
        "## Requested structures",
        "",
        f"- Strut IDs: {config['strut_ids']}",
        f"- Junction IDs, including automatic endpoints: {config['junction_ids']}",
        "",
        "## Provisional strut states",
        "",
    ]
    lines.extend(
        f"- `{state}`: {count}" for state, count in sorted(strut_counts.items())
    )
    lines.extend(["", "## Provisional junction states", ""])
    lines.extend(
        f"- `{state}`: {count}" for state, count in sorted(junction_counts.items())
    )
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "- [Strut measurements](strut_integrity.csv)",
            "- [Junction measurements](junction_integrity.csv)",
            "- [Run configuration](run_config.json)",
            "- Diagnostic panels are under [`evidence/`](evidence/).",
            "",
            "## Interpretation limits",
            "",
            "- States are provisional descriptions of CT integrity, not validated defect labels.",
            "- This workflow cannot distinguish intentional removal from a printing defect.",
            "- Thickness depends on segmentation threshold, partial-volume effects, and registration.",
            "- Junction morphology is compared only among selected junctions of equal expected degree.",
            "- Fewer than three equal-degree selected junctions prevents relative malformed-size assessment.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_inspection(
    tiff_path: str | Path,
    registered_json_path: str | Path,
    output_dir: str | Path,
    strut_ids: Iterable[int] = (),
    junction_ids: Iterable[int] = (),
    threshold: float | None = None,
    voxel_size_um: float = DEFAULT_VOXEL_SIZE_UM,
    overwrite: bool = False,
) -> dict:
    """Run manual-ID inspection and write measurements, panels, and report."""
    tiff_path = Path(tiff_path).resolve()
    graph_path = Path(registered_json_path).resolve()
    output_dir = Path(output_dir).resolve()
    if not tiff_path.is_file() or not graph_path.is_file():
        raise FileNotFoundError("The TIFF and registered JSON must both exist")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    selected_struts, selected_junctions = validate_requested_ids(
        graph, strut_ids, junction_ids
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}; use --overwrite"
            )
        shutil.rmtree(output_dir)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    volume = tifffile.memmap(tiff_path)
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D TIFF, found {volume.shape}")
    baseline_threshold = (
        float(threshold) if threshold is not None else estimate_global_threshold(volume)
    )
    positions = {
        int(item["id"]): np.asarray(item["position"], dtype=float)
        for item in graph["junctions"]
    }
    if any(
        np.any(position < 0)
        or np.any(xyz_to_zyx(position) >= np.asarray(volume.shape))
        for position in positions.values()
    ):
        raise ValueError("Registered graph contains junctions outside the TIFF")
    struts = {int(item["id"]): item for item in graph["struts"]}
    incident: dict[int, list[int]] = defaultdict(list)
    for strut in graph["struts"]:
        incident[int(strut["junction0"])].append(int(strut["id"]))
        incident[int(strut["junction1"])].append(int(strut["id"]))

    strut_metrics = [
        analyze_strut(
            volume,
            struts[strut_id],
            positions,
            baseline_threshold,
            voxel_size_um,
        )
        for strut_id in selected_struts
    ]
    comparison_median = (
        float(np.median([row["median_diameter_voxels"] for row in strut_metrics]))
        if strut_metrics
        else DESIGN_DIAMETER_UM / voxel_size_um
    )
    for row in strut_metrics:
        state, confidence, reason = classify_strut(
            row,
            comparison_median,
            design_diameter_voxels=DESIGN_DIAMETER_UM / voxel_size_um,
        )
        row["integrity_state"] = state
        row["confidence"] = confidence
        row["state_reason"] = reason

    junction_metrics = [
        analyze_junction(
            volume,
            junction_id,
            positions,
            struts,
            incident,
            baseline_threshold,
            voxel_size_um,
        )
        for junction_id in selected_junctions
    ]
    assign_junction_states(junction_metrics)

    public_struts = [_public_strut_row(row) for row in strut_metrics]
    public_junctions = [_public_junction_row(row) for row in junction_metrics]
    _write_csv(output_dir / "strut_integrity.csv", public_struts)
    _write_csv(output_dir / "junction_integrity.csv", public_junctions)
    for row in strut_metrics:
        _save_strut_panel(
            evidence_dir / f"strut_{row['strut_id']}_panel.png",
            volume,
            row,
            baseline_threshold,
        )
    for row in junction_metrics:
        _save_junction_panel(
            evidence_dir / f"junction_{row['junction_id']}_panel.png",
            row,
            positions,
        )

    config = {
        "tiff_path": str(tiff_path),
        "registered_json_path": str(graph_path),
        "output_dir": str(output_dir),
        "strut_ids": selected_struts,
        "junction_ids": selected_junctions,
        "baseline_threshold": baseline_threshold,
        "threshold_factors": list(THRESHOLD_FACTORS),
        "voxel_size_um": voxel_size_um,
        "voxel_calibration": "design-derived estimate",
        "design_diameter_um": DESIGN_DIAMETER_UM,
        "design_diameter_voxels": DESIGN_DIAMETER_UM / voxel_size_um,
        "coordinate_conventions": {"registered_graph": "XYZ", "tiff": "ZYX"},
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    _write_report(output_dir / "REPORT.md", config, public_struts, public_junctions)
    required = {
        "strut_integrity.csv",
        "junction_integrity.csv",
        "run_config.json",
        "REPORT.md",
    }
    missing = [name for name in required if not (output_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing outputs: {missing}")
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiff", required=True, type=Path)
    parser.add_argument("--registered-json", required=True, type=Path)
    parser.add_argument("--strut-ids", nargs="*", type=int, default=[])
    parser.add_argument("--junction-ids", nargs="*", type=int, default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--threshold", type=float)
    parser.add_argument(
        "--voxel-size-um", type=float, default=DEFAULT_VOXEL_SIZE_UM
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = run_inspection(
        args.tiff,
        args.registered_json,
        args.output_dir,
        strut_ids=args.strut_ids,
        junction_ids=args.junction_ids,
        threshold=args.threshold,
        voxel_size_um=args.voxel_size_um,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
