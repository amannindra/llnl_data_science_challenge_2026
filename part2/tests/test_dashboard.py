"""Tests for dashboard data, figures, and the initial Streamlit render."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from defect_cartographer.dashboard.data import (
    filter_table,
    load_dashboard_artifacts,
)
from defect_cartographer.dashboard.figures import (
    CANDIDATE_COLORS,
    CHART_CLASS_COLORS,
    class_count_figure,
)
from defect_cartographer.dashboard.pages import SEMANTIC_SYMBOLS
from defect_cartographer.dashboard.threejs_component import _component_renderer


def test_dashboard_data_filters_without_mutation() -> None:
    artifacts = load_dashboard_artifacts()
    original = artifacts.table.copy(deep=True)
    selected = filter_table(
        artifacts.table,
        classes=["missing", "broken"],
        occupancy_range=(0.0, 1.0),
        gap_range=(0.0, 1.0),
    )

    # The integration checkout reads Aman's automated full 18,468-row artifact.
    assert len(selected) == 374
    assert set(selected["prediction"]) == {"missing", "broken"}
    assert artifacts.table.equals(original)


def test_dashboard_figures_use_consistent_candidate_colors() -> None:
    table = load_dashboard_artifacts().table
    counts = class_count_figure(table)

    assert CANDIDATE_COLORS == {
        "intact": "#FFD60A",
        "missing": "#FF453A",
        "broken": "#0A84FF",
        "uncertain": "#30D158",
    }
    assert list(counts.data[0].marker.color) == [
        CHART_CLASS_COLORS[label]
        for label in ["missing", "broken", "uncertain", "intact"]
    ]
    assert counts.layout.paper_bgcolor == "#FFFFFF"
    assert counts.layout.plot_bgcolor == "#FFFFFF"


def test_dashboard_declares_accessible_classification_symbols() -> None:
    assert SEMANTIC_SYMBOLS == {
        "missing": "×",
        "broken": "∥",
        "uncertain": "?",
        "intact": "✓",
        "nominal": "◇",
    }


def test_streamlit_overview_renders_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()

    assert not app.exception
    assert app.title[0].value == "Lattice CT Explorer"
    assert len(app.metric) >= 5
    assert any(
        "Haseeb Ahmad · Ulices Ramirez · Anthony Ching · Aman Nindra"
        in markdown.value
        for markdown in app.markdown
    )
    assets = app_path.parent / "assets" / "branding"
    for asset_name in (
        "dsc-logo.png",
        "uc-merced-logo.webp",
        "ucr-primary-horizontal.png",
        "llnl-logo.webp",
    ):
        assert (assets / asset_name).stat().st_size > 0
    header_markup = "\n".join(markdown.value for markdown in app.markdown)
    assert 'alt="University of California, Merced"' in header_markup
    assert 'aria-label="University of California, Riverside"' in header_markup
    assert header_markup.index("brand-logo-dsc") < header_markup.index(
        "brand-logo-merced"
    )
    assert header_markup.index("brand-logo-merced") < header_markup.index(
        "brand-logo-riverside"
    )
    assert header_markup.index("brand-logo-riverside") < header_markup.index(
        "brand-logo-llnl"
    )


def test_all_dashboard_views_render_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    expected_titles = {
        "Strut Explorer": "Strut Explorer",
        "Visual Analysis": "Visual Analysis",
        "System Design": "System Design",
        "Copilot": "Analysis Copilot",
    }

    for page, title in expected_titles.items():
        app = app.radio[0].set_value(page).run(timeout=20)
        assert not app.exception
        assert app.title[0].value == title


def test_visual_analysis_has_no_unit_cell_workspace() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    _component_renderer.cache_clear()
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    app = app.radio[0].set_value("Visual Analysis").run(timeout=30)
    assert not app.exception
    assert app.selectbox[0].options[0] == "Full lattice (Three.js)"
    assert "X-ray 3D view" not in app.selectbox[0].options
    assert "Unit cell examples (Three.js)" not in app.selectbox[0].options
    assert not any(toggle.label == "Presentation Mode" for toggle in app.toggle)
    assert (
        sum(
            'aria-label="Classification legend"' in markdown.value
            for markdown in app.markdown
        )
        == 1
    )

    assert not any(
        subheader.value == "Interactive Unit Cell Inspector (Three.js)"
        for subheader in app.subheader
    )
