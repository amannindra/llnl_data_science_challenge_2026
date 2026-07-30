"""Build small, deterministic 3D strut scenes with independent ground truth.

The arrays use the same convention as the production reader: ``volume[z, y,
x]``.  Endpoints and STL surface samples use ``(x, y, z)``.  Each case states
both the physical truth and the response expected from a conservative
comparator.  Those differ for deliberately unobservable or unstable scenes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class VisualCase:
    """One immutable synthetic comparison and its independent expectations."""

    case_id: str
    description: str
    volume_zyx: np.ndarray
    endpoint0_xyz: tuple[float, float, float]
    endpoint1_xyz: tuple[float, float, float]
    surface_xyz: np.ndarray
    thresholds: tuple[float, ...]
    physical_has_error: bool
    expected_has_error: bool | None
    expected_radius_voxels: float = 2.0
    distance_tolerance_voxels: float = 2.0
    reason_for_expected_output: str = ""


SHAPE_ZYX = (48, 48, 48)
AXIAL_START = (7.0, 24.0, 24.0)
AXIAL_END = (40.0, 24.0, 24.0)
OBLIQUE_START = (8.0, 9.0, 10.0)
OBLIQUE_END = (38.0, 36.0, 35.0)
DEFAULT_THRESHOLDS = (90.0, 100.0, 110.0)


def _segment_geometry(
    shape_zyx: tuple[int, int, int],
    start_xyz: tuple[float, float, float],
    end_xyz: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Return unclipped axial fraction and distance to a finite segment."""

    z, y, x = np.indices(shape_zyx, dtype=np.float64)
    xyz = np.stack((x, y, z), axis=-1)
    start = np.asarray(start_xyz, dtype=np.float64)
    vector = np.asarray(end_xyz, dtype=np.float64) - start
    squared_length = float(vector @ vector)
    if squared_length == 0.0:
        raise ValueError("synthetic endpoints must be distinct")
    raw_fraction = np.einsum("...i,i->...", xyz - start, vector) / squared_length
    clipped_fraction = np.clip(raw_fraction, 0.0, 1.0)
    closest = start + clipped_fraction[..., None] * vector
    distance = np.linalg.norm(xyz - closest, axis=-1)
    return raw_fraction, distance


def _cylinder(
    *,
    start_xyz: tuple[float, float, float] = AXIAL_START,
    end_xyz: tuple[float, float, float] = AXIAL_END,
    radius: float = 2.0,
    value: float = 200.0,
    background: float = 0.0,
    removed_fraction_ranges: Iterable[tuple[float, float]] = (),
    shape_zyx: tuple[int, int, int] = SHAPE_ZYX,
) -> np.ndarray:
    """Render a finite bright cylinder directly on the native integer grid."""

    fraction, distance = _segment_geometry(shape_zyx, start_xyz, end_xyz)
    material = (fraction >= 0.0) & (fraction <= 1.0) & (distance <= radius)
    for lower, upper in removed_fraction_ranges:
        material &= ~((fraction >= lower) & (fraction <= upper))
    volume = np.full(shape_zyx, background, dtype=np.float32)
    volume[material] = value
    return volume


def _surface_points(
    start_xyz: tuple[float, float, float] = AXIAL_START,
    end_xyz: tuple[float, float, float] = AXIAL_END,
    *,
    radius: float = 2.0,
    axial_step: float = 0.5,
    radial_samples: int = 20,
) -> np.ndarray:
    """Sample the ideal STL cylinder surface without changing CT resolution."""

    start = np.asarray(start_xyz, dtype=np.float64)
    end = np.asarray(end_xyz, dtype=np.float64)
    vector = end - start
    length = float(np.linalg.norm(vector))
    unit = vector / length
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(reference @ unit)) > 0.80:
        reference = np.array([0.0, 1.0, 0.0])
    radial0 = np.cross(unit, reference)
    radial0 /= np.linalg.norm(radial0)
    radial1 = np.cross(unit, radial0)
    fractions = np.linspace(0.0, 1.0, int(np.ceil(length / axial_step)) + 1)
    angles = np.linspace(0.0, 2.0 * np.pi, radial_samples, endpoint=False)
    centers = start + fractions[:, None] * vector
    ring = radius * (
        np.cos(angles)[:, None] * radial0
        + np.sin(angles)[:, None] * radial1
    )
    return (centers[:, None, :] + ring[None, :, :]).reshape(-1, 3)


def _with_speckles(volume: np.ndarray, *, count: int, seed: int = 20260728) -> np.ndarray:
    result = volume.copy()
    generator = np.random.default_rng(seed)
    indices = generator.choice(result.size, size=count, replace=False)
    result.reshape(-1)[indices] = 200.0
    return result


def _with_endpoint_blobs(
    volume: np.ndarray,
    start_xyz: tuple[float, float, float] = AXIAL_START,
    end_xyz: tuple[float, float, float] = AXIAL_END,
    *,
    radius: float = 4.0,
) -> np.ndarray:
    z, y, x = np.indices(volume.shape, dtype=np.float64)
    xyz = np.stack((x, y, z), axis=-1)
    result = volume.copy()
    for endpoint in (start_xyz, end_xyz):
        result[np.linalg.norm(xyz - np.asarray(endpoint), axis=-1) <= radius] = 200.0
    return result


def _axial_gradient(volume: np.ndarray, start_value: float, end_value: float) -> np.ndarray:
    result = volume.copy()
    material = result > 0
    x = np.indices(result.shape, dtype=np.float32)[2]
    fraction = np.clip((x - AXIAL_START[0]) / (AXIAL_END[0] - AXIAL_START[0]), 0.0, 1.0)
    values = start_value + fraction * (end_value - start_value)
    result[material] = values[material]
    return result


def _segment_gradient(
    volume: np.ndarray,
    start_xyz: tuple[float, float, float],
    end_xyz: tuple[float, float, float],
    start_value: float,
    end_value: float,
) -> np.ndarray:
    """Apply an axial intensity gradient along an arbitrary XYZ segment."""

    result = volume.copy()
    fraction, _ = _segment_geometry(volume.shape, start_xyz, end_xyz)
    material = result > 0
    bounded = np.clip(fraction, 0.0, 1.0)
    values = start_value + bounded * (end_value - start_value)
    result[material] = values[material]
    return result


def _disconnected_faint_per_bin_support() -> np.ndarray:
    """Place sufficient faint voxels per slice without a 26-connected path."""

    result = np.zeros(SHAPE_ZYX, dtype=np.float32)
    for x in range(int(AXIAL_START[0]), int(AXIAL_END[0]) + 1):
        # Alternating six voxels transversely makes adjacent axial groups
        # disconnected even under the comparator's 26-neighbour definition.
        y = 21 if x % 2 == 0 else 27
        result[23:26, y, x] = 25.0
    return result


def _gap_with_faint_connected_halo() -> np.ndarray:
    """Combine a true bright-material gap with a faint continuous CT bridge."""

    gapped = _cylinder(removed_fraction_ranges=((0.40, 0.61),))
    faint_halo = _cylinder(radius=1.0, value=30.0)
    return np.maximum(gapped, faint_halo)


def _near_threshold_background_noise() -> np.ndarray:
    """Return deterministic background texture entirely below all thresholds."""

    z, y, x = np.indices(SHAPE_ZYX, dtype=np.float32)
    texture = (
        0.035 * np.sin(2.0 * np.pi * x / 17.0)
        + 0.020 * np.sin(2.0 * np.pi * y / 19.0)
        + 0.010 * np.sin(2.0 * np.pi * z / 23.0)
    )
    return np.asarray(99.40 + texture, dtype=np.float32)


def _bright_annulus_without_target() -> np.ndarray:
    """Put bright nearby material in the guarded annulus, never in the core."""

    fraction, distance = _segment_geometry(SHAPE_ZYX, AXIAL_START, AXIAL_END)
    nearby = (
        (fraction >= 0.0)
        & (fraction <= 1.0)
        & (distance >= 4.5)
        & (distance <= 6.0)
    )
    result = np.zeros(SHAPE_ZYX, dtype=np.float32)
    result[nearby] = 200.0
    return result


def _case(
    case_id: str,
    description: str,
    volume: np.ndarray,
    *,
    start: tuple[float, float, float] = AXIAL_START,
    end: tuple[float, float, float] = AXIAL_END,
    surface_start: tuple[float, float, float] | None = None,
    surface_end: tuple[float, float, float] | None = None,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    physical_has_error: bool,
    expected_has_error: bool | None,
    expected_radius_voxels: float = 2.0,
    distance_tolerance_voxels: float = 2.0,
    reason: str,
) -> VisualCase:
    return VisualCase(
        case_id=case_id,
        description=description,
        volume_zyx=volume,
        endpoint0_xyz=start,
        endpoint1_xyz=end,
        surface_xyz=_surface_points(
            surface_start or start,
            surface_end or end,
            radius=expected_radius_voxels,
        ),
        thresholds=thresholds,
        physical_has_error=physical_has_error,
        expected_has_error=expected_has_error,
        expected_radius_voxels=expected_radius_voxels,
        distance_tolerance_voxels=distance_tolerance_voxels,
        reason_for_expected_output=reason,
    )


def build_visual_cases() -> tuple[VisualCase, ...]:
    """Return fixed cases covering geometry, noise, intensity, and FOV."""

    pinhole = _cylinder()
    pinhole[24, 24, 24] = 0.0
    small_shift_start = (7.0, 25.0, 24.0)
    small_shift_end = (40.0, 25.0, 24.0)
    large_shift_start = (7.0, 31.0, 24.0)
    large_shift_end = (40.0, 31.0, 24.0)
    neighbor_start = (7.0, 32.0, 24.0)
    neighbor_end = (40.0, 32.0, 24.0)
    close_neighbor_start = (7.0, 29.0, 24.0)
    close_neighbor_end = (40.0, 29.0, 24.0)
    truncated_start = (-9.0, 24.0, 24.0)
    truncated_end = (12.0, 24.0, 24.0)

    return (
        _case("01_intact_axial", "Intact axis-aligned strut.", _cylinder(),
              physical_has_error=False, expected_has_error=False,
              reason="Continuous material should be accepted."),
        _case("02_intact_oblique", "Intact XYZ-oblique strut exercises coordinate ordering.",
              _cylinder(start_xyz=OBLIQUE_START, end_xyz=OBLIQUE_END),
              start=OBLIQUE_START, end=OBLIQUE_END,
              physical_has_error=False, expected_has_error=False,
              reason="The comparator must sample the correct ZYX CT voxels."),
        _case("03_fully_missing", "The STL expects a strut, but the CT corridor is empty.",
              np.zeros(SHAPE_ZYX, dtype=np.float32),
              physical_has_error=True, expected_has_error=True,
              reason="No realized axial support is a confirmed mismatch."),
        _case("04_midspan_gap", "A wide transverse gap breaks the middle of the strut.",
              _cylinder(removed_fraction_ranges=((0.40, 0.61),)),
              physical_has_error=True, expected_has_error=True,
              reason="A gap of at least three axial bins must be detected."),
        _case("05_endpoint_break", "The first quarter of the strut body is absent.",
              _cylinder(removed_fraction_ranges=((0.0, 0.27),)),
              physical_has_error=True, expected_has_error=True,
              reason="Endpoint exclusion must not hide a substantial break."),
        _case("06_single_pinhole", "One dark voxel is segmentation noise, not a broken strut.",
              pinhole, physical_has_error=False, expected_has_error=False,
              reason="Sub-resolution pinholes must not become confirmed defects."),
        _case("07_small_lateral_shift", "Observed material is shifted by one voxel.",
              _cylinder(start_xyz=small_shift_start, end_xyz=small_shift_end),
              physical_has_error=False, expected_has_error=False,
              reason="A one-voxel registration residual lies inside tolerance."),
        _case("08_large_lateral_shift", "Observed material is seven voxels from the design.",
              _cylinder(start_xyz=large_shift_start, end_xyz=large_shift_end),
              physical_has_error=True, expected_has_error=True,
              reason="A displacement well outside tolerance is a geometric mismatch."),
        _case("09_thin_continuous", "A radius-one strut remains continuous.",
              _cylinder(radius=1.0), physical_has_error=False, expected_has_error=False,
              reason="Version one detects absent/broken struts, not thickness defects."),
        _case("10_thick_continuous", "A radius-four strut remains continuous.",
              _cylinder(radius=4.0), physical_has_error=False, expected_has_error=False,
              reason="Extra thickness must not be mislabeled as missing or broken."),
        _case("11_speckles_only", "Random bright voxels occur without a target strut.",
              _with_speckles(np.zeros(SHAPE_ZYX, dtype=np.float32), count=500),
              physical_has_error=True, expected_has_error=True,
              reason="Sparse noise cannot create sustained axial support."),
        _case("12_parallel_neighbor_only", "Only a parallel neighboring strut is present.",
              _cylinder(start_xyz=neighbor_start, end_xyz=neighbor_end),
              physical_has_error=True, expected_has_error=True,
              reason="Material outside the target corridor cannot fill the target edge."),
        _case("13_scaled_intensity", "Intensity and all thresholds are scaled by six.",
              _cylinder(value=1200.0), thresholds=(540.0, 600.0, 660.0),
              physical_has_error=False, expected_has_error=False,
              reason="A consistent intensity-unit change must preserve the decision."),
        _case("14_axial_intensity_gradient", "An intact strut has a smooth 180-to-260 gradient.",
              _axial_gradient(_cylinder(), 180.0, 260.0),
              physical_has_error=False, expected_has_error=False,
              reason="All material remains above the threshold perturbations."),
        _case("15_threshold_disagreement", "Material equals the middle threshold exactly.",
              _cylinder(value=100.0),
              physical_has_error=False, expected_has_error=None,
              reason="Opposing threshold decisions must become review-required, not a false binary."),
        _case("16_truncated_field_of_view", "One endpoint lies outside the CT field of view.",
              _cylinder(start_xyz=truncated_start, end_xyz=truncated_end),
              start=truncated_start, end=truncated_end,
              physical_has_error=False, expected_has_error=None,
              reason="Insufficient CT coverage is unobservable rather than missing."),
        _case("17_oblique_midspan_gap", "An oblique strut has a wide central break.",
              _cylinder(start_xyz=OBLIQUE_START, end_xyz=OBLIQUE_END,
                        removed_fraction_ranges=((0.43, 0.59),)),
              start=OBLIQUE_START, end=OBLIQUE_END,
              physical_has_error=True, expected_has_error=True,
              reason="Gap detection must remain valid away from cardinal axes."),
        _case("18_endpoint_blobs_only", "Bright junction-like blobs exist but the body is absent.",
              _with_endpoint_blobs(np.zeros(SHAPE_ZYX, dtype=np.float32)),
              physical_has_error=True, expected_has_error=True,
              reason="Endpoints alone cannot impersonate a realized strut body."),
        _case("19_gradient_crosses_thresholds",
              "An intact member smoothly crosses below and above the threshold ensemble.",
              _axial_gradient(_cylinder(), 80.0, 120.0),
              physical_has_error=False, expected_has_error=None,
              reason=(
                  "A smooth acquisition-intensity gradient may require review, but must not "
                  "be asserted as a confident geometric break."
              )),
        _case("20_close_parallel_neighbor_only",
              "Only a close parallel neighbor touches the target tolerance corridor.",
              _cylinder(start_xyz=close_neighbor_start, end_xyz=close_neighbor_end),
              physical_has_error=True, expected_has_error=True,
              reason=(
                  "Unowned material from a nearby edge must not supply continuous support "
                  "to a missing target edge."
              )),
        _case("21_thick_gradient_crosses_thresholds",
              "A radius-four intact member smoothly crosses the threshold ensemble.",
              _axial_gradient(_cylinder(radius=4.0), 80.0, 120.0),
              physical_has_error=False, expected_has_error=None,
              reason=(
                  "A guarded annular background must make the gradient response independent "
                  "of member thickness; uncertain intensity remains review-required."
              )),
        _case("22_disconnected_faint_per_bin_support",
              "Every axial bin has faint samples, but they form disconnected components.",
              _disconnected_faint_per_bin_support(),
              physical_has_error=True, expected_has_error=True,
              reason=(
                  "Count-only contrast is insufficient; no 26-connected target path exists, "
                  "so the missing member must remain an error candidate."
              )),
        _case("23_gap_with_faint_connected_halo",
              "A bright-material gap contains a faint noise-significant connected bridge.",
              _gap_with_faint_connected_halo(),
              physical_has_error=True, expected_has_error=None,
              reason=(
                  "A connected faint bridge can be partial-volume blur or residual material; "
                  "the scan is fundamentally ambiguous and requires review."
              )),
        _case("24_background_near_threshold_noise",
              "The target is absent in textured background just below all thresholds.",
              _near_threshold_background_noise(),
              thresholds=(99.5, 100.0, 100.5),
              physical_has_error=True, expected_has_error=True,
              reason=(
                  "A robust noise/SNR floor must prevent near-threshold texture from becoming "
                  "subthreshold continuity."
              )),
        _case("25_bright_annulus_contamination",
              "Nearby bright material contaminates the guarded annulus but not the target core.",
              _bright_annulus_without_target(),
              physical_has_error=True, expected_has_error=True,
              reason=(
                  "A contaminated background estimate cannot authorize an error-to-review "
                  "downgrade for a missing target."
              )),
        _case("26_oblique_gradient_crosses_thresholds",
              "An intact oblique member smoothly crosses the threshold ensemble.",
              _segment_gradient(
                  _cylinder(start_xyz=OBLIQUE_START, end_xyz=OBLIQUE_END),
                  OBLIQUE_START,
                  OBLIQUE_END,
                  80.0,
                  120.0,
              ),
              start=OBLIQUE_START, end=OBLIQUE_END,
              physical_has_error=False, expected_has_error=None,
              reason=(
                  "Annular hysteresis and shift stability must work for non-cardinal geometry; "
                  "an intensity-confounded intact member remains review-required."
              )),
    )


def public_case_spec(case: VisualCase) -> dict[str, Any]:
    """Return the JSON-safe input contract without embedding the full array."""

    nonzero = case.volume_zyx[case.volume_zyx != 0]
    return {
        "case_id": case.case_id,
        "description": case.description,
        "shape_zyx": list(case.volume_zyx.shape),
        "dtype": str(case.volume_zyx.dtype),
        "endpoint0_xyz": list(case.endpoint0_xyz),
        "endpoint1_xyz": list(case.endpoint1_xyz),
        "thresholds": list(case.thresholds),
        "physical_has_error": case.physical_has_error,
        "expected_has_error": case.expected_has_error,
        "expected_radius_voxels": case.expected_radius_voxels,
        "distance_tolerance_voxels": case.distance_tolerance_voxels,
        "reason_for_expected_output": case.reason_for_expected_output,
        "foreground_voxel_count": int(np.count_nonzero(case.volume_zyx)),
        "foreground_intensity_min": None if nonzero.size == 0 else float(nonzero.min()),
        "foreground_intensity_max": None if nonzero.size == 0 else float(nonzero.max()),
    }


__all__ = ["VisualCase", "build_visual_cases", "public_case_spec"]
