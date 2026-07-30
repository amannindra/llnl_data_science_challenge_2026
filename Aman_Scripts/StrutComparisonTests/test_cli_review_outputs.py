"""Operational tests for distinct error and review CSV handoffs."""

from __future__ import annotations

import csv

import pytest

from Aman_Scripts.compare_stl_tiff_struts import (
    _write_candidate_csv,
    _write_review_csv,
    parse_args,
)


def _record(identifier: int, *, has_error, applicable=True, review=True) -> dict:
    return {
        "id": identifier,
        "edge_id": f"E{identifier}",
        "junction0": identifier * 2,
        "junction1": identifier * 2 + 1,
        "endpoint0_xyz_voxel": [1.0, 2.0, 3.0],
        "endpoint1_xyz_voxel": [4.0, 5.0, 6.0],
        "comparison_applicable": applicable,
        "has_error": has_error,
        "review_required": review,
        "confidence": 0.0,
        "realized_axial_fraction": 0.4,
        "longest_unrealized_gap_voxels": 7,
        "bridge_connected_26": False,
        "stl_to_ct_near_fraction": 0.5,
        "decision_reason": "synthetic",
        "absolute_threshold_has_error": has_error is None,
        "absolute_threshold_decision_reason": "absolute-synthetic",
        "contrast_review_authorized": has_error is None,
        "contrast_shift_agreement": 1.0 if has_error is None else 0.0,
    }


def _rows(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_error_and_review_csvs_are_disjoint_and_keep_review_veto(tmp_path) -> None:
    payload = {
        "struts": [
            _record(1, has_error=True),
            _record(2, has_error=None),
            _record(3, has_error=False, review=False),
            _record(4, has_error=None, applicable=False, review=False),
        ]
    }
    error_rows = _rows(_write_candidate_csv(tmp_path, payload))
    review_rows = _rows(_write_review_csv(tmp_path, payload))
    assert [row["strut_id"] for row in error_rows] == ["1"]
    assert [row["strut_id"] for row in review_rows] == ["2"]
    assert review_rows[0]["contrast_review_authorized"] == "True"
    assert review_rows[0]["absolute_threshold_has_error"] == "True"


@pytest.mark.parametrize("value", ["0", "-0.1", "1.1", "nan", "inf"])
def test_cli_rejects_degenerate_contrast_fraction(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--minimum-local-contrast-fraction", value])


def test_cli_explicit_disable_flag_is_recorded() -> None:
    arguments = parse_args(["--disable-local-contrast-review"])
    assert arguments.disable_local_contrast_review is True
    assert arguments.minimum_local_contrast_fraction == pytest.approx(0.25)

