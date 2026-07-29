from __future__ import annotations

import json

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.dashboard.threejs_component import scene_payload


def test_scene_payload_is_compact_registered_geometry() -> None:
    payload = scene_payload(
        str((DEFAULT_CONFIG.output_dir / "lattice_scene.npz").resolve())
    )

    assert payload["schemaVersion"] == 2
    assert payload["sceneKind"] == "lattice"
    assert payload["coordinateOrder"] == "zyx"
    assert len(payload["nominalStrutIds"]) == 18_468
    assert len(payload["nominalPositionsZyx"]) == 18_468 * 2 * 3
    assert len(payload["junctionIds"]) == 10_206
    assert len(payload["junctionPositionsZyx"]) == 10_206 * 3
    assert len(payload["nominalJunctionIds"]) == 18_468 * 2
    assert len(payload["analyzedStrutIds"]) == 60
    assert len(payload["analyzedPositionsZyx"]) == 60 * 2 * 3
    assert len(payload["analyzedLabelCodes"]) == 60
    assert payload["xrayVertexTexture"] == []
    assert "volume" not in payload
    assert "voxels" not in payload
    assert payload["palette"]["nominal"] == "#215290"
    assert payload["palette"]["nodes"] == "#8FB9E3"
    assert payload["palette"]["candidates"]["intact"] == "#2E7D32"
    assert payload["palette"]["candidates"]["missing"] == "#D81B60"
    assert payload["palette"]["candidates"]["broken"] == "#FFC107"
    assert payload["palette"]["candidates"]["thin"] == "#7B2CBF"
    assert payload["palette"]["candidates"]["uncertain"] == "#E76F00"
    assert payload["palette"]["segmentation"] == "#00C2D7"
    assert payload["palette"]["expectedCenterline"] == "#FFD60A"
    assert payload["palette"]["observedCenterline"] == "#FF2D92"
    assert len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) < 6_000_000
