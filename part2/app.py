"""Streamlit entry point for the Lattice CT Explorer dashboard."""

from __future__ import annotations

import base64
from functools import lru_cache
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


@lru_cache(maxsize=8)
def _asset_data_uri(path: Path) -> str:
    """Return a small local branding asset as an embedded browser-safe URI."""

    media_types = {
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_types.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported branding asset format: {path.suffix}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _render_brand_header() -> None:
    branding_dir = PART2_DIR / "assets" / "branding"
    assets = {
        "dsc": _asset_data_uri(branding_dir / "dsc-logo.png"),
        "merced": _asset_data_uri(branding_dir / "uc-merced-logo.webp"),
        "riverside": _asset_data_uri(
            branding_dir / "ucr-primary-horizontal.png"
        ),
        "llnl": _asset_data_uri(branding_dir / "llnl-logo.webp"),
    }
    st.markdown(
        f"""
<div class="brand-header">
  <img class="brand-logo brand-logo-dsc" src="{assets['dsc']}"
       alt="Data Science Challenge">
<div class="brand-title">
  <span>2026 Data Science Challenge</span>
  <strong>Lattice CT Analysis</strong>
  <div class="team-byline">Haseeb Ahmad · Ulices Ramirez · Anthony Ching · Aman Nindra</div>
</div>
  <img class="brand-logo brand-logo-merced" src="{assets['merced']}"
       alt="University of California, Merced">
  <svg class="brand-logo brand-logo-riverside"
       viewBox="24 45 238 70"
       preserveAspectRatio="xMidYMid meet"
       role="img"
       aria-label="University of California, Riverside">
    <image href="{assets['riverside']}" width="600" height="146"></image>
  </svg>
  <img class="brand-logo brand-logo-llnl" src="{assets['llnl']}"
       alt="Lawrence Livermore National Laboratory">
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="brand-divider"></div>', unsafe_allow_html=True)


def main() -> None:
    """Render one dashboard page selected from the sidebar."""

    st.set_page_config(
        page_title="Lattice CT Explorer",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
<style>
    :root {
        color-scheme: light;
        --canvas: #FFFFFF;
        --workspace: #F2F5F8;
        --card: #F7F9FB;
        --ink: #16202A;
        --muted: #5E6B78;
        --accent: #215290;
        --accent-dark: #12365D;
        --accent-mid: #8FB9E3;
        --accent-light: #C3D4E3;
        --challenge-green: #9CCB3B;
        --chart-green: #2E7D32;
        --chart-magenta: #D81B60;
        --chart-yellow: #FFC107;
        --chart-purple: #7B2CBF;
        --chart-orange: #E76F00;
        --divider: #C9D5E1;
    }
    html, body, [class*="css"], .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                     "Helvetica Neue", Arial, sans-serif;
        color: var(--ink);
    }
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] { background: var(--canvas) !important; }
    .brand-header {
        align-items: center;
        display: grid;
        gap: 16px;
        grid-template-columns:
            72px minmax(280px, 1fr)
            minmax(120px, 0.82fr)
            minmax(120px, 0.82fr)
            minmax(140px, 0.92fr);
        width: 100%;
    }
    .brand-logo {
        display: block;
        height: auto;
        max-height: 52px;
        max-width: 100%;
        object-fit: contain;
        width: 100%;
    }
    .brand-logo-dsc {
        justify-self: start;
        max-height: 64px;
        width: 64px;
    }
    .brand-logo-merced,
    .brand-logo-riverside,
    .brand-logo-llnl {
        justify-self: end;
    }
    .brand-title {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 0;
    }
    .brand-title span {
        color: var(--accent);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .brand-title strong {
        color: var(--ink);
        font-size: 1.35rem;
        letter-spacing: -0.025em;
    }
    .team-byline {
        color: var(--muted);
        font-size: 0.76rem;
        line-height: 1.35;
        overflow-wrap: anywhere;
    }
    .brand-divider {
        border-bottom: 3px solid var(--accent);
        box-shadow: 0 1px 0 var(--challenge-green);
        margin: 8px 0 18px;
    }
    @media (max-width: 960px) {
        .brand-header {
            grid-template-columns: 64px repeat(4, minmax(0, 1fr));
            gap: 12px;
        }
        .brand-logo-dsc {
            grid-column: 1;
            grid-row: 1;
            width: 56px;
        }
        .brand-title {
            grid-column: 2 / -1;
            grid-row: 1;
        }
        .brand-logo-merced {
            grid-column: 1 / 3;
            grid-row: 2;
        }
        .brand-logo-riverside {
            grid-column: 3 / 5;
            grid-row: 2;
        }
        .brand-logo-llnl {
            grid-column: 5;
            grid-row: 2;
        }
        .brand-logo-merced,
        .brand-logo-riverside,
        .brand-logo-llnl {
            justify-self: center;
            max-height: 44px;
        }
    }
    .block-container {
        max-width: 1640px;
        padding: 24px 32px 96px;
    }
    h1 {
        color: var(--accent-dark) !important;
        font-size: clamp(2rem, 3vw, 2.65rem) !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
        line-height: 1.1 !important;
        margin-bottom: 4px !important;
    }
    h2, h3 {
        color: var(--accent-dark) !important;
        letter-spacing: -0.01em !important;
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
        display: none;
    }
    [data-testid="stMetric"] {
        background: var(--card);
        border: 1px solid var(--divider);
        border-left: 4px solid var(--accent);
        border-radius: 8px;
        padding: 16px;
        min-height: 98px;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        letter-spacing: -0.03em;
    }
    div[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {
        background: var(--canvas);
        border: 1px solid var(--divider);
        border-radius: 10px;
        overflow: hidden;
        padding: 8px;
    }
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] > div,
    [data-baseweb="tab-panel"],
    [data-baseweb="select"] > div,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {
        background-color: #FFFFFF !important;
        color: var(--ink) !important;
        color-scheme: light !important;
    }
    .agent-card, .definition-card, .scope-card {
        background: var(--card);
        border: 1px solid var(--divider);
        border-top: 4px solid var(--accent);
        border-radius: 8px;
        padding: 18px;
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
        background: var(--accent-dark);
        border: 1px solid var(--accent-dark);
        border-radius: 8px;
        box-shadow: 0 4px 16px rgba(18, 54, 93, 0.14);
        margin-bottom: 16px;
        padding: 6px 12px;
        position: static;
    }
    .st-key-primary-navigation {
        position: sticky;
        top: 0.5rem;
        z-index: 900;
    }
    [data-testid="stElementContainer"] {
        scroll-margin-top: 4rem;
    }
    iframe[title="lattice_threejs_viewer"] {
        display: block;
        overflow: visible;
        width: 100%;
    }
    div[role="radiogroup"][aria-label="Primary navigation"] label,
    div[role="radiogroup"][aria-label="Primary navigation"] p {
        color: #FFFFFF !important;
        font-weight: 650;
    }
    .muted { color: var(--muted); }
    .stButton > button[kind="primary"] {
        background: var(--accent);
        border: 0;
        border-radius: 6px;
        padding: 8px 24px;
    }
    .stButton > button:not([kind="primary"]) {
        border-color: var(--divider);
        border-radius: 6px;
    }
    div[data-baseweb="tab-list"] {
        background: var(--workspace);
        border-radius: 8px;
        padding: 4px;
    }
    .workbench-status, .copilot-status {
        align-items: center;
        background: var(--workspace);
        border: 1px solid var(--divider);
        border-radius: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px 24px;
        margin: 12px 0;
        padding: 10px 14px;
    }
    .workbench-status span {
        color: var(--muted);
        font-size: 0.8rem;
    }
    .workbench-status span:first-child {
        color: var(--accent-dark);
        border-left: 4px solid var(--challenge-green);
        padding-left: 10px;
    }
    .copilot-status {
        align-items: stretch;
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .copilot-status span {
        background: #FFFFFF;
        border: 1px solid var(--divider);
        border-radius: 6px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 10px 12px;
    }
    .copilot-status small { color: var(--muted); }
    .system-notice, .integration-contract, .copilot-empty {
        background: var(--card);
        border: 1px solid var(--divider);
        border-left: 4px solid var(--challenge-green);
        border-radius: 8px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin: 12px 0 20px;
        padding: 14px 16px;
    }
    .copilot-empty {
        align-items: center;
        border-left-color: var(--accent);
        color: var(--muted);
        justify-content: center;
        min-height: 150px;
        text-align: center;
    }
    .integration-contract span { color: var(--muted); }
    .semantic-legend {
        align-items: center;
        background: var(--workspace);
        border: 1px solid var(--divider);
        border-radius: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px 18px;
        margin: 10px 0 18px;
        padding: 10px 14px;
    }
    .semantic-legend.compact { margin: 8px 0 12px; }
    .semantic-legend-item {
        align-items: center;
        color: var(--ink);
        display: inline-flex;
        font-size: 0.8rem;
        font-weight: 600;
        gap: 7px;
    }
    .semantic-legend-item b {
        align-items: center;
        border: 1px solid rgba(22, 32, 42, 0.24);
        border-radius: 50%;
        color: #FFFFFF;
        display: inline-flex;
        font-size: 0.7rem;
        height: 20px;
        justify-content: center;
        width: 20px;
    }
    .semantic-legend-item:nth-child(2) b { color: #16202A; }
    button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    textarea:focus-visible,
    [tabindex]:focus-visible {
        outline: 3px solid #0066CC !important;
        outline-offset: 3px !important;
    }
    hr { border-color: var(--divider) !important; }
    @media (max-width: 900px) {
        .block-container { padding: 20px 16px 48px; }
        .copilot-status { grid-template-columns: 1fr 1fr; }
    }
</style>
""",
        unsafe_allow_html=True,
    )
    _render_brand_header()
    pending_page = st.session_state.pop("_pending_primary_navigation", None)
    if pending_page in PAGES:
        st.session_state["primary-navigation"] = pending_page
    page_name = st.radio(
        "Primary navigation",
        list(PAGES),
        horizontal=True,
        label_visibility="collapsed",
        key="primary-navigation",
    )

    try:
        artifacts = load_dashboard_artifacts()
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Dashboard artifacts are unavailable: {exc}")
        st.stop()
    PAGES[page_name](artifacts)


if __name__ == "__main__":
    main()
