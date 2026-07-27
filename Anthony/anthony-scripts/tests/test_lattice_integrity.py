"""Tests for the manual strut and junction integrity inspector."""

from __future__ import annotations

import unittest

import numpy as np

from src.inspect_lattice_integrity import (
    JUNCTION_STATES,
    STRUT_STATES,
    assign_junction_states,
    classify_strut,
    sample_strut_cross_sections,
    validate_requested_ids,
    xyz_to_zyx,
    zyx_to_xyz,
)


def strut_metrics(
    continuity: float = 1.0,
    gap: float = 0.0,
    endpoint_0: float = 1.0,
    endpoint_1: float = 1.0,
    diameter: float = 6.0,
    middle: float = 1.0,
) -> dict:
    profile = {
        "continuity": continuity,
        "longest_gap_voxels": gap,
        "gap_center_fraction": 0.5 if gap else None,
        "endpoint_0_support": endpoint_0,
        "endpoint_1_support": endpoint_1,
    }
    return {
        "threshold_metrics": {
            "low": dict(profile),
            "baseline": dict(profile),
            "high": dict(profile),
        },
        "middle_continuity": middle,
        "median_diameter_voxels": diameter,
    }


class CoordinateAndIdTests(unittest.TestCase):
    def test_xyz_zyx_roundtrip(self) -> None:
        points = np.array([[1.0, 2.0, 3.0], [7.0, 8.0, 9.0]])
        np.testing.assert_array_equal(zyx_to_xyz(xyz_to_zyx(points)), points)

    def test_strut_endpoints_are_automatically_included(self) -> None:
        graph = {
            "struts": [{"id": 4, "junction0": 10, "junction1": 11}],
            "junctions": [{"id": 10}, {"id": 11}, {"id": 12}],
        }
        struts, junctions = validate_requested_ids(graph, [4], [12])
        self.assertEqual(struts, [4])
        self.assertEqual(junctions, [10, 11, 12])

    def test_unknown_id_is_rejected(self) -> None:
        graph = {
            "struts": [{"id": 4, "junction0": 10, "junction1": 11}],
            "junctions": [{"id": 10}, {"id": 11}],
        }
        with self.assertRaisesRegex(ValueError, "Unknown strut"):
            validate_requested_ids(graph, [99], [])


class ThicknessTests(unittest.TestCase):
    def test_synthetic_cylinder_diameter(self) -> None:
        volume = np.zeros((41, 41, 41), dtype=np.float32)
        zz, yy, xx = np.indices(volume.shape)
        cylinder = (
            (yy - 20) ** 2 + (zz - 20) ** 2 <= 3**2
        ) & (xx >= 5) & (xx <= 35)
        volume[cylinder] = 100.0
        result = sample_strut_cross_sections(
            volume,
            start_xyz=(5, 20, 20),
            end_xyz=(35, 20, 20),
            threshold=50.0,
        )
        self.assertGreater(np.median(result["diameters_voxels"]), 5.5)
        self.assertLess(np.median(result["diameters_voxels"]), 6.8)


class ProvisionalStrutStateTests(unittest.TestCase):
    def test_good_strut(self) -> None:
        state, _, _ = classify_strut(strut_metrics(), comparison_median_voxels=6)
        self.assertEqual(state, "good")

    def test_persistent_gap_is_likely_discontinuous(self) -> None:
        state, _, _ = classify_strut(
            strut_metrics(continuity=0.75, gap=4.0),
            comparison_median_voxels=6,
        )
        self.assertEqual(state, "likely_discontinuous")

    def test_endpoint_gap_is_endpoint_disconnected(self) -> None:
        state, _, _ = classify_strut(
            strut_metrics(
                continuity=0.90,
                endpoint_0=0.30,
                endpoint_1=1.0,
                middle=1.0,
            ),
            comparison_median_voxels=6,
        )
        self.assertEqual(state, "endpoint_disconnected")

    def test_thin_continuous_strut(self) -> None:
        state, _, _ = classify_strut(
            strut_metrics(diameter=3.5),
            comparison_median_voxels=6,
        )
        self.assertEqual(state, "thin_continuous")

    def test_strut_state_is_bounded(self) -> None:
        state, _, _ = classify_strut(
            strut_metrics(continuity=0.85, gap=1.0),
            comparison_median_voxels=6,
        )
        self.assertIn(state, STRUT_STATES)


class ProvisionalJunctionStateTests(unittest.TestCase):
    @staticmethod
    def row(identifier: int, degree: int, supported: int, volume: float) -> dict:
        return {
            "junction_id": identifier,
            "expected_degree": degree,
            "supported_branches": supported,
            "component_volume_voxels": volume,
            "equivalent_diameter_voxels": volume ** (1 / 3),
            "radial_asymmetry": 0.2,
        }

    def test_missing_branch_is_under_fused(self) -> None:
        rows = [self.row(1, 4, 3, 100)]
        assign_junction_states(rows)
        self.assertEqual(rows[0]["integrity_state"], "junction_under_fused")

    def test_peer_comparison_is_withheld_with_fewer_than_three(self) -> None:
        rows = [self.row(1, 4, 4, 100), self.row(2, 4, 4, 105)]
        assign_junction_states(rows)
        self.assertFalse(rows[0]["morphology_comparison_available"])
        self.assertIn(rows[0]["integrity_state"], JUNCTION_STATES)

    def test_large_same_degree_outlier_is_malformed(self) -> None:
        rows = [
            self.row(1, 4, 4, 100),
            self.row(2, 4, 4, 102),
            self.row(3, 4, 4, 1000),
        ]
        assign_junction_states(rows)
        self.assertEqual(
            rows[2]["integrity_state"], "junction_enlarged_or_malformed"
        )


if __name__ == "__main__":
    unittest.main()
