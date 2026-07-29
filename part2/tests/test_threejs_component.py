from __future__ import annotations

import json

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.dashboard.threejs_component import scene_payload


def test_scene_payload_is_compact_registered_geometry() -> None:
    payload = scene_payload(
        str((DEFAULT_CONFIG.output_dir / "lattice_scene.npz").resolve())
    )

    assert payload["schemaVersion"] == 1
    assert payload["sceneKind"] == "lattice"
    assert payload["coordinateOrder"] == "zyx"
    assert len(payload["nominalStrutIds"]) == 18_468
    assert len(payload["nominalPositionsZyx"]) == 18_468 * 2 * 3
    assert len(payload["analyzedStrutIds"]) == 60
    assert len(payload["analyzedPositionsZyx"]) == 60 * 2 * 3
    assert len(payload["analyzedLabelCodes"]) == 60
    assert "volume" not in payload
    assert "voxels" not in payload
    assert len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) < 5_000_000
