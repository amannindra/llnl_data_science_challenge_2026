"""Plotly figures for saved lattice CT evidence."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


CANDIDATE_COLORS = {
    "healthy": "#248A3D",
    "missing": "#D70015",
    "broken": "#C93400",
    "thin": "#8944AB",
    "thick": "#E08A00",
    "bent_or_misaligned": "#7A5AF8",
    "uncertain": "#0066CC",
    "not_applicable": "#9A9AA0",
}
CHART_PALETTE = {
    "blue": ("#215290", "#507DAB", "#89A8C6", "#C3D4E3"),
    "green": ("#A8C75D", "#BED583", "#D3E3AB", "#E9F1D4"),
    "red": ("#D56364", "#DD888A", "#E8AFB0", "#F4D8D8"),
    "cyan": ("#69C5EF", "#88D3F2", "#ADE1F7", "#D6F0FB"),
}
CHART_CLASS_COLORS = {
    "missing": CHART_PALETTE["red"][0],
    "broken": CHART_PALETTE["blue"][0],
    "thin": CHART_PALETTE["green"][0],
    "uncertain": CHART_PALETTE["cyan"][0],
    "healthy": CHART_PALETTE["blue"][2],
    "thick": CHART_PALETTE["green"][0],
    "bent_or_misaligned": "#7A5AF8",
    "not_applicable": "#9A9AA0",
}
CANDIDATE_ORDER = [
    "missing", "broken", "thin", "thick", "bent_or_misaligned",
    "uncertain", "healthy", "not_applicable",
]
SYSTEM_FONT = '-apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif'


def _finish(figure: go.Figure, *, title: str, height: int) -> go.Figure:
    figure.update_layout(
        title=dict(text=title, font=dict(size=22, color="#1D1D1F")),
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family=SYSTEM_FONT, color="#1D1D1F"),
        margin=dict(l=24, r=24, t=72, b=24),
        legend_title=None,
        hoverlabel=dict(font_family=SYSTEM_FONT),
    )
    figure.update_xaxes(gridcolor="#E8E8ED", zerolinecolor="#E8E8ED")
    figure.update_yaxes(gridcolor="#E8E8ED", zerolinecolor="#E8E8ED")
    return figure


def class_count_figure(table: pd.DataFrame) -> go.Figure:
    counts = table["prediction"].value_counts().reindex(CANDIDATE_ORDER, fill_value=0)
    figure = go.Figure(
        go.Bar(
            x=[label.title() for label in counts.index],
            y=counts.values,
            marker_color=[CHART_CLASS_COLORS[label] for label in counts.index],
            text=counts.values,
            textposition="outside",
            hovertemplate="%{x}: %{y} struts<extra></extra>",
        )
    )
    figure.update_layout(xaxis_title=None, yaxis_title="Struts")
    return _finish(figure, title="Classification counts", height=400)


def lattice_3d_figure(
    table: pd.DataFrame,
    *,
    title: str = "Registered strut geometry",
    xray_context: dict | None = None,
    context_opacity: float = 0.10,
    mute_intact: bool = False,
) -> go.Figure:
    figure = go.Figure()
    if xray_context is not None:
        vertices = xray_context["vertices_zyx"]
        faces = xray_context["faces"]
        figure.add_trace(
            go.Mesh3d(
                x=vertices[:, 2],
                y=vertices[:, 1],
                z=vertices[:, 0],
                i=faces[:, 0],
                j=faces[:, 1],
                k=faces[:, 2],
                color="#A1A1A6",
                opacity=float(context_opacity),
                name="CT material context",
                hoverinfo="skip",
                flatshading=False,
                lighting=dict(ambient=0.85, diffuse=0.25, specular=0.05),
                showlegend=True,
            )
        )
    for label in CANDIDATE_ORDER:
        subset = table[table["prediction"] == label]
        if subset.empty:
            continue
        xs: list[float | None] = []
        ys: list[float | None] = []
        zs: list[float | None] = []
        hover: list[str | None] = []
        for row in subset.itertuples(index=False):
            details = (
                f"Strut {int(row.strut_id)}<br>Class: {label.title()}<br>"
                f"Material coverage: {row.occupancy:.3f}<br>"
                f"Longest gap: {row.gap_fraction:.3f}"
            )
            xs.extend([row.start_x, row.end_x, None])
            ys.extend([row.start_y, row.end_y, None])
            zs.extend([row.start_z, row.end_z, None])
            hover.extend([details, details, None])
        trace_color = "#86868B" if mute_intact and label == "healthy" else CANDIDATE_COLORS[label]
        trace_width = 3 if mute_intact and label == "healthy" else 7
        figure.add_trace(
            go.Scatter3d(
                x=xs, y=ys, z=zs, mode="lines", name=label.title(),
                line=dict(color=trace_color, width=trace_width),
                text=hover, hovertemplate="%{text}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter3d(
                x=subset["mid_x"], y=subset["mid_y"], z=subset["mid_z"],
                mode="markers", name=f"{label.title()} midpoint", showlegend=False,
                marker=dict(color=trace_color, size=3 if label == "healthy" else 5),
                customdata=np.column_stack(
                    [subset["strut_id"], subset["occupancy"], subset["gap_fraction"]]
                ),
                hovertemplate=(
                    "Strut %{customdata[0]:.0f}<br>"
                    f"Class: {label.title()}<br>"
                    "Material coverage: %{customdata[1]:.3f}<br>"
                    "Longest gap: %{customdata[2]:.3f}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        scene=dict(
            xaxis=dict(title="CT x (voxels)", backgroundcolor="#FFFFFF", gridcolor="#E8E8ED"),
            yaxis=dict(title="CT y (voxels)", backgroundcolor="#FFFFFF", gridcolor="#E8E8ED"),
            zaxis=dict(title="CT z (voxels)", backgroundcolor="#FFFFFF", gridcolor="#E8E8ED"),
            aspectmode="data",
        ),
    )
    return _finish(figure, title=title, height=680)


def thickness_histogram_figure(
    table: pd.DataFrame,
    *,
    thin_cutoff_um: float | None,
    design_reference_um: float | None = None,
) -> go.Figure:
    valid = table.loc[
        table["thickness_measurement_valid"].astype(bool),
        ["diameter_median_um", "prediction", "strut_id"],
    ].dropna(subset=["diameter_median_um"])
    figure = px.histogram(
        valid,
        x="diameter_median_um",
        color="prediction",
        color_discrete_map=CHART_CLASS_COLORS,
        category_orders={"prediction": CANDIDATE_ORDER},
        nbins=max(8, min(18, len(valid))),
        hover_data=["strut_id"],
        labels={"diameter_median_um": "Estimated diameter (µm)", "prediction": "Class"},
    )
    if thin_cutoff_um is not None:
        figure.add_vline(
            x=thin_cutoff_um, line_color=CHART_CLASS_COLORS["thin"], line_dash="dash",
            annotation_text="Thin cutoff", annotation_position="top left",
        )
    if design_reference_um is not None:
        figure.add_vline(
            x=design_reference_um, line_color="#86868B", line_dash="dot",
            annotation_text="Design reference", annotation_position="top right",
        )
    figure.update_layout(bargap=0.05, yaxis_title="Count")
    return _finish(figure, title="Strut thickness distribution", height=520)


def spatial_projection_figure(table: pd.DataFrame) -> go.Figure:
    figure = px.scatter(
        table,
        x="mid_x", y="mid_y", color="prediction", symbol="height_band",
        color_discrete_map=CHART_CLASS_COLORS,
        category_orders={"prediction": CANDIDATE_ORDER},
        hover_data={
            "strut_id": True, "mid_z": ":.1f", "occupancy": ":.3f",
            "gap_fraction": ":.3f", "mid_x": ":.1f", "mid_y": ":.1f",
        },
        labels={
            "mid_x": "CT x (voxels)", "mid_y": "CT y (voxels)",
            "prediction": "Class",
        },
    )
    figure.update_yaxes(scaleanchor="x", scaleratio=1)
    return _finish(figure, title="Spatial distribution: x–y projection", height=600)
