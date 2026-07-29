from __future__ import annotations

import numpy as np

from defect_cartographer.core.geometry import (
    build_strut_table,
    endpoints_for_struts,
    line_points,
    stratified_sample,
)


def sample_graph() -> dict:
    junctions = []
    struts = []
    identifier = 0
    for z in range(3):
        for y in range(4):
            for x in range(5):
                first = len(junctions)
                junctions.append(
                    {"id": first, "position": [10 * x + 2, 10 * y + 3, 10 * z + 4]}
                )
                junctions.append(
                    {"id": first + 1, "position": [10 * x + 7, 10 * y + 8, 10 * z + 9]}
                )
                struts.append(
                    {"id": identifier, "junction0": first, "junction1": first + 1}
                )
                identifier += 1
    return {"junctions": junctions, "struts": struts, "unit_cells": []}


def test_endpoints_convert_xyz_to_zyx() -> None:
    ids, starts, ends = endpoints_for_struts(sample_graph(), strut_ids=[0])
    assert ids.tolist() == [0]
    assert starts[0].tolist() == [4.0, 3.0, 2.0]
    assert ends[0].tolist() == [9.0, 8.0, 7.0]


def test_centerline_trims_junction_ends() -> None:
    points, parameters = line_points(
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 10.0]),
        spacing_vox=0.5,
        trim_fraction=0.1,
    )
    assert np.isclose(parameters[0], 0.1)
    assert np.isclose(parameters[-1], 0.9)
    assert np.isclose(points[0, 2], 1.0)
    assert np.isclose(points[-1, 2], 9.0)


def test_stratified_sample_is_reproducible_without_review_fields() -> None:
    table = build_strut_table(sample_graph())
    first = stratified_sample(table, sample_size=30, seed=42)
    second = stratified_sample(table, sample_size=30, seed=42)
    assert first["strut_id"].tolist() == second["strut_id"].tolist()
    assert first["strut_id"].nunique() == 30
    assert set(first["region"]) == {"exterior", "interior"}
    assert not {"split", "manual_label", "manual_notes"}.intersection(first.columns)
