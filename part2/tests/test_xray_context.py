"""Tests for bounded CT context generation and loading."""

from __future__ import annotations

import numpy as np

from defect_cartographer.core.xray_context import load_xray_context


def test_load_xray_context_validates_schema(tmp_path) -> None:
    path = tmp_path / "context.npz"
    np.savez_compressed(
        path,
        vertices_zyx=np.zeros((4, 3), dtype=np.float32),
        faces=np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int32),
        threshold=np.array(40_333.0),
        downsample=np.array(8),
    )
    context = load_xray_context(path)
    assert context["vertices_zyx"].shape == (4, 3)
    assert context["faces"].shape == (2, 3)
    assert context["downsample"] == 8
