import json

import numpy as np
import tifffile

from Aman_src.mcp_server import register_json_to_tiff


def test_registration_manual_preserves_topology_and_applies_xyz_transform(tmp_path):
    source = tmp_path / "lattice.json"
    volume = tmp_path / "scan.tif"
    output = tmp_path / "registered.json"
    payload = {
        "junctions": [
            {"id": 0, "position": [1.0, 1.0, 1.0]},
            {"id": 1, "position": [2.0, 1.0, 1.0]},
            {"id": 2, "position": [1.0, 2.0, 1.0]},
        ],
        "struts": [{"id": 0, "junction0": 0, "junction1": 1}],
        "unit_cells": [],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")
    scan = np.zeros((8, 8, 8), dtype=np.uint8)
    scan[2:6, 2:6, 2:6] = 2
    tifffile.imwrite(volume, scan)

    result = register_json_to_tiff(
        str(source), str(volume), str(output), mode="manual",
        translation_xyz=[2, 3, 4], rotation_xyz_degrees=[0, 0, 0],
        scale_xyz=[2, 2, 2], threshold=1, max_points=100,
    )

    assert result.startswith("Saved registered JSON")
    registered = json.loads(output.read_text(encoding="utf-8"))
    assert registered["junctions"][0]["position"] == [4.0, 5.0, 6.0]
    assert registered["struts"] == payload["struts"]
    assert registered["registration"]["tilt_acknowledged"] is True
    assert registered["registration"]["source_coordinate_order"] == "XYZ"


def test_registration_requires_manual_parameters(tmp_path):
    source = tmp_path / "lattice.json"
    volume = tmp_path / "scan.tif"
    output = tmp_path / "registered.json"
    source.write_text(json.dumps({"junctions": [
        {"id": i, "position": [float(i), 0, 0]} for i in range(3)
    ], "struts": [], "unit_cells": []}), encoding="utf-8")
    tifffile.imwrite(volume, np.ones((3, 3, 3), dtype=np.uint8))

    result = register_json_to_tiff(
        str(source), str(volume), str(output), mode="manual", threshold=0.5,
    )
    assert result.startswith("Error: Registration failed:")
    assert not output.exists()
