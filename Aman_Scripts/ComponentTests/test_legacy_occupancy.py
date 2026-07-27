#!/usr/bin/env python3
"""Synthetic-only checks for the preserved legacy occupancy diagnostic."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import tifffile

from _harness import Checker
from Components.lattice_graph import parse_lattice_graph
from Components.legacy_occupancy import centerline_occupancy, otsu_threshold, sphere_offsets


def _graph() -> object:
    return parse_lattice_graph({
        "junctions": [
            {"id": 10, "position": [2, 4, 4]},
            {"id": 30, "position": [7, 4, 4]},
            {"id": 50, "position": [2, 7, 7]},
            {"id": 70, "position": [7, 7, 7]},
        ],
        "struts": [
            {"id": 101, "junction0": 10, "junction1": 30, "thickness": 1},
            {"id": 303, "junction0": 50, "junction1": 70, "thickness": 1},
        ],
        "unit_cells": [],
    })


def main() -> int:
    check = Checker("legacy_occupancy", minimum_checks=10)
    check.equal("radius zero contains origin only", sphere_offsets(0), ((0, 0, 0),))
    check.equal("radius one has seven lattice points", len(sphere_offsets(1)), 7)
    check.check("radius one excludes cube diagonal", (1, 1, 1) not in sphere_offsets(1))
    check.raises("negative radius rejected", ValueError, sphere_offsets, -1)
    check.raises("boolean radius rejected", ValueError, sphere_offsets, True)
    split = otsu_threshold(np.array([0] * 100 + [10] * 100, dtype=np.float32), bins=32)
    check.check("Otsu split lies between two modes", 0 <= split < 10, str(split))
    check.equal("constant Otsu sample returns constant", otsu_threshold(np.ones(10) * 7), 7.0)
    check.raises("empty Otsu sample rejected", ValueError, otsu_threshold, np.array([]))
    check.raises("too few Otsu bins rejected", ValueError, otsu_threshold, np.arange(5), bins=1)

    graph = _graph()
    volume = np.zeros((10, 10, 10), dtype=np.uint16)
    volume[4, 4, 1:9] = 100
    original = volume.copy()
    result = centerline_occupancy(
        volume, graph, material_threshold=50, n_samples=9, radius=0, missing_cutoff=0.3,
    )
    check.equal("noncontiguous source strut IDs preserved", result.strut_ids.tolist(), [101, 303])
    check.equal("noncontiguous endpoint IDs preserved", result.junction0_ids.tolist(), [10, 50])
    check.close("fully supported synthetic strut has occupancy one", float(result.occupancy[0]), 1.0)
    check.close("empty synthetic corridor has occupancy zero", float(result.occupancy[1]), 0.0)
    check.equal("only empty corridor is candidate missing", result.candidate_missing.tolist(), [False, True])
    check.equal("midpoints remain in XYZ order", result.midpoints_xyz.tolist(), [[4.5, 4.0, 4.0], [4.5, 7.0, 7.0]])
    check.equal("material threshold preserved", result.material_threshold, 50.0)
    check.equal("missing cutoff preserved", result.missing_cutoff, 0.3)
    check.check("occupancy never mutates input volume", np.array_equal(volume, original))
    check.raises("2D volume rejected", ValueError, centerline_occupancy, np.zeros((4, 4)), graph)
    check.raises("one centerline sample rejected", ValueError, centerline_occupancy, volume, graph, n_samples=1)
    check.raises("invalid missing cutoff rejected", ValueError, centerline_occupancy, volume, graph, missing_cutoff=2)
    check.raises("nonfinite material threshold rejected", ValueError, centerline_occupancy, volume, graph, material_threshold=float("nan"))
    check.raises("fractional sample count rejected", ValueError, centerline_occupancy, volume, graph, n_samples=2.9)
    check.raises("fractional threshold stride rejected", ValueError, centerline_occupancy, volume, graph, threshold_sample_stride=2.9)
    signed = np.full((10, 10, 10), -10.0, dtype=np.float32)
    signed_result = centerline_occupancy(signed, graph, material_threshold=-5, radius=1)
    check.equal("negative background is not replaced by invented zero intensity",
                signed_result.occupancy.tolist(), [0.0, 0.0])

    from analyze_json import run_legacy_occupancy

    with tempfile.TemporaryDirectory(prefix="dssi_legacy_artifacts_") as temporary:
        root = Path(temporary)
        tiff_path = root / "fixture.tiff"
        tifffile.imwrite(tiff_path, volume, imagej=True, metadata={"axes": "ZYX"})
        destination = root / "outputs"
        destination.mkdir()
        artifacts = run_legacy_occupancy(graph, tiff_path, destination)
        check.equal("legacy CSV keeps established filename", artifacts["csv"].name, "json_target_strut_occupancy.csv")
        check.equal("legacy figure keeps established filename", artifacts["figure"].name, "json_target_missing_struts.png")
        check.check("legacy figure is nonempty", artifacts["figure"].stat().st_size > 0)
        csv_lines = artifacts["csv"].read_text().splitlines()
        check.equal("legacy CSV keeps established schema",
                    csv_lines[0], "strut_id,junction0,junction1,midx,midy,midz,occupancy,missing")
        check.equal("legacy CSV writes one row per strut", len(csv_lines), 3)
    return check.done()


if __name__ == "__main__":
    raise SystemExit(main())
