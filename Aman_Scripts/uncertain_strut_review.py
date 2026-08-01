"""Sample, render, and record human review verdicts for uncertain struts.

Reads the automated full-lattice classification, samples struts still labeled
"uncertain" that have not yet been reviewed, and renders raw-TIFF evidence
panels: three orthogonal maximum-intensity projections of a local crop around
the strut, with the registered expected centerline overlaid in red. Because
every strut's orientation has exactly one zero-delta axis (it lies flat in one
of the three projection planes), at least one of the three panels always shows
the full strut with zero foreshortening. A local 3D point-cloud render is also
available (`--formats 3d` or `both`) for the rare case where the flat
projections are not enough to decide (see strut 1523 in
`human_review_labels.csv` for a documented example).

The renderer never uses the segmented TIFF for the image texture; only the raw
native TIFF, read lazily via `tifffile.memmap`. Verdicts are appended to the
CSV that `defect_cartographer.core.full_results._apply_human_review_overrides`
reads (`strut_id,human_label,review_note,reviewer`), one row per strut,
duplicates rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile

from Components.ct_surface_metrology import trilinear_sample
from Components.strut_metrology import (
    _cross_section_frame,
    _select_seeded_material_component,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = ROOT / "part2/artifacts/sample/full_strut_classification.csv"
DEFAULT_TIFF = ROOT / (
    "data/missing_struts/tif_stacks/"
    "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
)
DEFAULT_OUTPUT = ROOT / "Aman_Scripts/outputs/uncertain_strut_review"
DEFAULT_HUMAN_REVIEW = (
    ROOT / "Aman_Scripts/outputs/strut_defect_classification/human_review_labels.csv"
)
DEFAULT_IDS = (11, 6754, 1775, 14755, 1523)

CLASSIFICATION_LABELS = (
    "healthy",
    "missing",
    "broken",
    "thin",
    "thick",
    "bent_or_misaligned",
    "uncertain",
    "not_applicable",
)

REVIEW_LABEL_MENU = {
    "healthy": "Continuous strut, correct thickness, no defect visible.",
    "missing": "No material present anywhere along the expected centerline.",
    "broken": (
        "Material is present but the centerline is disconnected somewhere along "
        "its length (a real internal/partial gap, not just absent everywhere)."
    ),
    "thin": "Continuous strut, but visibly under-diameter versus neighboring struts.",
    "thick": "Continuous strut, but visibly over-diameter versus neighboring struts.",
    "bent_or_misaligned": (
        "Continuous strut whose centerline is visibly offset from the red "
        "registered/expected line — plausibly a real bend, or just registration "
        "error; use judgment from the image."
    ),
    "uncertain": (
        "Still genuinely ambiguous after this review (e.g. needs the 3D view or a "
        "deeper look) — leave it for a later pass rather than guessing."
    ),
    "not_applicable": (
        "The expected strut position is intentionally absent from the design "
        "(e.g. exterior scaffold/build plate artifact), not a manufacturing defect."
    ),
}


def _uncertainty_explanation(row: pd.Series) -> str:
    reason = str(row.classification_reason)
    gap = float(row.longest_unsupported_gap_voxels)
    disp = float(row.p90_centerline_displacement_voxels)
    occ = float(row.observed_axial_fraction)
    supported = bool(row.connected_support)
    tiff_valid = bool(row.tiff_measurement_valid) if not pd.isna(row.tiff_measurement_valid) else False
    thickness = None if pd.isna(row.thickness_um_median) else float(row.thickness_um_median)

    if reason == "measurements_near_a_declared_tolerance":
        detail = (
            f"axial support {occ:.0%}, connected={supported}, longest gap {gap:.1f} vox, "
            f"centerline offset p90 {disp:.2f} vox"
        )
        if thickness is not None:
            detail += f", measured thickness {thickness:.0f} um"
        return (
            "Automated rule: deterministic measurements sit close enough to the "
            f"declared tolerance band that the classifier could not confidently call "
            f"healthy vs. a defect ({detail}). Look for a visible gap, thinning/"
            "thickening, or centerline offset in the image."
        )
    if reason == "insufficient_measurement_evidence":
        return (
            "Automated rule: the native-TIFF cross-section measurement was not valid "
            f"(tiff_measurement_valid={tiff_valid}), so there isn't enough "
            "deterministic evidence to classify this strut automatically. Judge "
            "directly from the raw-TIFF image whether material is present, absent, "
            "or disconnected."
        )
    if reason == "human_review_override":
        return (
            "Previously reviewed by a human, but the reviewer's own verdict was "
            "'uncertain' — flagged for a second look, ideally with the 3D view."
        )
    return f"Automated rule flagged this strut as uncertain (reason: {reason})."


def load_reviewed_ids(human_review_path: Path) -> set[int]:
    if not human_review_path.is_file():
        return set()
    reviews = pd.read_csv(human_review_path)
    if reviews.empty:
        return set()
    return {int(value) for value in reviews["strut_id"]}


def sample_uncertain_ids(
    table_path: Path,
    human_review_path: Path,
    n: int = 5,
    seed: int | None = None,
    exclude: Iterable[int] = (),
) -> list[int]:
    """Pick up to `n` uncertain struts that have no human review entry yet."""

    table = pd.read_csv(table_path, usecols=["strut_id", "defect_type"])
    pool = table.loc[table["defect_type"] == "uncertain", "strut_id"].astype(int)
    reviewed = load_reviewed_ids(human_review_path) | {int(value) for value in exclude}
    pool = pool[~pool.isin(reviewed)]
    if pool.empty:
        return []
    rng = np.random.default_rng(seed)
    count = min(n, len(pool))
    chosen = rng.choice(pool.to_numpy(), size=count, replace=False)
    return sorted(int(value) for value in chosen)


def append_review(
    strut_id: int,
    human_label: str,
    review_note: str,
    human_review_path: Path = DEFAULT_HUMAN_REVIEW,
    reviewer: str = "uncertain_strut_review_agent",
) -> dict:
    """Append one verdict to the human-review CSV. Rejects duplicate strut IDs."""

    if human_label not in CLASSIFICATION_LABELS:
        raise ValueError(f"Unsupported label {human_label!r}; must be one of {CLASSIFICATION_LABELS}")
    strut_id = int(strut_id)
    human_review_path.parent.mkdir(parents=True, exist_ok=True)
    if human_review_path.is_file():
        existing = pd.read_csv(human_review_path)
    else:
        existing = pd.DataFrame(columns=["strut_id", "human_label", "review_note", "reviewer"])
    if len(existing) and strut_id in {int(value) for value in existing["strut_id"]}:
        raise ValueError(f"Strut {strut_id} already has a human review entry")
    new_row = pd.DataFrame(
        [{"strut_id": strut_id, "human_label": human_label, "review_note": review_note, "reviewer": reviewer}]
    )
    updated = pd.concat([existing, new_row], ignore_index=True)
    tmp_path = human_review_path.with_suffix(".csv.tmp")
    updated.to_csv(tmp_path, index=False)
    tmp_path.replace(human_review_path)
    return {"strut_id": strut_id, "human_label": human_label, "human_review_path": str(human_review_path)}


def _bounds(row: pd.Series, shape: tuple[int, int, int], margin: int = 8):
    points = np.array(
        [
            [row.start_z, row.start_y, row.start_x],
            [row.end_z, row.end_y, row.end_x],
        ],
        dtype=float,
    )
    low = np.floor(points.min(axis=0) - margin).astype(int)
    high = np.ceil(points.max(axis=0) + margin + 1).astype(int)
    low = np.maximum(low, 0)
    high = np.minimum(high, np.asarray(shape))
    return low, high


def _line_points(row: pd.Series, low: np.ndarray, high: np.ndarray, count: int = 100):
    start = np.array([row.start_z, row.start_y, row.start_x], dtype=float)
    end = np.array([row.end_z, row.end_y, row.end_x], dtype=float)
    points = start[None, :] + np.linspace(0.0, 1.0, count)[:, None] * (end - start)[None, :]
    return points - low[None, :], (points >= low).all(axis=1) & (points < high).all(axis=1)


def _save_2d(row: pd.Series, crop: np.ndarray, low: np.ndarray, path: Path) -> None:
    projections = [
        (np.max(crop, axis=0), "XY max projection", ("x (voxels)", "y (voxels)")),
        (np.max(crop, axis=1), "XZ max projection", ("x (voxels)", "z (voxels)")),
        (np.max(crop, axis=2), "YZ max projection", ("y (voxels)", "z (voxels)")),
    ]
    points, valid = _line_points(row, low, low + np.asarray(crop.shape))
    points = points[valid]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.6), constrained_layout=True)
    for index, (image, title, labels) in enumerate(projections):
        ax = axes[index]
        finite = image[np.isfinite(image)]
        low_value, high_value = np.percentile(finite, [1, 99.7])
        ax.imshow(image, cmap="gray", origin="lower", vmin=low_value, vmax=high_value)
        if index == 0:
            ax.plot(points[:, 2], points[:, 1], color="#ff3b30", linewidth=1.5)
            ax.scatter([row.start_x - low[2], row.end_x - low[2]], [row.start_y - low[1], row.end_y - low[1]], c="#00e5ff", s=18)
        elif index == 1:
            ax.plot(points[:, 2], points[:, 0], color="#ff3b30", linewidth=1.5)
            ax.scatter([row.start_x - low[2], row.end_x - low[2]], [row.start_z - low[0], row.end_z - low[0]], c="#00e5ff", s=18)
        else:
            ax.plot(points[:, 1], points[:, 0], color="#ff3b30", linewidth=1.5)
            ax.scatter([row.start_y - low[1], row.end_y - low[1]], [row.start_z - low[0], row.end_z - low[0]], c="#00e5ff", s=18)
        ax.set_title(title)
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
    fig.suptitle(
        f"Uncertain strut {int(row.name)} | {row.edge_id}\n"
        f"Raw TIFF texture; red = registered expected centerline | reason: {row.classification_reason}",
        fontsize=12,
    )
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _save_3d(row: pd.Series, crop: np.ndarray, low: np.ndarray, path: Path) -> None:
    finite = crop[np.isfinite(crop)]
    threshold = float(np.percentile(finite, 98.0))
    coordinates = np.argwhere(crop >= threshold)
    if len(coordinates) > 18_000:
        stride = int(np.ceil(len(coordinates) / 18_000))
        coordinates = coordinates[::stride]
    values = crop[tuple(coordinates.T)].astype(float)
    points, valid = _line_points(row, low, low + np.asarray(crop.shape))
    points = points[valid]
    fig = plt.figure(figsize=(9, 8), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(
        coordinates[:, 2], coordinates[:, 1], coordinates[:, 0],
        c=values, cmap="gray", s=4, alpha=0.32, linewidths=0,
    )
    ax.plot(points[:, 2], points[:, 1], points[:, 0], color="#ff3b30", linewidth=3, label="expected centerline")
    ax.scatter(
        [row.start_x - low[2], row.end_x - low[2]],
        [row.start_y - low[1], row.end_y - low[1]],
        [row.start_z - low[0], row.end_z - low[0]],
        c="#00e5ff", s=35, label="registered endpoints",
    )
    ax.set_xlabel("x (voxels)")
    ax.set_ylabel("y (voxels)")
    ax.set_zlabel("z (voxels)")
    ax.set_title(
        f"Raw-TIFF local 3D texture — strut {int(row.name)}\n"
        f"threshold shown: 98th percentile ({threshold:.0f}); red = expected centerline"
    )
    ax.legend(loc="upper right")
    ax.view_init(elev=23, azim=-58)
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _otsu_mask_panel(
    row: pd.Series,
    volume: np.ndarray,
    path: Path,
    *,
    station_fraction: float = 0.5,
    endpoint_exclusion_fraction: float = 0.12,
    cross_section_step_voxels: float = 0.5,
    search_margin_voxels: float = 3.0,
    minimum_local_contrast: float = 1000.0,
) -> dict:
    """Render one representative cross-section exactly as the automated
    classifier sees it: same local Otsu threshold and connected-component
    material selection as Components/strut_metrology.py, not a reimplementation.
    """

    endpoint0_xyz = np.array([row.start_x, row.start_y, row.start_z], dtype=float)
    endpoint1_xyz = np.array([row.end_x, row.end_y, row.end_z], dtype=float)
    expected_radius = float(row.expected_radius_median_voxels)

    first, _second, direction, axes, length = _cross_section_frame(endpoint0_xyz, endpoint1_xyz)
    start = endpoint_exclusion_fraction * length
    stop = (1.0 - endpoint_exclusion_fraction) * length
    axial_position = start + station_fraction * (stop - start)
    station = first + axial_position * direction

    grid_extent = expected_radius + search_margin_voxels
    coordinates = np.arange(-grid_extent, grid_extent + 0.5 * cross_section_step_voxels, cross_section_step_voxels)
    vv, uu = np.meshgrid(coordinates, coordinates, indexing="ij")
    local_uv = np.stack((uu.ravel(), vv.ravel()), axis=1)
    offsets_xyz = local_uv @ axes
    query = station[None, :] + offsets_xyz
    sampled, in_bounds = trilinear_sample(volume, query)
    radial_grid = np.linalg.norm(local_uv, axis=1)

    component = _select_seeded_material_component(
        sampled, in_bounds, local_uv, vv.shape, radial_grid, expected_radius, minimum_local_contrast,
    )

    intensity_grid = sampled.reshape(vv.shape)
    finite = intensity_grid[np.isfinite(intensity_grid)]
    low_value, high_value = (np.percentile(finite, [1, 99.7]) if finite.size else (0.0, 1.0))
    fig, panels = plt.subplots(1, 2, figsize=(11, 5.4), constrained_layout=True)
    panels[0].imshow(intensity_grid, cmap="gray", origin="lower", vmin=low_value, vmax=high_value)
    panels[0].set_title(f"Raw cross-section (station @ {station_fraction:.0%} of body)")

    panels[1].imshow(intensity_grid, cmap="gray", origin="lower", vmin=low_value, vmax=high_value)
    if component["reason"] == "component_selected":
        measurement_disk = (radial_grid <= expected_radius + 2.0).reshape(vv.shape)
        material_mask = (
            (sampled >= component["level"]).reshape(vv.shape)
            & in_bounds.reshape(vv.shape)
            & measurement_disk
        )
        selected_mask = component["component"].reshape(vv.shape)
        overlay = np.zeros(vv.shape + (4,), dtype=float)
        overlay[material_mask] = [1.0, 0.55, 0.0, 0.35]
        overlay[selected_mask] = [0.0, 0.9, 0.3, 0.55]
        panels[1].imshow(overlay, origin="lower")
        title = (
            f"Otsu level={component['level']:.0f} | contrast={component['contrast']:.0f} | "
            f"area_fraction={component['area_fraction']:.2f} (green=selected material, orange=above-threshold unselected)"
        )
    else:
        title = f"Otsu segmentation failed: {component['reason']}"
    panels[1].set_title(title, fontsize=9.5)
    for panel in panels:
        panel.set_xlabel("u (voxels, cross-section)")
        panel.set_ylabel("v (voxels, cross-section)")
    fig.suptitle(
        f"Strut {int(row.name)} — local Otsu segmentation (Components/strut_metrology.py), "
        f"expected radius {expected_radius:.2f} vox",
        fontsize=12,
    )
    fig.savefig(path, dpi=170, facecolor="white")
    plt.close(fig)
    return {
        "path": str(path),
        "station_fraction": station_fraction,
        "expected_radius_voxels": expected_radius,
        "reason": component["reason"],
        "otsu_level": component.get("level"),
        "contrast": component.get("contrast"),
        "area_fraction": component.get("area_fraction"),
    }


def render(
    ids: tuple[int, ...],
    table_path: Path,
    tiff_path: Path,
    output: Path,
    formats: tuple[str, ...] = ("2d",),
    include_otsu: bool = False,
) -> dict:
    table = pd.read_csv(table_path)
    selected = table[table.strut_id.isin(ids)].set_index("strut_id")
    missing = sorted(set(ids) - set(int(value) for value in selected.index))
    if missing:
        raise ValueError(f"Strut IDs not found: {missing}")
    output.mkdir(parents=True, exist_ok=True)
    volume = tifffile.memmap(tiff_path)
    records = []
    for strut_id in ids:
        row = selected.loc[strut_id]
        low, high = _bounds(row, volume.shape)
        crop = np.asarray(volume[low[0]:high[0], low[1]:high[1], low[2]:high[2]])
        stem = f"strut_{strut_id}"
        path_2d = output / f"{stem}_2d_raw_tiff.png"
        path_3d = output / f"{stem}_3d_raw_tiff.png"
        if "2d" in formats:
            _save_2d(row, crop, low, path_2d)
        if "3d" in formats:
            _save_3d(row, crop, low, path_3d)
        otsu_info = None
        path_otsu = output / f"{stem}_otsu_mask.png"
        if include_otsu:
            otsu_info = _otsu_mask_panel(row, volume, path_otsu)
        records.append(
            {
                "strut_id": int(strut_id),
                "edge_id": str(row.edge_id),
                "classification_reason": str(row.classification_reason),
                "classification_status": str(row.classification_status),
                "observed_axial_fraction": float(row.observed_axial_fraction),
                "connected_support": bool(row.connected_support),
                "longest_unsupported_gap_voxels": float(row.longest_unsupported_gap_voxels),
                "p90_centerline_displacement_voxels": float(row.p90_centerline_displacement_voxels),
                "measurement_valid": bool(row.measurement_valid),
                "tiff_measurement_valid": bool(row.tiff_measurement_valid),
                "thickness_um_median": None if pd.isna(row.thickness_um_median) else float(row.thickness_um_median),
                "crop_start_zyx": low.tolist(),
                "crop_stop_zyx_exclusive": high.tolist(),
                "raw_tiff": str(tiff_path),
                "image_2d": str(path_2d) if "2d" in formats else None,
                "image_3d": str(path_3d) if "3d" in formats else None,
                "why_uncertain": _uncertainty_explanation(row),
                "label_menu": REVIEW_LABEL_MENU,
                "image_otsu_mask": str(path_otsu) if include_otsu else None,
                "otsu": otsu_info,
            }
        )
    manifest = {
        "source_table": str(table_path),
        "source_raw_tiff": str(tiff_path),
        "human_review_path": str(DEFAULT_HUMAN_REVIEW),
        "records": records,
    }
    (output / "review_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", type=int, default=None)
    parser.add_argument("--sample", type=int, default=None, help="Auto-sample N unreviewed uncertain struts instead of --ids.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--exclude", nargs="*", type=int, default=(), help="Extra strut IDs to exclude from --sample.")
    parser.add_argument("--formats", choices=["2d", "3d", "both"], default="2d")
    parser.add_argument("--otsu", action="store_true", help="Also render the classifier's local Otsu segmentation at the mid-body cross-section.")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--tiff", type=Path, default=DEFAULT_TIFF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--human-review", type=Path, default=DEFAULT_HUMAN_REVIEW)

    subparsers = parser.add_subparsers(dest="command")
    record_parser = subparsers.add_parser("record", help="Append one human verdict to the review CSV.")
    record_parser.add_argument("--strut-id", type=int, required=True)
    record_parser.add_argument("--label", required=True, choices=CLASSIFICATION_LABELS)
    record_parser.add_argument("--note", required=True)
    record_parser.add_argument("--reviewer", default="uncertain_strut_review_agent")
    record_parser.add_argument("--human-review", type=Path, default=DEFAULT_HUMAN_REVIEW)

    args = parser.parse_args()

    if args.command == "record":
        result = append_review(args.strut_id, args.label, args.note, args.human_review, args.reviewer)
        print(json.dumps(result, indent=2))
        return

    if args.sample is not None:
        ids = sample_uncertain_ids(args.table, args.human_review, n=args.sample, seed=args.seed, exclude=args.exclude)
        if not ids:
            print(json.dumps({"records": [], "note": "No unreviewed uncertain struts remain."}, indent=2))
            return
    elif args.ids:
        ids = args.ids
    else:
        ids = list(DEFAULT_IDS)

    formats = ("2d", "3d") if args.formats == "both" else (args.formats,)
    print(json.dumps(render(tuple(ids), args.table, args.tiff, args.output, formats, include_otsu=args.otsu), indent=2))


if __name__ == "__main__":
    main()
