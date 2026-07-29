"""Streamlit entry point for the Lattice CT Explorer dashboard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from defect_cartographer.dashboard.data import load_dashboard_artifacts
from defect_cartographer.dashboard.pages import (
    render_architecture,
    render_copilot,
    render_explorer,
    render_overview,
    render_thickness_spatial,
)


PAGES = {
    "Overview": render_overview,
    "Strut Explorer": render_explorer,
    "Visual Analysis": render_thickness_spatial,
    "System Design": render_architecture,
    "Copilot": render_copilot,
}
PART2_DIR = Path(__file__).resolve().parent


def _render_brand_header() -> None:
    left, center, right = st.columns([1, 4, 1.8], vertical_alignment="center")
    with left:
        st.image(
            PART2_DIR / "assets" / "branding" / "dsc-logo.png",
            width=104,
        )
    with center:
        st.markdown(
            """
<div class="brand-title">
  <span>2026 Data Science Challenge</span>
  <strong>Lattice CT Analysis</strong>
</div>
""",
            unsafe_allow_html=True,
        )
    with right:
        st.image(
            PART2_DIR / "assets" / "branding" / "llnl-logo.webp",
            width=220,
        )
    st.markdown('<div class="brand-divider"></div>', unsafe_allow_html=True)


def main() -> None:
    """Render one dashboard page selected from the sidebar."""

    st.set_page_config(
        page_title="Lattice CT Explorer",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
<style>
    :root {
        --canvas: #FFFFFF;
        --card: #F5F5F7;
        --ink: #1D1D1F;
        --muted: #86868B;
        --accent: #215290;
        --accent-mid: #507DAB;
        --accent-light: #C3D4E3;
        --chart-green: #A8C75D;
        --chart-red: #D56364;
        --chart-cyan: #69C5EF;
        --divider: #E8E8ED;
    }
    html, body, [class*="css"], .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                     "Helvetica Neue", Arial, sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--canvas); }
    .brand-title {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 8px 0;
    }
    .brand-title span {
        color: var(--accent);
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .brand-title strong {
        color: var(--ink);
        font-size: 1.55rem;
        letter-spacing: -0.025em;
    }
    .brand-divider {
        border-bottom: 1px solid var(--divider);
        margin: 16px 0 32px;
    }
    .block-container {
        max-width: 1440px;
        padding: 64px 48px 96px;
    }
    h1 {
        font-size: clamp(2.5rem, 4vw, 3.5rem) !important;
        font-weight: 650 !important;
        letter-spacing: -0.035em !important;
        line-height: 1.08 !important;
        margin-bottom: 8px !important;
    }
    h2, h3 {
        color: var(--ink) !important;
        letter-spacing: -0.02em !important;
    }
    p, li { line-height: 1.45; }
    [data-testid="stSidebar"] { background: var(--card); }
    [data-testid="stSidebar"] > div { padding: 32px 16px; }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4 { color: var(--ink) !important; }
    [data-testid="stSidebar"] input { accent-color: var(--accent) !important; }
    [data-testid="stHeader"] {
        background: var(--canvas);
        border-bottom: 1px solid var(--divider);
    }
    [data-testid="stMetric"] {
        background: var(--card);
        border: 0;
        border-radius: 20px;
        padding: 24px;
        min-height: 128px;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        letter-spacing: -0.03em;
    }
    div[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {
        background: var(--canvas);
        border: 1px solid var(--divider);
        border-radius: 20px;
        overflow: hidden;
        padding: 8px;
    }
    .agent-card, .definition-card, .scope-card {
        background: var(--card);
        border-radius: 20px;
        padding: 24px;
        height: 100%;
    }
    .agent-card h3, .definition-card h3 { margin-top: 0; margin-bottom: 8px; }
    .agent-label {
        color: var(--muted);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    div[role="radiogroup"][aria-label="Primary navigation"] {
        background: var(--card);
        border-radius: 98px;
        padding: 8px 16px;
        margin-bottom: 48px;
    }
    .muted { color: var(--muted); }
    .stButton > button[kind="primary"] {
        background: var(--accent);
        border: 0;
        border-radius: 98px;
        padding: 8px 24px;
    }
    .stButton > button:not([kind="primary"]) { border-radius: 12px; }
    hr { border-color: var(--divider) !important; }
    @media (max-width: 900px) {
        .block-container { padding: 32px 16px 64px; }
    }
</style>
""",
        unsafe_allow_html=True,
    )
    _render_brand_header()
    page_name = st.radio(
        "Primary navigation",
        list(PAGES),
        horizontal=True,
        label_visibility="collapsed",
    )

    try:
        artifacts = load_dashboard_artifacts()
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Dashboard artifacts are unavailable: {exc}")
        st.stop()
    PAGES[page_name](artifacts)


if __name__ == "__main__":
    main()
