"""Render auditable orthogonal projections and analyze the written PNGs."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "llnl-matplotlib-cache"))

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from .synthetic_cases import VisualCase


FIGURE_PIXELS = (1200, 900)


def _decision_label(value: bool | None) -> str:
    if value is True:
        return "ERROR"
    if value is False:
        return "HEALTHY"
    return "REVIEW"


def _show_projection(
    axis: Any,
    image: np.ndarray,
    start_ab: tuple[float, float],
    end_ab: tuple[float, float],
    title: str,
    labels: tuple[str, str],
) -> None:
    minimum = float(np.min(image))
    maximum = float(np.max(image))
    # Most fixtures have a true zero background and retain the physical
    # zero-to-maximum display.  A deliberately near-threshold background
    # fixture occupies the entire field; min/max normalization makes its tiny
    # deterministic noise visible without changing any numerical comparison.
    if minimum > 0.0 and maximum > minimum:
        normalized = (image - minimum) / (maximum - minimum)
    else:
        normalized = image / maximum if maximum > 0.0 else image
    axis.imshow(normalized, origin="lower", cmap="gray", vmin=0.0, vmax=1.0,
                interpolation="nearest")
    axis.plot([start_ab[0], end_ab[0]], [start_ab[1], end_ab[1]],
              color="#00e5ff", linewidth=2.0, linestyle="--", label="STL centerline")
    axis.scatter([start_ab[0], end_ab[0]], [start_ab[1], end_ab[1]],
                 c=["#39ff14", "#ffea00"], s=28, edgecolors="black", linewidths=0.5)
    axis.set_title(f"{title}\ndisplay range [{minimum:.3g}, {maximum:.3g}]")
    axis.set_xlabel(labels[0])
    axis.set_ylabel(labels[1])
    axis.set_xlim(-0.5, image.shape[1] - 0.5)
    axis.set_ylim(-0.5, image.shape[0] - 0.5)


def render_case(case: VisualCase, result: Mapping[str, Any], path: Path) -> Path:
    """Write one four-panel evidence image with no hidden interpolation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    start = case.endpoint0_xyz
    end = case.endpoint1_xyz
    volume = case.volume_zyx
    figure, axes = plt.subplots(2, 2, figsize=(12, 9), dpi=100)
    _show_projection(axes[0, 0], volume.max(axis=0), (start[0], start[1]),
                     (end[0], end[1]), "XY maximum projection", ("x", "y"))
    _show_projection(axes[0, 1], volume.max(axis=1), (start[0], start[2]),
                     (end[0], end[2]), "XZ maximum projection", ("x", "z"))
    _show_projection(axes[1, 0], volume.max(axis=2), (start[1], start[2]),
                     (end[1], end[2]), "YZ maximum projection", ("y", "z"))

    profile_axis = axes[1, 1]
    realized = result.get("realized_profile")
    if isinstance(realized, list) and realized:
        values = np.asarray(realized, dtype=float)
        profile_axis.plot([0, len(values) - 1], [1, 1], color="#00acc1",
                          linestyle="--", linewidth=1.7, label="STL expected",
                          zorder=1)
        profile_axis.step(np.arange(len(values)), values, where="mid",
                          color="#e91e63", linewidth=2.2, label="CT realized",
                          zorder=3)
        contrast = result.get("local_contrast_profile")
        if isinstance(contrast, list) and len(contrast) == len(values):
            contrast_values = np.asarray(contrast, dtype=float)
            profile_axis.step(
                np.arange(len(contrast_values)),
                contrast_values,
                where="mid",
                color="#43a047",
                linewidth=1.8,
                linestyle=":",
                label="local contrast support",
                zorder=4,
            )
        profile_axis.set_xlim(0, max(1, len(values) - 1))
        profile_axis.set_ylim(-0.08, 1.15)
        profile_axis.set_xlabel("axial bin")
        profile_axis.set_ylabel("material supported")
        profile_axis.legend(loc="lower left", fontsize=8)
    else:
        profile_axis.text(0.5, 0.5, "No valid axial profile\n(unobservable)",
                          ha="center", va="center", transform=profile_axis.transAxes)
        profile_axis.set_xticks([])
        profile_axis.set_yticks([])
    profile_axis.set_title("Comparator evidence")
    expected = _decision_label(case.expected_has_error)
    actual = _decision_label(result.get("has_error"))
    outcome_match = result.get("has_error") is case.expected_has_error
    metrics = (
        f"expected={expected}  actual={actual}  match={outcome_match}\n"
        f"realized={result.get('realized_axial_fraction')}  "
        f"contrast={result.get('local_contrast_realized_fraction')}  "
        f"gap={result.get('longest_unrealized_gap_voxels')}  "
        f"agreement={result.get('perturbation_agreement')}\n"
        f"reason={result.get('decision_reason')}"
    )
    profile_axis.text(0.02, 0.97, metrics, transform=profile_axis.transAxes,
                      ha="left", va="top", fontsize=8,
                      bbox={"facecolor": "white", "alpha": 0.86, "edgecolor": "#777777"})
    banner = "#2e7d32" if outcome_match else "#c62828"
    figure.suptitle(
        f"{case.case_id}: {case.description}\n"
        f"physical truth={_decision_label(case.physical_has_error)} | "
        f"expected response={expected} | actual response={actual}",
        color="white", backgroundcolor=banner, fontsize=13,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.92))
    figure.savefig(path, dpi=100, facecolor="white", metadata={"Software": "LLNL visual tests"})
    plt.close(figure)
    return path


def analyze_png(path: Path) -> dict[str, Any]:
    """Reopen a PNG and record objective evidence that rendering succeeded."""

    payload = path.read_bytes()
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        dimensions = list(image.size)
    channel_standard_deviation = [float(np.std(rgb[..., channel])) for channel in range(3)]
    nonwhite = np.any(rgb < 250, axis=2)
    cyan_overlay = (
        (rgb[..., 0] < 80) & (rgb[..., 1] > 150) & (rgb[..., 2] > 180)
    )
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "dimensions_xy": dimensions,
        "mode": "RGB",
        "channel_standard_deviation": channel_standard_deviation,
        "nonwhite_pixel_fraction": float(np.mean(nonwhite)),
        "cyan_stl_overlay_pixel_count": int(np.count_nonzero(cyan_overlay)),
        "visual_checks_pass": bool(
            dimensions == list(FIGURE_PIXELS)
            and len(payload) > 20_000
            and min(channel_standard_deviation) > 20.0
            and float(np.mean(nonwhite)) > 0.05
            and int(np.count_nonzero(cyan_overlay)) > 50
        ),
    }


def build_contact_sheet(case_paths: list[Path], output_path: Path) -> Path:
    """Combine every case into a deterministic review sheet."""

    columns = 3
    thumbnail_size = (400, 300)
    rows = (len(case_paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumbnail_size[0], rows * thumbnail_size[1]), "white")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(case_paths):
        with Image.open(path) as image:
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
            x = (index % columns) * thumbnail_size[0]
            y = (index // columns) * thumbnail_size[1]
            sheet.paste(thumbnail, (x, y))
            draw.rectangle((x, y, x + thumbnail_size[0] - 1, y + thumbnail_size[1] - 1),
                           outline="#303030", width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG", optimize=False)
    return output_path


__all__ = ["FIGURE_PIXELS", "analyze_png", "build_contact_sheet", "render_case"]
