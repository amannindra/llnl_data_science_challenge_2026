"""Streamlit page renderers for Lattice CT Explorer."""

from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from ..agents import copilot_status, run_copilot
from ..core.io import read_json
from ..core.slice_evidence import get_strut_slice_evidence
from .data import DashboardArtifacts
from .figures import (
    CANDIDATE_COLORS,
    class_count_figure,
    lattice_3d_figure,
    spatial_projection_figure,
    thickness_histogram_figure,
)
from .threejs_component import lattice_threejs_viewer, unit_cell_threejs_viewer


def _candidate_badge(label: str) -> str:
    color = CANDIDATE_COLORS[label]
    text_color = "#1D1D1F" if label == "broken" else color
    return (
        f'<span style="background:{color}26;color:{text_color};'
        'padding:8px 16px;border-radius:98px;font-weight:650;">'
        f"{html.escape(label.title())}</span>"
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


def render_overview(artifacts: DashboardArtifacts) -> None:
    st.title("Lattice CT Explorer")
    st.caption("Registered CT volume and aligned nominal strut geometry")

    counts = artifacts.metrics["prediction_counts"]
    alignment = artifacts.alignment
    columns = st.columns(5)
    columns[0].metric("Analyzed struts", artifacts.metrics["sample_size"])
    columns[1].metric(
        "Classified",
        f"{artifacts.metrics['classification_coverage']:.0%}",
        help="Fraction assigned a class other than uncertain.",
    )
    columns[2].metric(
        "Flagged struts",
        counts["missing"] + counts["broken"] + counts["thin"],
        help="Missing, broken, or thin classifications.",
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
The pipeline aligns the nominal JSON struts to the CT volume, samples material
along each expected centerline, measures support and geometry, then applies
transparent rules in this order:

**missing → broken → uncertain → thin → intact**

**Uncertain** means the expected strut is not aligned closely enough to CT
material, or its material-support result changes across nearby thresholds.
The evidence is therefore not stable enough for a stronger classification.
"""
        )
        st.caption(
            f"Coordinate mapping: {alignment['selected_mapping']}. "
            "The registered coordinates retain the specimen tilt."
        )


DEFECT_TABS = ("missing", "broken", "thin", "uncertain")
UNIT_CELL_EXAMPLES = {
    "Broken": ("broken", 521, 12958),
    "Missing": ("missing", 646, 16082),
    "Thin": ("thin", 605, 15040),
    "Intact": ("intact", 362, 9000),
}
SEMANTIC_SYMBOLS = {
    "missing": "×",
    "broken": "∥",
    "thin": "↓",
    "uncertain": "?",
    "intact": "✓",
    "nominal": "◇",
}
MEASUREMENT_HELP = {
    "occupancy": (
        "Material coverage: fraction of expected centerline samples with segmented "
        "CT material inside the search corridor."
    ),
    "gap_fraction": (
        "Longest gap: largest uninterrupted unsupported centerline run divided by "
        "the sampled strut length."
    ),
    "alignment_error_vox": (
        "Alignment offset: median distance in voxels from the expected centerline "
        "to nearby segmented CT material."
    ),
    "diameter_median_um": (
        "Diameter: exploratory median interior thickness converted with the saved "
        "anisotropic voxel spacing."
    ),
}


def _semantic_legend(*, compact: bool = False) -> None:
    """Render one text-and-symbol legend so color is never the only cue."""

    labels = ("missing", "broken", "thin", "uncertain", "intact", "nominal")
    items = "".join(
        '<span class="semantic-legend-item">'
        f'<b style="background:{CANDIDATE_COLORS.get(label, "#215290")}">'
        f'{SEMANTIC_SYMBOLS[label]}</b>{label.title()}</span>'
        for label in labels
    )
    qualifier = " compact" if compact else ""
    st.markdown(
        f'<div class="semantic-legend{qualifier}" role="list" '
        f'aria-label="Classification legend">{items}</div>',
        unsafe_allow_html=True,
    )


def _example_artifacts(
    artifacts: DashboardArtifacts,
    label: str,
) -> tuple[str, int, int, Path, Path]:
    key, cell_id, target_strut_id = UNIT_CELL_EXAMPLES[label]
    unit_cell_dir = artifacts.sample_dir / "unit_cells"
    return (
        key,
        cell_id,
        target_strut_id,
        unit_cell_dir / f"{key}_cell_{cell_id}.npz",
        unit_cell_dir / f"{key}_cell_{cell_id}.json",
    )


def _open_strut_in_visual_analysis(strut_id: int) -> None:
    """Synchronize one Explorer selection with the Three.js inspection page."""

    st.session_state["selected_strut_id"] = int(strut_id)
    st.session_state["_viewer_selection_pending"] = True
    st.session_state["_pending_primary_navigation"] = "Visual Analysis"
    st.session_state["_pending_visualization"] = "X-ray 3D view"


def _render_defect_tab(table: pd.DataFrame, label: str) -> None:
    candidates = table.loc[table["prediction"] == label].copy()
    st.metric(f"{label.title()} candidates", len(candidates))
    search_column, region_column, orientation_column = st.columns([1, 1, 1.4])
    search = search_column.text_input(
        "Search strut ID",
        key=f"{label}-strut-search",
        placeholder="e.g. 16082",
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
    table_event = st.dataframe(
        visible[display_columns],
        width="stretch",
        height=420,
        hide_index=True,
        key=f"{label}-candidate-table",
        on_select="rerun",
        selection_mode="single-row",
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
    selected_rows = (
        list(table_event.selection.rows)
        if hasattr(table_event, "selection")
        else []
    )
    if selected_rows:
        selected_row = int(selected_rows[0])
        if 0 <= selected_row < len(visible):
            selected_table_id = int(visible.iloc[selected_row]["strut_id"])
            guard_key = f"_last_opened_{label}_strut"
            if st.session_state.get(guard_key) != selected_table_id:
                st.session_state[guard_key] = selected_table_id
                _open_strut_in_visual_analysis(selected_table_id)
                st.rerun()

    if filtered.empty:
        st.info(f"No {label} candidates match the current filters.")
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
    if st.button(
        "Inspect in Visual Analysis",
        key=f"{label}-inspect-selected",
        type="primary",
    ):
        _open_strut_in_visual_analysis(int(selected_id))
        st.rerun()


def render_explorer(artifacts: DashboardArtifacts) -> None:
    st.title("Strut Explorer")
    st.caption("Inspect exploratory defect candidates by classification")
    defect_table = artifacts.table[
        artifacts.table["prediction"].isin(DEFECT_TABS)
    ].copy()
    st.caption(
        "Filter and download candidate records here, then open a selected strut "
        "in the Visual Analysis workspace for registered 3D and CT inspection."
    )
    tabs = st.tabs([label.title() for label in DEFECT_TABS])
    for tab, label in zip(tabs, DEFECT_TABS):
        with tab:
            _render_defect_tab(defect_table, label)


def render_thickness_spatial(artifacts: DashboardArtifacts) -> None:
    st.title("Visual Analysis")
    st.caption("Explore measurements, registered geometry, and CT context")
    _semantic_legend(compact=True)
    pending_visualization = st.session_state.pop("_pending_visualization", None)
    visualization_options = [
        "X-ray 3D view",
        "Unit cell examples (Three.js)",
        "Thickness distribution",
        "Spatial distribution",
        "Classification counts",
    ]
    if pending_visualization in visualization_options:
        st.session_state["visualization-selector"] = pending_visualization
    visualization = st.selectbox(
        "Visualization",
        visualization_options,
        key="visualization-selector",
    )

    if visualization == "X-ray 3D view":
        control_a, control_b = st.columns(2)
        show_intact = control_a.toggle("Show intact struts", value=True)
        context_opacity = control_b.slider(
            "CT context opacity", 0.0, 0.35, 0.10, 0.01
        )
        visible = (
            artifacts.table
            if show_intact
            else artifacts.table[artifacts.table["prediction"] != "intact"]
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
            "Muted blue lines are intact candidates; semantic colors identify the "
            "other exploratory candidate classes."
        )
        _threejs_inspector(artifacts)
    elif visualization == "Unit cell examples (Three.js)":
        _unit_cell_inspector(artifacts)
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
        "Three.js renders all 18,468 registered nominal struts in one blue buffer. "
        "The 60 analyzed struts are selectable overlays with linked registered CT "
        "slice evidence; all other struts remain visual context only."
    )
    scene_path = artifacts.sample_dir / "lattice_scene.npz"
    if not scene_path.is_file():
        st.warning("The compact lattice scene artifact is unavailable.")
        return
    requested_id = st.session_state.get("selected_strut_id")
    valid_ids = set(artifacts.table["strut_id"].astype(int))
    if requested_id is not None and int(requested_id) not in valid_ids:
        requested_id = None
        st.session_state.pop("selected_strut_id", None)
    slice_evidence = None
    if requested_id is not None:
        try:
            slice_evidence = get_strut_slice_evidence(
                int(requested_id),
                crop_size=128,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            st.warning(f"Linked CT slice evidence is unavailable: {exc}")
    try:
        result = lattice_threejs_viewer(
            scene_path,
            selected_strut_id=(
                None if requested_id is None else int(requested_id)
            ),
            slice_evidence=slice_evidence,
        )
    except RuntimeError as exc:
        st.error(f"The interactive lattice inspector could not load: {exc}")
        return

    component_id = getattr(result, "selected_strut_id", None)
    pending_sync = bool(st.session_state.get("_viewer_selection_pending", False))
    if component_id is not None:
        component_id = int(component_id)
    if pending_sync:
        if component_id == requested_id:
            st.session_state.pop("_viewer_selection_pending", None)
    elif component_id != requested_id:
        if component_id is None:
            st.session_state.pop("selected_strut_id", None)
        elif component_id in valid_ids:
            st.session_state["selected_strut_id"] = component_id
        st.rerun()

    selected_id = requested_id
    if selected_id is None:
        st.caption(
            "Choose a candidate class and strut number, or click one of the 60 "
            "analyzed overlays, to inspect saved measurements and linked CT slices."
        )
        return

    rows = artifacts.table.loc[
        artifacts.table["strut_id"] == int(selected_id)
    ]
    if rows.empty:
        st.warning(
            f"Strut {int(selected_id)} is not in the saved 60-strut analysis."
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


def _unit_cell_inspector(
    artifacts: DashboardArtifacts,
) -> None:
    st.subheader("Interactive Unit Cell Inspector (Three.js)")
    st.caption(
        "Three.js renders the 24 canonical unit-cell struts as solid geometry. "
        "Spheres mark their shared endpoints, and the selected exploratory target "
        "is highlighted with its semantic class color."
    )
    selected_label = st.radio(
        "Example",
        list(UNIT_CELL_EXAMPLES),
        horizontal=True,
        key="unit-cell-example",
    )
    key, cell_id, target_strut_id, scene_path, metadata_path = _example_artifacts(
        artifacts,
        selected_label,
    )
    missing = [
        path.name
        for path in (scene_path, metadata_path)
        if not path.is_file()
    ]
    if missing:
        st.warning(f"Unit-cell artifacts are unavailable: {', '.join(missing)}")
        return
    metadata = read_json(metadata_path)
    if int(metadata["target_strut_id"]) != target_strut_id:
        st.error("Unit-cell metadata does not match the approved target strut.")
        return
    st.markdown(
        '<div class="workbench-status">'
        f'<span><strong>{html.escape(selected_label)}</strong> exploratory candidate</span>'
        f'<span>Cell {cell_id}</span><span>Target strut {target_strut_id}</span>'
        '<span>24 canonical nominal struts</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        slice_evidence = get_strut_slice_evidence(target_strut_id, crop_size=128)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        st.warning(f"Linked CT evidence is unavailable: {exc}")
        slice_evidence = None
    try:
        unit_cell_threejs_viewer(
            scene_path,
            slice_evidence=slice_evidence,
            key=f"unit-cell-threejs-{key}",
        )
    except RuntimeError as exc:
        st.error(f"The unit-cell inspector could not load: {exc}")
        return

    st.caption(
        f"Registered mapping: {metadata['selected_mapping']}. The specimen tilt is "
        "preserved. Linked views are locally contrast-scaled supporting evidence, "
        "not ground-truth validation."
    )
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
 registration -> 60-strut selection -> centerline sampling
              -> measurements -> fixed candidate rules
                 |
                 v
     CSV / JSON / PNG / Markdown artifacts
                 |
                 v
        Read-only ArtifactService
                 |
                 v
        Six bounded FastMCP tools
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

**missing → broken → uncertain → thin → intact**
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
            '<span class="muted">60 fixed struts · seed 20260723 · voxel spacing '
            "58.09 µm · JSON (x,y,z) mapped to CT array (z,y,x).</span></div>",
            unsafe_allow_html=True,
        )


COPILOT_PROMPTS = (
    "Compare the saved missing and broken candidates.",
    "Explain how thickness is measured and when it is excluded.",
    "Summarize the registered CT-to-JSON evidence workflow.",
)


def _run_copilot_exchange(prompt: str) -> None:
    """Store one live, evidence-bounded Copilot exchange in session state."""

    history = st.session_state.setdefault("copilot-history", [])
    history.append({"role": "user", "content": prompt})
    with st.spinner("Reviewing saved evidence"):
        response = run_copilot(prompt, page_context={"page": "copilot"})
    history.append(
        {
            "role": "assistant",
            "content": response["answer"],
            "evidence": response["evidence"],
            "warnings": response["warnings"],
            "selected_strut_id": response.get("selected_strut_id"),
        }
    )


def render_copilot(_: DashboardArtifacts) -> None:
    st.title("Analysis Copilot")
    st.caption("A read-only conversational interface for saved lattice evidence")
    status = copilot_status()
    state = "Live" if status["available"] else "Interface ready"
    st.markdown(
        '<div class="copilot-status">'
        f'<span><strong>Coordinator</strong><small>{state}</small></span>'
        f'<span><strong>Measurement and QA</strong><small>{state}</small></span>'
        f'<span><strong>Visualization and reporting</strong><small>{state}</small></span>'
        f'<span><strong>Model</strong><small>{html.escape(status["model"])}</small></span>'
        "</div>",
        unsafe_allow_html=True,
    )
    if not status["available"]:
        st.markdown(
            '<div class="system-notice"><strong>Live calls are disabled.</strong> '
            "The conversation interface and read-only integration boundary are "
            "prepared, but no API key is configured and no external call will be made."
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        """
The **Analysis Coordinator** delegates measurement questions to the
**Measurement and QA Sub-agent** and presentation questions to the
**Visualization and Reporting Sub-agent**. Their factual evidence comes from
read-only MCP tools.
"""
    )
    st.markdown("**Suggested evidence questions**")
    prompt_columns = st.columns(3)
    for column, suggestion in zip(prompt_columns, COPILOT_PROMPTS):
        if column.button(
            suggestion,
            key=f"copilot-suggestion-{suggestion}",
            disabled=not status["available"],
            width="stretch",
        ):
            _run_copilot_exchange(suggestion)
            st.rerun()

    history = st.session_state.setdefault("copilot-history", [])
    if not history:
        st.markdown(
            '<div class="copilot-empty"><strong>No conversation yet</strong>'
            "<span>Responses will cite saved evidence and retain exploratory "
            "classification boundaries.</span></div>",
            unsafe_allow_html=True,
        )
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            evidence = message.get("evidence", [])
            warnings = message.get("warnings", [])
            if evidence:
                with st.expander("Evidence used"):
                    for item in evidence:
                        st.markdown(f"- {item}")
            if warnings:
                st.caption(" ".join(warnings))

    prompt = st.chat_input(
        "Ask about the saved analysis",
        disabled=not status["available"],
    )
    if prompt:
        _run_copilot_exchange(prompt)
        st.rerun()

    st.markdown(
        '<div class="integration-contract"><strong>Future integration contract</strong>'
        "<span>Detector, validator, clustering, measurement, and reporting outputs "
        "will join through stable <code>strut_id</code> references. Unavailable "
        "teammate outputs remain explicitly unavailable rather than inferred.</span>"
        "</div>",
        unsafe_allow_html=True,
    )
