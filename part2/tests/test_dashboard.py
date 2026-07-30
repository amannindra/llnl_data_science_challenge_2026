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


def test_dashboard_data_filters_without_mutation() -> None:
    artifacts = load_dashboard_artifacts()
    original = artifacts.table.copy(deep=True)
    selected = filter_table(
        artifacts.table,
        classes=["missing", "broken"],
        occupancy_range=(0.0, 1.0),
        gap_range=(0.0, 1.0),
    )

    assert len(selected) == 376
    assert set(selected["prediction"]) == {"missing", "broken"}
    assert artifacts.table.equals(original)


def test_dashboard_figures_use_consistent_candidate_colors() -> None:
    table = load_dashboard_artifacts().table
    counts = class_count_figure(table)
    lattice = lattice_3d_figure(table[table["prediction"] != "healthy"])

    assert list(counts.data[0].marker.color) == [
        CHART_CLASS_COLORS[label]
        for label in ["missing", "broken", "thin", "thick", "bent_or_misaligned", "uncertain", "healthy", "not_applicable"]
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
        CANDIDATE_COLORS["bent_or_misaligned"],
        CANDIDATE_COLORS["not_applicable"],
    }


def test_streamlit_overview_renders_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()

    assert not app.exception
    assert app.title[0].value == "Lattice CT Explorer"
    assert len(app.metric) >= 5
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
