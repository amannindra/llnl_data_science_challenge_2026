"""Plots and a traceable Markdown report for the 60-strut MVP run."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analysis import DISPLAY_COLORS, RULE_VERSION, RuleSettings


def plot_thickness(
    table: pd.DataFrame,
    output_path: Path,
    design_diameter_um: float,
) -> None:
    """Plot a preliminary histogram for material-supported sampled struts."""

    values = table.loc[
        table["thickness_measurement_valid"]
        & np.isfinite(table["diameter_median_um"]),
        "diameter_median_um",
    ].to_numpy(float)
    fig, axis = plt.subplots(figsize=(8, 5))
    if len(values):
        bins = min(15, max(5, int(np.sqrt(len(values)))))
        axis.hist(values, bins=bins, color="#4c78a8", edgecolor="white", alpha=0.9)
        axis.axvline(
            np.median(values),
            color="black",
            linestyle="-",
            label=f"Sample median: {np.median(values):.1f} µm",
        )
    else:
        axis.text(0.5, 0.5, "No supported thickness measurements", ha="center")
    axis.axvline(
        design_diameter_um,
        color="#d62728",
        linestyle="--",
        label=f"Tentative design reference: {design_diameter_um:.0f} µm",
    )
    axis.set(
        title="Preliminary sampled-strut thickness distribution",
        xlabel="Median local diameter (µm)",
        ylabel="Sampled strut count",
    )
    axis.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_spatial_distribution(table: pd.DataFrame, output_path: Path) -> None:
    """Show candidate locations in two projections plus categorical counts."""

    colors = [DISPLAY_COLORS.get(str(value), "#7f7f7f") for value in table["prediction"]]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    axes[0].scatter(table["mid_x"], table["mid_y"], c=colors, s=28, alpha=0.85)
    axes[0].set(title="X–Y projection", xlabel="x (voxels)", ylabel="y (voxels)")
    axes[0].set_aspect("equal", adjustable="box")
    axes[1].scatter(table["mid_x"], table["mid_z"], c=colors, s=28, alpha=0.85)
    axes[1].set(title="X–Z projection", xlabel="x (voxels)", ylabel="z (voxels)")
    axes[1].set_aspect("equal", adjustable="box")
    counts = Counter(table["prediction"].astype(str))
    labels = list(DISPLAY_COLORS)
    axes[2].bar(
        labels,
        [counts.get(label, 0) for label in labels],
        color=[DISPLAY_COLORS[label] for label in labels],
    )
    axes[2].set(title="Candidate counts", ylabel="Struts")
    axes[2].tick_params(axis="x", rotation=35)
    fig.suptitle("Stratified sample only — not a full-part defect distribution")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def render_report(
    output_path: Path,
    alignment: dict[str, Any],
    metrics: dict[str, Any],
    table: pd.DataFrame,
    thickness_reference: dict[str, float],
) -> None:
    """Write a human-readable report without overstating unvalidated results."""

    counts = Counter(table["prediction"].astype(str))
    default_rules = RuleSettings().__dict__
    lines = [
        "# Lattice CT Analysis — 60-Strut Report",
        "",
        "> **Prototype status:** This is an automated, deterministic EDA workflow, "
        "not the final Part 2 system. Defect-candidate labels are produced by the "
        "transparent, provisional rules documented below; they are not validated defect labels.",
        "",
        "## Status",
        "",
        f"- Alignment gate passed: **{alignment['reliable']}**",
        f"- Sampled expected struts: **{len(table)}** of 18,468",
        f"- Axis mapping: `{alignment['selected_mapping']}`",
        f"- Provisional rule version: `{RULE_VERSION}`",
        "- Residual correction: none; registered coordinates already include specimen tilt.",
        "",
        "## Alignment evidence",
        "",
        f"- Otsu threshold: `{alignment['threshold_otsu']:.1f}` intensity units",
        f"- Material found within search neighborhood: `{alignment['material_found_fraction']:.1%}`",
        f"- Median centerline-to-material distance: `{alignment['median_material_distance_vox']:.2f}` voxels "
        f"(`{alignment['median_material_distance_um']:.1f} µm`)",
        f"- 90th-percentile distance: `{alignment['p90_material_distance_vox']:.2f}` voxels "
        f"(`{alignment['p90_material_distance_um']:.1f} µm`)",
        "",
        "## How the prototype detects defect candidates",
        "",
        "### Inputs and roles",
        "",
        "- **Registered CT TIFF:** measured grayscale X-ray attenuation. Bright voxels "
        "are treated as candidate printed material after thresholding.",
        "- **Registered JSON graph:** the nominal lattice topology and expected junction/"
        "strut coordinates. It identifies where a strut should exist; it does not "
        "contain defect labels.",
        "- **Voxel spacing:** `58.09 µm` in each axis, used to convert distance-transform "
        "measurements from voxels to micrometres.",
        "",
        "### Automated processing sequence",
        "",
        "1. **Load without copying the full CT.** The TIFF is memory-mapped so local "
        "strut regions can be analyzed without allocating a second full volume.",
        "2. **Estimate material intensity.** Otsu's method computes a global baseline "
        "threshold from sampled CT intensities.",
        "3. **Verify JSON-to-CT alignment before analysis.** All six coordinate-axis "
        "permutations are scored on expected centerlines. The selected mapping must "
        "find material near at least 85% of sampled stations, with median distance "
        "≤2 voxels and 90th-percentile distance ≤4 voxels. Failure stops the pipeline.",
        "4. **Select a reproducible EDA sample.** A fixed random seed (`20260723`) "
        "round-robin samples 60 of 18,468 expected struts across interior/exterior "
        "regions, low/middle/high positions, and strut orientations.",
        "5. **Extract one local ROI per expected strut.** The nominal centerline is "
        "sampled every 0.5 voxel. The first and last 10% are trimmed to reduce junction "
        "node contamination.",
        "6. **Segment material three ways.** Each ROI is thresholded at 97%, 100%, and "
        "103% of the Otsu threshold. A voxel is material when its intensity is greater "
        "than or equal to the tested threshold.",
        "7. **Measure centerline support.** At every centerline station, the analysis "
        "searches up to 4 voxels for segmented material and records occupancy, the "
        "longest unsupported run, alignment distance, peak intensity, and local diameter.",
        "8. **Assign a candidate class.** The rule hierarchy below is applied in order. "
        "The result, reason, features, and uncalibrated confidence are written to CSV.",
        "9. **Summarize and visualize.** The pipeline writes a traceable feature table, "
        "metrics, and thickness and spatial-distribution plots.",
        "",
        "### Feature definitions",
        "",
        "- **Occupancy:** fraction of sampled centerline stations that have thresholded "
        "material within the 4-voxel search radius.",
        "- **Gap fraction:** longest consecutive run without nearby material divided by "
        "the number of sampled stations.",
        "- **Alignment error:** median distance from expected centerline stations to the "
        "nearest thresholded material.",
        "- **Diameter:** twice the segmented-mask Euclidean distance-transform radius, "
        "summarized over the central 60% of the strut.",
        "- **Threshold stability:** fraction of the three threshold tests whose coarse "
        "state agrees with the baseline Otsu result.",
        "",
        "### Provisional classification rules",
        "",
        "| Candidate | Automated rule | Interpretation |",
        "|---|---|---|",
        f"| Missing | occupancy ≤ `{default_rules['missing_max_occupancy']:.2f}` "
        "at all three tested thresholds | Almost no CT material follows the "
        "expected strut. |",
        f"| Broken | occupancy ≤ `{default_rules['broken_max_occupancy']:.2f}` and "
        f"gap fraction ≥ `{default_rules['broken_min_gap_fraction']:.2f}` | "
        "Some material exists, but a long internal interruption is present. |",
        f"| Uncertain | alignment error > `{default_rules['maximum_alignment_error_vox']:.1f}` "
        f"voxels or threshold stability < `{default_rules['minimum_stability']:.3f}` | "
        "The geometry or segmentation is not stable enough for a stronger label. |",
        "| Thin | valid interior intact measurement and diameter is at or below the "
        "sample-derived lower-tail cutoff | Supported material is unusually narrow "
        "relative to this exploratory sample. |",
        "| Intact | none of the preceding rules apply | Material continuously supports "
        "the expected centerline under the provisional rules. |",
        "",
        "Rules are evaluated in the order shown. Therefore, a nearly empty strut is "
        "classified as missing before the broken-strut rule is considered.",
        "",
        "### What “confidence” means here",
        "",
        "The CSV confidence value is an **uncalibrated rule-strength score**, not a "
        "probability that a prediction is correct. It combines threshold stability "
        "with either distance from the missing-occupancy boundary or centerline "
        "alignment quality. No labeled ground truth is available, so accuracy, "
        "precision, recall, and F1 cannot currently be reported honestly.",
        "",
        "## Automated candidate summary",
        "",
    ]
    for label in DISPLAY_COLORS:
        count = counts.get(label, 0)
        lines.append(f"- {label.title()}: `{count}/{len(table)}` (`{count/len(table):.1%}`)")
    lines.extend(
        [
            "",
            f"- Classification coverage: `{metrics['classification_coverage']:.1%}`",
            f"- Median threshold stability: `{metrics['median_threshold_stability']:.1%}`",
            f"- Mean processing time: `{metrics['mean_runtime_seconds_per_strut']:.3f}` seconds/strut",
            "",
            "These are automated exploratory classifications and continuous measurements.",
            "",
            "## Thickness",
            "",
            f"- Measured median across supported sample: `{metrics['median_diameter_um']}` µm",
            f"- Valid interior thickness measurements: `{metrics['valid_thickness_measurement_count']}/{len(table)}`",
            f"- Conservative thin-candidate cutoff: `{thickness_reference['thin_candidate_cutoff_um']}` µm",
            "- Exterior thickness values are excluded because nearby solid skins/walls can contaminate the distance transform.",
            "- The 350 µm value is shown only as an unconfirmed design reference.",
            "- One voxel equals 58.09 µm, so segmentation and alignment errors materially affect diameter.",
            "",
            "![Preliminary sampled-strut thickness histogram](thickness_histogram.png)",
            "",
            "## Spatial distribution",
            "",
            "The following projections show only the stratified 60-strut sample, "
            "not the full-part defect distribution.",
            "",
            "![Sampled candidate spatial distribution](spatial_distribution.png)",
            "",
            "## Outputs",
            "",
            "- `alignment.json`: selected coordinate mapping, thresholds, stop criteria, "
            "and alignment evidence",
            "- `sampled_struts.csv`: one row per sampled strut with coordinates, ROI "
            "features, predictions, reasons, confidence scores, runtime, and exclusions",
            "- `pipeline_metrics.json`: automated coverage, stability, alignment, runtime, "
            "memory, thickness, and reproducibility metadata",
            "- `thickness_reference.json`: exploratory diameter distribution and thin cutoff",
            "- `thickness_histogram.png`: preliminary sampled thickness distribution",
            "- `spatial_distribution.png`: sampled candidate locations",
            "",
            "The JSON files can be opened directly in Cursor. The CSV is easiest to "
            "inspect with Cursor's table viewer, Python/pandas, or a spreadsheet tool. "
            "The Markdown report is the compact human-readable summary.",
            "",
            "## Limitations and next decision",
            "",
            "- This is a 60-strut stratified EDA sample, not the full lattice.",
            "- The JSON describes nominal expected struts and contains no defect labels.",
            "- Intentional versus manufacturing-caused missing struts cannot be inferred.",
            "- Candidate percentages are not defect prevalence estimates for the full part.",
            "- The provisional 10% all-threshold missing boundary, 15% gap boundary, "
            "and related rules were not supplied by the instructors and have not "
            "been scientifically calibrated.",
            "- Thin classification remains exploratory until experts define or validate a criterion.",
            "- The configured 350 µm design reference is unconfirmed; recent literature on "
            "a related specimen family reports 424 µm, so the applicable CAD revision must "
            "be checked before final thickness conclusions.",
            "- Use the automated alignment, stability, coverage, runtime, and uncertainty "
            "evidence to decide whether the method is suitable for scaling.",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
