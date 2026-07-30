from __future__ import annotations

import json

from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.dashboard.threejs_component import scene_payload


def test_scene_payload_is_compact_registered_geometry() -> None:
    payload = scene_payload(
        str(DEFAULT_CONFIG.dashboard_scene_path.resolve())
    )

    assert payload["schemaVersion"] == 3
    assert "sceneKind" not in payload
    assert payload["coordinateOrder"] == "zyx"
    assert len(payload["nominalStrutIds"]) == 18_468
    assert len(payload["nominalPositionsZyx"]) == 18_468 * 2 * 3
    assert len(payload["analyzedStrutIds"]) == 18_468
    assert "analyzedPositionsZyx" not in payload
    assert len(payload["analyzedLabelCodes"]) == 18_468
    assert len(payload["analyzedRawLabelCodes"]) == 18_468
    assert payload["rawLabelNames"]
    assert "volume" not in payload
    assert "voxels" not in payload
    assert len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) < 3_000_000
