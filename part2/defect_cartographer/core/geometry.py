"""Registered graph coordinates, stratified sampling, and vector conversion."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable

import numpy as np
import pandas as pd


def junction_positions(graph: dict[str, Any]) -> dict[int, np.ndarray]:
    """Return registered junction positions in JSON `(x, y, z)` order."""

    return {
        int(junction["id"]): np.asarray(junction["position"], dtype=np.float64)
        for junction in graph["junctions"]
    }


def registered_junctions(
    graph: dict[str, Any],
    permutation: tuple[int, int, int] = (2, 1, 0),
    residual_transform: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return sorted junction IDs and positions in registered CT `(z,y,x)`."""

    positions = junction_positions(graph)
    ids = np.asarray(sorted(positions), dtype=np.int64)
    points = np.asarray([positions[int(junction_id)] for junction_id in ids])
    points = points[:, permutation]
    if residual_transform is not None:
        points = apply_homogeneous(points, residual_transform)
    return ids, points


def endpoints_for_struts(
    graph: dict[str, Any],
    strut_ids: Iterable[int] | None = None,
    permutation: tuple[int, int, int] = (2, 1, 0),
    residual_transform: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return IDs and endpoints in registered CT array coordinate order."""

    positions = junction_positions(graph)
    strut_by_id = {int(strut["id"]): strut for strut in graph["struts"]}
    ids = (
        np.asarray(sorted(strut_by_id), dtype=np.int64)
        if strut_ids is None
        else np.asarray(list(strut_ids), dtype=np.int64)
    )
    missing = [int(strut_id) for strut_id in ids if int(strut_id) not in strut_by_id]
    if missing:
        raise KeyError(f"Unknown strut IDs: {missing[:10]}")

    starts_xyz = np.asarray(
        [positions[int(strut_by_id[int(i)]["junction0"])] for i in ids],
        dtype=np.float64,
    )
    ends_xyz = np.asarray(
        [positions[int(strut_by_id[int(i)]["junction1"])] for i in ids],
        dtype=np.float64,
    )
    starts = starts_xyz[:, permutation]
    ends = ends_xyz[:, permutation]
    if residual_transform is not None:
        starts = apply_homogeneous(starts, residual_transform)
        ends = apply_homogeneous(ends, residual_transform)
    return ids, starts, ends


def apply_homogeneous(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Apply a 4x4 homogeneous transform to an N-by-3 point array."""

    points = np.asarray(points, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (4, 4):
        raise ValueError(f"Residual transform must be 4x4, found {matrix.shape}")
    homogeneous = np.column_stack((points, np.ones(len(points))))
    transformed = homogeneous @ matrix.T
    if np.any(np.isclose(transformed[:, 3], 0)):
        raise ValueError("Residual transform produced a zero homogeneous coordinate")
    return transformed[:, :3] / transformed[:, 3, None]


def line_points(
    start: np.ndarray,
    end: np.ndarray,
    *,
    spacing_vox: float = 0.5,
    trim_fraction: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a strut centerline after trimming node-adjacent endpoints."""

    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    length = float(np.linalg.norm(end - start))
    count = max(9, int(np.ceil(length / spacing_vox)) + 1)
    parameters = np.linspace(trim_fraction, 1.0 - trim_fraction, count)
    points = start[None, :] * (1.0 - parameters[:, None]) + end[None, :] * parameters[:, None]
    return points, parameters


def _orientation_bin(vector: np.ndarray) -> str:
    """Create a sign-insensitive orientation label for stratification."""

    vector = np.asarray(vector, dtype=np.float64)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return "degenerate"
    unit = vector / norm
    first_nonzero = np.flatnonzero(np.abs(unit) > 1e-6)
    if first_nonzero.size and unit[first_nonzero[0]] < 0:
        unit = -unit
    quantized = np.rint(unit * 2).astype(int)
    return ":".join(str(int(item)) for item in quantized)


def build_strut_table(
    graph: dict[str, Any],
    permutation: tuple[int, int, int] = (2, 1, 0),
    residual_transform: np.ndarray | None = None,
) -> pd.DataFrame:
    """Build spatial descriptors for every expected strut."""

    ids, starts, ends = endpoints_for_struts(
        graph,
        permutation=permutation,
        residual_transform=residual_transform,
    )
    midpoints = (starts + ends) / 2.0
    all_points = np.vstack((starts, ends))
    lower = all_points.min(axis=0)
    upper = all_points.max(axis=0)
    extent = np.maximum(upper - lower, 1e-12)
    normalized = (midpoints - lower) / extent
    boundary_distance = np.minimum(normalized, 1.0 - normalized).min(axis=1)
    height_index = np.minimum((normalized[:, 0] * 3).astype(int), 2)
    height_names = np.asarray(["low", "middle", "high"])

    table = pd.DataFrame(
        {
            "strut_id": ids,
            "start_z": starts[:, 0],
            "start_y": starts[:, 1],
            "start_x": starts[:, 2],
            "end_z": ends[:, 0],
            "end_y": ends[:, 1],
            "end_x": ends[:, 2],
            "mid_z": midpoints[:, 0],
            "mid_y": midpoints[:, 1],
            "mid_x": midpoints[:, 2],
            "length_vox": np.linalg.norm(ends - starts, axis=1),
            "region": np.where(boundary_distance < 0.18, "exterior", "interior"),
            "height_band": height_names[height_index],
            "orientation": [
                _orientation_bin(end - start) for start, end in zip(starts, ends)
            ],
        }
    )
    return table


def stratified_sample(
    table: pd.DataFrame,
    sample_size: int,
    seed: int,
) -> pd.DataFrame:
    """Round-robin sample joint spatial/orientation strata reproducibly."""

    if sample_size <= 0 or sample_size > len(table):
        raise ValueError(f"sample_size must be in 1..{len(table)}")
    rng = np.random.default_rng(seed)
    grouped: dict[tuple[str, str, str], deque[int]] = defaultdict(deque)
    shuffled = table.sample(frac=1.0, random_state=seed)
    for index, row in shuffled.iterrows():
        key = (str(row["region"]), str(row["height_band"]), str(row["orientation"]))
        grouped[key].append(int(index))

    keys = list(grouped)
    rng.shuffle(keys)
    chosen: list[int] = []
    while len(chosen) < sample_size:
        progressed = False
        for key in keys:
            if grouped[key] and len(chosen) < sample_size:
                chosen.append(grouped[key].popleft())
                progressed = True
        if not progressed:
            raise RuntimeError("Could not obtain the requested stratified sample")

    result = table.loc[chosen].reset_index(drop=True)
    result.insert(0, "sample_order", np.arange(len(result), dtype=int))
    return result
