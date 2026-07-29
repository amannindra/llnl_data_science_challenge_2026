from __future__ import annotations

import pytest

from defect_cartographer.core.slice_evidence import get_strut_slice_evidence


def test_broken_strut_slice_evidence_is_bounded_and_layered() -> None:
    evidence = get_strut_slice_evidence(12_958)

    assert evidence["schemaVersion"] == 3
    assert evidence["strutId"] == 12_958
    assert evidence["candidateLabel"] == "broken"
    assert evidence["focusMethod"] == "center of largest unsupported centerline run"
    assert evidence["preferredView"] == "longitudinal"
    assert evidence["slabThicknessVox"] == 9
    assert evidence["rawCtVolumeEmbedded"] is False
    assert len(evidence["views"]) == 4
    assert {view["axis"] for view in evidence["views"]} == {
        "longitudinal",
        "z",
        "y",
        "x",
    }
    for view in evidence["views"]:
        assert len(view["frames"]) == 5
        assert [frame["offsetVox"] for frame in view["frames"]] == [-4, -2, 0, 2, 4]
        for frame in view["frames"]:
            assert set(frame["modes"]) == {"exact", "slab"}
            for mode in frame["modes"].values():
                assert mode["rawDataUrl"].startswith("data:image/png;base64,")
                assert mode["segmentationBoundaryDataUrl"].startswith(
                    "data:image/png;base64,"
                )
                assert mode["observedCenterlineDataUrl"].startswith(
                    "data:image/png;base64,"
                )
            assert (
                frame["slabBoundsGlobal"][1] - frame["slabBoundsGlobal"][0]
                <= 9
            )
        assert len(view["expectedLine"]) == 4
        assert len(view["focusPoint"]) == 2
    aligned = next(
        view for view in evidence["views"] if view["axis"] == "longitudinal"
    )
    assert aligned["title"] == "Along strut"
    assert aligned["frames"][2]["indexLabel"] == "center plane"
    assert aligned["expectedLine"][1] == aligned["expectedLine"][3] == 0.5


def test_missing_strut_uses_midpoint_and_fixed_crop() -> None:
    evidence = get_strut_slice_evidence(16_082)

    assert evidence["candidateLabel"] == "missing"
    assert evidence["focusMethod"] == "expected target-strut midpoint"
    lower = evidence["cropBoundsZyx"]["lowerInclusive"]
    upper = evidence["cropBoundsZyx"]["upperExclusive"]
    assert [high - low for low, high in zip(lower, upper)] == [96, 96, 96]


def test_slice_evidence_supports_wider_browser_context() -> None:
    evidence = get_strut_slice_evidence(9_000, crop_size=128)

    lower = evidence["cropBoundsZyx"]["lowerInclusive"]
    upper = evidence["cropBoundsZyx"]["upperExclusive"]
    assert [high - low for low, high in zip(lower, upper)] == [128, 128, 128]
    assert evidence["candidateLabel"] == "intact"
    assert evidence["rawCtVolumeEmbedded"] is False


def test_slice_evidence_rejects_unanalyzed_strut() -> None:
    with pytest.raises(ValueError, match="saved 60-strut analysis"):
        get_strut_slice_evidence(0)
