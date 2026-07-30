"""Bounded rendered CT evidence for one registered lattice strut."""

from __future__ import annotations

import hashlib
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from matplotlib.colors import ListedColormap

from .core.config import DEFAULT_CONFIG, DefectConfig


MAX_CROP_RADIUS_VOXELS = 64
DEFAULT_CROP_RADIUS_VOXELS = 24


def _bounded_int(value: int, name: str, *, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if not lower <= value <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return value


def _bounds(center: float, radius: int, size: int) -> tuple[int, int]:
    midpoint = int(round(float(center)))
    return max(0, midpoint - radius), min(size, midpoint + radius + 1)


def _display_limits(image: np.ndarray) -> tuple[float, float]:
    values = np.asarray(image, dtype=np.float32)
    low, high = np.percentile(values, [1.0, 99.5])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(np.min(values))
        high = float(np.max(values))
    if high <= low:
        high = low + 1.0
    return float(low), float(high)


def _panel(
    axis: plt.Axes,
    image: np.ndarray,
    mask: np.ndarray | None,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
) -> None:
    low, high = _display_limits(image)
    axis.imshow(image, cmap="gray", vmin=low, vmax=high, origin="upper")
    if mask is not None and np.any(mask):
        overlay = np.ma.masked_where(~mask.astype(bool), mask)
        axis.imshow(
            overlay,
            cmap=ListedColormap([(0.1, 0.8, 0.35, 0.42)]),
            interpolation="nearest",
            origin="upper",
        )
    midpoint_y = (image.shape[0] - 1) / 2.0
    midpoint_x = (image.shape[1] - 1) / 2.0
    axis.axhline(midpoint_y, color="#ef4444", linewidth=0.8, alpha=0.8)
    axis.axvline(midpoint_x, color="#ef4444", linewidth=0.8, alpha=0.8)
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    axis.set_aspect("equal")


def _load_record(config: DefectConfig, strut_id: int) -> dict[str, Any]:
    table_path = config.dashboard_table_path
    if not table_path.is_file():
        raise FileNotFoundError(f"Full classification artifact is missing: {table_path}")
    table = pd.read_csv(table_path, usecols=[
        "strut_id", "prediction", "mid_z", "mid_y", "mid_x",
    ])
    rows = table.loc[table["strut_id"] == int(strut_id)]
    if rows.empty:
        raise ValueError(f"Strut {strut_id} is not present in the full registered lattice")
    return rows.iloc[0].to_dict()


def render_strut_ct_evidence(
    strut_id: int,
    *,
    crop_radius_voxels: int = DEFAULT_CROP_RADIUS_VOXELS,
    config: DefectConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Render three orthogonal raw-CT views with the Otsu mask overlaid."""

    strut_id = _bounded_int(strut_id, "strut_id", lower=0, upper=18_467)
    crop_radius_voxels = _bounded_int(
        crop_radius_voxels,
        "crop_radius_voxels",
        lower=8,
        upper=MAX_CROP_RADIUS_VOXELS,
    )
    record = _load_record(config, strut_id)
    ct_path = config.ct_path
    mask_path = config.otsu_mask_path
    if not ct_path.is_file():
        raise FileNotFoundError(f"Raw CT TIFF is missing: {ct_path}")
    if not mask_path.is_file():
        raise FileNotFoundError(f"Otsu mask TIFF is missing: {mask_path}")

    volume_zyx = tifffile.memmap(ct_path, mode="r")
    mask_zyx = tifffile.memmap(mask_path, mode="r")
    try:
        if volume_zyx.shape != mask_zyx.shape:
            raise ValueError(
                f"Raw CT and Otsu mask shapes differ: {volume_zyx.shape} vs {mask_zyx.shape}"
            )
        z, y, x = (
            float(record["mid_z"]),
            float(record["mid_y"]),
            float(record["mid_x"]),
        )
        z0, z1 = _bounds(z, crop_radius_voxels, volume_zyx.shape[0])
        y0, y1 = _bounds(y, crop_radius_voxels, volume_zyx.shape[1])
        x0, x1 = _bounds(x, crop_radius_voxels, volume_zyx.shape[2])
        panels = [
            (volume_zyx[int(round(z)), y0:y1, x0:x1], mask_zyx[int(round(z)), y0:y1, x0:x1], "Axial · z", "x", "y"),
            (volume_zyx[z0:z1, int(round(y)), x0:x1], mask_zyx[z0:z1, int(round(y)), x0:x1], "Coronal · y", "x", "z"),
            (volume_zyx[z0:z1, y0:y1, int(round(x))], mask_zyx[z0:z1, y0:y1, int(round(x))], "Sagittal · x", "y", "z"),
        ]
        output_dir = config.ct_evidence_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / f"strut_{strut_id}_r{crop_radius_voxels}.png"
        if not image_path.is_file():
            figure, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), constrained_layout=True)
            for axis, (image, mask, title, xlabel, ylabel) in zip(axes, panels):
                _panel(axis, image, mask, title=title, xlabel=xlabel, ylabel=ylabel)
            figure.suptitle(
                f"Strut {strut_id} · {record['prediction']} · red = expected midpoint, green = Otsu material",
                fontsize=12,
            )
            temporary = image_path.with_suffix(".tmp.png")
            figure.savefig(temporary, dpi=140, facecolor="white")
            plt.close(figure)
            temporary.replace(image_path)
    finally:
        del volume_zyx
        del mask_zyx

    payload = {
        "status": "ct_evidence_ready",
        "strut_id": strut_id,
        "prediction": str(record["prediction"]),
        "image_path": str(image_path),
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "center_zyx": [float(record["mid_z"]), float(record["mid_y"]), float(record["mid_x"])],
        "crop_radius_voxels": crop_radius_voxels,
        "voxel_pitch_um": float(config.voxel_spacing_um[0]),
        "raw_ct_included": False,
        "rendered_evidence_only": True,
        "interpretation": "Green overlay is Otsu-segmented material; red crosshairs mark the expected strut midpoint.",
    }
    return payload
