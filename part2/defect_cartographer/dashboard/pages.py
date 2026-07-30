"""Streamlit page renderers for Lattice CT Explorer."""

from __future__ import annotations

import html
import asyncio
import math

import pandas as pd
import streamlit as st

from ..agents import copilot_status, run_copilot
from ..agents.mcp_tools import call_readonly_mcp
from .data import DashboardArtifacts
from .figures import (
    CANDIDATE_COLORS,
    class_count_figure,
    lattice_3d_figure,
    spatial_projection_figure,
    thickness_histogram_figure,
)
from .threejs_component import lattice_threejs_viewer


def _label_title(label: str) -> str:
    return label.replace("_", " ").title()


def _candidate_badge(label: str) -> str:
    color = CANDIDATE_COLORS[label]
    return (
        f'<span style="background:{color}12;color:{color};'
        'padding:8px 16px;border-radius:98px;font-weight:650;">'
        f"{html.escape(_label_title(label))}</span>"
    )


def _measurement_guide() -> None:
    with st.expander("How to read the measurements"):
        st.markdown(
            """
**Orientation** — The direction of a nominal strut in registered CT `(z, y, x)`
axes. A value such as `0:-1:-1` means little change in z while y and x decrease.

**Material coverage (occupancy)** — The fraction of expected centerline sampling
positions where segmented CT material is found within four voxels.

**Longest gap (gap fraction)** — The longest uninterrupted unsupported portion
of the centerline divided by its total sampled length.

**Alignment offset (voxels)** — The median voxel distance between the expected
centerline and the nearest segmented CT material.

**Threshold agreement (threshold stability)** — The fraction of three nearby
segmentation thresholds that agree with the baseline material-support state.

**Rule strength (uncalibrated)** — A heuristic measure of how strongly the
selected rule fired. It is not a probability or accuracy score.

**Evidence (prediction_reason)** — The specific measurements and cutoff that
caused the rule-based classification.
"""
        )


@st.cache_data(show_spinner=False)
def _load_strut_ct_evidence(strut_id: int) -> dict:
    """Ask the unified MCP boundary for one rendered CT evidence panel."""

    return asyncio.run(
        call_readonly_mcp(
            "get_strut_ct_evidence",
            {"strut_id": int(strut_id), "crop_radius_voxels": 24},
        )
    )


def _render_ct_evidence(strut_id: int) -> None:
    """Show the bounded CT crop returned by the unified evidence agent."""

    try:
        evidence = _load_strut_ct_evidence(int(strut_id))
        st.subheader("CT evidence")
        st.image(evidence["image_path"], width="stretch")
        st.caption(
            "Green overlay: Otsu-segmented material. Red crosshairs: expected "
            "strut midpoint. This is rendered evidence, not raw CT data."
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        st.warning(f"CT evidence is unavailable for strut {int(strut_id)}: {exc}")


def render_overview(artifacts: DashboardArtifacts) -> None:
    st.title("Lattice CT Explorer")
    st.caption("Registered CT volume and aligned nominal strut geometry")

    counts = artifacts.metrics["prediction_counts"]
    alignment = artifacts.alignment
    columns = st.columns(5)
    columns[0].metric("Analyzed struts", artifacts.metrics["sample_size"])
    columns[1].metric(
        "Decisive labels",
        f"{artifacts.metrics['classification_coverage']:.0%}",
        help="Healthy or physical-defect labels; bent, uncertain, and design-excluded review states are not counted.",
    )
    columns[2].metric(
        "Flagged struts",
        sum(counts.get(label, 0) for label in (
            "missing", "broken", "thin", "thick", "bent_or_misaligned", "uncertain"
        )),
        help="Defect findings plus review-required classifications.",
    )
    columns[3].metric(
        "Median diameter", f"{artifacts.metrics['median_diameter_um']:.1f} µm"
    )
    columns[4].metric(
        "Registration",
        "Passed" if alignment["reliable"] else "Review",
        help=f"{alignment['material_found_fraction']:.1%} material support",
    )

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.plotly_chart(
            class_count_figure(artifacts.table),
            width="stretch",
            config={"displaylogo": False},
        )
    with right:
        st.subheader("How the analysis works")
        st.markdown(
            """
    The dashboard loads all registered JSON struts and joins each one to the
    automated native-TIFF classification. Review states remain visible and are
    not silently converted into healthy or defect labels.

**Uncertain** means the expected strut is not aligned closely enough to CT
material, or its material-support result changes across nearby thresholds.
The evidence is therefore not stable enough for a stronger classification.
"""
        )
        st.caption(
            f"Coordinate mapping: {alignment['selected_mapping']}. "
            "The registered coordinates retain the specimen tilt."
        )


DEFECT_TABS = (
    "missing", "broken", "thin", "thick", "bent_or_misaligned", "uncertain"
)


def _render_defect_tab(table: pd.DataFrame, label: str) -> None:
    candidates = table.loc[table["prediction"] == label].copy()
    st.metric(f"{_label_title(label)} records", len(candidates))
    search_column, region_column, orientation_column = st.columns([1, 1, 1.4])
    search = search_column.text_input(
        "Search strut ID",
        key=f"{label}-strut-search",
        placeholder="e.g. 1885",
    ).strip()
    regions = region_column.multiselect(
        "Region",
        sorted(candidates["region"].dropna().astype(str).unique()),
        key=f"{label}-region-filter",
    )
    orientations = orientation_column.multiselect(
        "Orientation",
        sorted(candidates["orientation"].dropna().astype(str).unique()),
        key=f"{label}-orientation-filter",
    )
    filtered = candidates
    if search:
        filtered = filtered[
            filtered["strut_id"].astype(int).astype(str).str.contains(search, regex=False)
        ]
    if regions:
        filtered = filtered[filtered["region"].isin(regions)]
    if orientations:
        filtered = filtered[filtered["orientation"].isin(orientations)]
    filtered = filtered.sort_values("strut_id").reset_index(drop=True)

    page_size_column, page_column, download_column = st.columns([1, 1, 2])
    page_size = page_size_column.selectbox(
        "Rows per page",
        [10, 25, 50, 100],
        key=f"{label}-page-size",
    )
    page_count = max(1, math.ceil(len(filtered) / int(page_size)))
    page = page_column.number_input(
        "Page",
        min_value=1,
        max_value=page_count,
        value=1,
        step=1,
        key=f"{label}-page",
    )
    download_column.download_button(
        "Download filtered CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name=f"{label}_candidate_struts.csv",
        mime="text/csv",
        key=f"{label}-csv",
        disabled=filtered.empty,
    )
    start = (int(page) - 1) * int(page_size)
    visible = filtered.iloc[start : start + int(page_size)]
    st.caption(
        f"{len(filtered)} matching candidates · page {int(page)} of {page_count}"
    )
    display_columns = [
        "strut_id",
        "region",
        "orientation",
        "occupancy",
        "gap_fraction",
        "diameter_median_um",
    ]
    st.dataframe(
        visible[display_columns],
        width="stretch",
        height=420,
        hide_index=True,
        column_config={
            "strut_id": "Strut",
            "region": "Region",
            "orientation": "Orientation",
            "occupancy": st.column_config.NumberColumn(
                "Material coverage", format="%.3f"
            ),
            "gap_fraction": st.column_config.NumberColumn(
                "Longest gap", format="%.3f"
            ),
            "diameter_median_um": st.column_config.NumberColumn(
                "Diameter", format="%.1f µm"
            ),
        },
    )

    if filtered.empty:
        st.info(f"No {_label_title(label).lower()} records match the current filters.")
        return
    selected_id = st.selectbox(
        "Selected strut details",
        filtered["strut_id"].astype(int).tolist(),
        key=f"{label}-selected-strut",
    )
    details = filtered.loc[filtered["strut_id"] == int(selected_id)].iloc[0]
    st.markdown(_candidate_badge(label), unsafe_allow_html=True)
    detail_columns = st.columns(4)
    detail_columns[0].metric("Material coverage", f"{details['occupancy']:.3f}")
    detail_columns[1].metric("Longest gap", f"{details['gap_fraction']:.3f}")
    alignment_error = details["alignment_error_vox"]
    detail_columns[2].metric(
        "Alignment offset",
        "Not available" if pd.isna(alignment_error) else f"{alignment_error:.2f} vox",
    )
    diameter = details["diameter_median_um"]
    detail_columns[3].metric(
        "Diameter",
        "Not eligible" if pd.isna(diameter) else f"{diameter:.1f} µm",
    )
    st.caption(f"Evidence: {details['prediction_reason']}")
    _render_ct_evidence(int(selected_id))


def render_explorer(artifacts: DashboardArtifacts) -> None:
    st.title("Strut Explorer")
    st.caption("Inspect exploratory defect candidates by classification")
    defect_table = artifacts.table[
        artifacts.table["prediction"].isin(DEFECT_TABS)
    ].copy()

    st.plotly_chart(
        lattice_3d_figure(defect_table),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
    )
    _measurement_guide()
    tabs = st.tabs([_label_title(label) for label in DEFECT_TABS])
    for tab, label in zip(tabs, DEFECT_TABS):
        with tab:
            _render_defect_tab(defect_table, label)


def render_thickness_spatial(artifacts: DashboardArtifacts) -> None:
    st.title("Visual Analysis")
    st.caption("Explore measurements, registered geometry, and CT context")
    visualization = st.selectbox(
        "Visualization",
        [
            "X-ray 3D view",
            "Thickness distribution",
            "Spatial distribution",
            "Classification counts",
        ],
    )

    if visualization == "X-ray 3D view":
        control_a, control_b = st.columns(2)
        show_healthy = control_a.toggle("Show healthy struts", value=False)
        context_opacity = control_b.slider(
            "CT context opacity", 0.0, 0.35, 0.10, 0.01
        )
        visible = (
            artifacts.table
            if show_healthy
            else artifacts.table[~artifacts.table["prediction"].isin(["healthy", "not_applicable"])]
        )
        st.plotly_chart(
            lattice_3d_figure(
                visible,
                title="Registered CT and analyzed struts",
                xray_context=artifacts.xray_context,
                context_opacity=context_opacity,
                mute_intact=True,
            ),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
        )
        st.caption(
            "The translucent surface is a bounded, downsampled CT-derived context. "
            "Gray lines are healthy classifications; colored lines are findings or review states."
        )
        _threejs_inspector(artifacts)
    elif visualization == "Thickness distribution":
        reference = artifacts.thickness_reference
        show_design = st.toggle(
            "Show 350 µm design reference",
            value=False,
            help="Confirm the applicable CAD revision before treating this as final.",
        )
        st.plotly_chart(
            thickness_histogram_figure(
                artifacts.table,
                thin_cutoff_um=reference["thin_candidate_cutoff_um"],
                design_reference_um=(
                    reference["design_reference_um_unconfirmed"] if show_design else None
                ),
            ),
            width="stretch",
            config={"displaylogo": False},
        )
        st.caption(
            f"{reference['valid_thickness_measurement_count']} struts have eligible "
            "interior thickness measurements; exterior struts are excluded to reduce "
            "skin and wall contamination."
        )
    elif visualization == "Spatial distribution":
        st.plotly_chart(
            spatial_projection_figure(artifacts.table),
            width="stretch",
            config={"displaylogo": False},
        )
    else:
        st.plotly_chart(
            class_count_figure(artifacts.table),
            width="stretch",
            config={"displaylogo": False},
        )


def _threejs_inspector(artifacts: DashboardArtifacts) -> None:
    st.subheader("Interactive Full-Lattice Inspector (Three.js)")
    st.caption(
        "Three.js renders all 18,468 registered nominal struts in one steel-gray "
        "buffer. Every automated classification is available as a colored overlay; "
        "healthy and not-applicable records start hidden."
    )
    scene_path = artifacts.sample_dir / "full_lattice_scene.npz"
    if not scene_path.is_file():
        st.warning("The compact lattice scene artifact is unavailable.")
        return
    try:
        with st.container(key="lattice-fullbleed"):
            result = lattice_threejs_viewer(scene_path)
    except RuntimeError as exc:
        st.error(f"The interactive lattice inspector could not load: {exc}")
        return

    selected_id = getattr(result, "selected_strut_id", None)
    if selected_id is None:
        st.caption(
            "Select any classified strut to inspect its saved evidence."
        )
        return

    rows = artifacts.table.loc[
        artifacts.table["strut_id"] == int(selected_id)
    ]
    if rows.empty:
        st.warning(
            f"Strut {int(selected_id)} is not in the full saved classification."
        )
        return
    details = rows.iloc[0]
    st.markdown(
        f"**Selected strut {int(selected_id)}**",
    )
    st.markdown(
        _candidate_badge(str(details["prediction"])),
        unsafe_allow_html=True,
    )
    columns = st.columns(4)
    columns[0].metric("Material coverage", f"{details['occupancy']:.3f}")
    columns[1].metric("Longest gap", f"{details['gap_fraction']:.3f}")
    alignment_error = details["alignment_error_vox"]
    columns[2].metric(
        "Alignment offset",
        (
            "Not available"
            if pd.isna(alignment_error)
            else f"{alignment_error:.2f} vox"
        ),
    )
    diameter = details["diameter_median_um"]
    columns[3].metric(
        "Diameter",
        "Not eligible" if pd.isna(diameter) else f"{diameter:.1f} µm",
    )
    st.caption(f"Evidence: {details['prediction_reason']}")
    _render_ct_evidence(int(selected_id))


def render_architecture(artifacts: DashboardArtifacts) -> None:
    st.title("System Design")
    st.caption("A deterministic measurement core with bounded evidence tools and agents")

    architecture_tab, agents_tab, methods_tab = st.tabs(
        ["Architecture", "Agents and MCP", "Methods and evidence"]
    )
    with agents_tab:
        st.subheader("Agent roles")
        columns = st.columns(3, gap="large")
        cards = [
            (
                "Manager agent",
                "Analysis Coordinator",
                "Receives the question, delegates specialist work, and combines the "
                "evidence into one response.",
            ),
            (
                "Specialist sub-agent 1",
                "Measurement and QA Sub-agent",
                "Queries saved measurements, compares classifications, and checks that "
                "interpretations match the deterministic evidence.",
            ),
            (
                "Specialist sub-agent 2",
                "Visualization and Reporting Sub-agent",
                "Prepares plot instructions, explains methodology, and creates bounded "
                "Three.js scene filters and selected-strut specifications.",
            ),
        ]
        for column, (label, title, body) in zip(columns, cards):
            column.markdown(
                f'<div class="agent-card"><div class="agent-label">{label}</div>'
                f"<h3>{title}</h3><p>{body}</p></div>",
                unsafe_allow_html=True,
            )
        st.subheader("MCP evidence boundary")
        st.dataframe(
            pd.DataFrame(
                [
                    ("get_pipeline_summary", "Both sub-agents", "Aggregate evidence"),
                    ("get_strut_details", "Measurement and QA", "One saved strut"),
                    ("filter_defect_candidates", "Both sub-agents", "Bounded records"),
                    ("compare_defect_groups", "Measurement and QA", "Group comparison"),
                    ("get_methodology", "Both sub-agents", "Method explanation"),
                    (
                        "prepare_threejs_scene",
                        "Visualization and Reporting",
                        "Read-only scene filters and IDs",
                    ),
                    (
                        "get_strut_ct_evidence",
                        "Visualization and Reporting",
                        "Rendered CT crop for selected strut",
                    ),
                    (
                        "raw_ct_*",
                        "Unified formal agent",
                        "Mounted Aman CT utilities",
                    ),
                ],
                columns=["MCP tool", "Available to", "Purpose"],
            ),
            hide_index=True,
            width="stretch",
        )
    with architecture_tab:
        st.subheader("End-to-end evidence flow")
        st.code(
            """
Registered CT TIFF + aligned nominal JSON
                 |
                 v
      Deterministic scientific core
 registered full lattice -> TIFF measurements -> automated classifications
                 |
                 v
     CSV / JSON / PNG / Markdown artifacts
                 |
                 v
        Read-only ArtifactService
                 |
                 v
        Unified FastMCP agent: dashboard evidence + mounted Aman CT tools
                 |
        +--------+---------+
        |                  |
        v                  v
 Analysis Coordinator   External MCP client
    /          \\
   v            v
Measurement   Visualization
and QA        and Reporting
Sub-agent     Sub-agent
        \\      /
         v    v
 Streamlit + Plotly + Three.js
""".strip(),
            language="text",
        )
        st.markdown(
            """
The deterministic core owns every measurement and classification. Agents only
query saved evidence through MCP. Neither specialist receives raw CT arrays,
write permission, or authority to change classifications.
"""
        )
    with methods_tab:
        st.subheader("Scientific method")
        st.markdown(
            """
The JSON supplies expected strut centerlines in registered coordinates. The core
samples segmented CT material near each centerline, measures coverage, gaps,
alignment offset, threshold agreement, and eligible thickness, then applies:

**missing → broken → thin/thick → bent-or-misaligned → uncertain → healthy**
"""
        )
        _measurement_guide()
        left, right = st.columns(2, gap="large")
        with left:
            st.plotly_chart(
                thickness_histogram_figure(
                    artifacts.table,
                    thin_cutoff_um=artifacts.thickness_reference[
                        "thin_candidate_cutoff_um"
                    ],
                ),
                width="stretch",
                config={"displaylogo": False},
            )
        with right:
            st.plotly_chart(
                spatial_projection_figure(artifacts.table),
                width="stretch",
                config={"displaylogo": False},
            )
        st.markdown(
            '<div class="scope-card"><strong>Reproducibility</strong><br>'
            '<span class="muted">18,468 registered struts · native TIFF evidence · '
            "JSON (x,y,z) mapped to CT array (z,y,x).</span></div>",
            unsafe_allow_html=True,
        )


def render_copilot(_: DashboardArtifacts) -> None:
    st.title("Analysis Copilot")
    status = copilot_status()
    if status["available"]:
        st.caption(f"Live agent mode · {status['model']}")
    else:
        st.info(
            "Live agent mode requires OPENAI_API_KEY. The dashboard and evidence "
            "tools remain available without it."
        )
    st.markdown(
        """
The **Analysis Coordinator** delegates measurement questions to the
**Measurement and QA Sub-agent** and presentation questions to the
**Visualization and Reporting Sub-agent**. Their factual evidence comes from
read-only MCP tools.
"""
    )
    prompt = st.text_area(
        "Ask about the saved analysis",
        placeholder=(
            "Compare missing and broken classifications and explain which "
            "measurements triggered each rule."
        ),
        height=120,
    )
    if st.button("Ask copilot", type="primary", disabled=not prompt.strip()):
        with st.spinner("Reviewing the evidence"):
            response = run_copilot(prompt, page_context={"page": "copilot"})
        st.markdown(response["answer"])
        for evidence in response["evidence"]:
            st.markdown(f"- {evidence}")
        if response["warnings"]:
            st.caption(" ".join(response["warnings"]))
