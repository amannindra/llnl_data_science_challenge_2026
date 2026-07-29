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
    lattice_3d_figure,
)
from defect_cartographer.dashboard.pages import UNIT_CELL_EXAMPLES


def test_dashboard_data_filters_without_mutation() -> None:
    artifacts = load_dashboard_artifacts()
    original = artifacts.table.copy(deep=True)
    selected = filter_table(
        artifacts.table,
        classes=["missing", "broken"],
        occupancy_range=(0.0, 1.0),
        gap_range=(0.0, 1.0),
    )

    assert len(selected) == 3
    assert set(selected["prediction"]) == {"missing", "broken"}
    assert artifacts.table.equals(original)


def test_dashboard_figures_use_consistent_candidate_colors() -> None:
    table = load_dashboard_artifacts().table
    counts = class_count_figure(table)
    lattice = lattice_3d_figure(table[table["prediction"] != "intact"])

    assert list(counts.data[0].marker.color) == [
        CHART_CLASS_COLORS[label]
        for label in ["missing", "broken", "thin", "uncertain", "intact"]
    ]
    trace_colors = {
        trace.line.color
        for trace in lattice.data
        if getattr(trace, "mode", None) == "lines"
    }
    assert trace_colors == {
        CANDIDATE_COLORS["missing"],
        CANDIDATE_COLORS["broken"],
        CANDIDATE_COLORS["thin"],
        CANDIDATE_COLORS["uncertain"],
    }


def test_dashboard_declares_four_traceable_unit_cell_examples() -> None:
    assert UNIT_CELL_EXAMPLES == {
        "Broken": ("broken", 521, 12958),
        "Missing": ("missing", 646, 16082),
        "Thin": ("thin", 605, 15040),
        "Intact": ("intact", 362, 9000),
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
    assert (assets / "dsc-logo.png").stat().st_size > 0
    assert (assets / "llnl-logo.webp").stat().st_size > 0


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
