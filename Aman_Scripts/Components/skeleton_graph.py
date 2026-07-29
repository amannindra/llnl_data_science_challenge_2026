"""Convert a binary voxel skeleton into a lattice graph of junctions and struts.

``skimage.morphology.skeletonize`` reduces a segmented strut lattice to a
one-voxel-wide centerline, but that centerline is still just a voxel mask: it
carries no notion of which voxels form a junction and which form the strut
between two junctions.  This module recovers that structure.

The extraction is deliberately sparse.  A full CT volume holds hundreds of
millions of voxels while its skeleton holds around a million, so every step
after the initial ``np.argwhere`` works on the ``(N, 3)`` coordinate list rather
than the dense array.  Memory therefore scales with the skeleton, not the scan.

Method
------
1.  Count each skeleton voxel's 26-connected neighbours to obtain its *degree*.
2.  Classify: degree 1 is a free end, degree 2 is interior to a strut, and
    degree 3 or more is a junction.
3.  Cluster spatially adjacent non-degree-2 voxels into **nodes**.  A real
    junction is a small blob of several voxels, not a single one, so the node
    position is the centroid of its cluster.
4.  Walk the degree-2 runs between nodes to recover **struts**, accumulating the
    true polyline arc length rather than the straight-line node separation.

Coordinates follow the project convention: input arrays are indexed ``[z, y, x]``
and every emitted ``position`` is ``(x, y, z)``.  Lengths are in voxels.

Importing this module performs no filesystem access.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

from .coordinates import zyx_to_xyz

__all__ = [
    "SkeletonGraph",
    "SkeletonGraphError",
    "SkeletonNode",
    "SkeletonStrut",
    "build_lattice_payload",
    "skeleton_to_lattice",
]

SCHEMA_VERSION = "ct-skeleton-lattice.v1"

# The 26 neighbours of a voxel, excluding the voxel itself.
_OFFSETS: tuple[tuple[int, int, int], ...] = tuple(
    (dz, dy, dx)
    for dz in (-1, 0, 1)
    for dy in (-1, 0, 1)
    for dx in (-1, 0, 1)
    if (dz, dy, dx) != (0, 0, 0)
)

# Euclidean step length for a move of (|dz|, |dy|, |dx|): 1, sqrt(2) or sqrt(3).
_STEP_LENGTH: tuple[float, ...] = tuple(
    math.sqrt(abs(dz) + abs(dy) + abs(dx)) for dz, dy, dx in _OFFSETS
)


class SkeletonGraphError(ValueError):
    """Raised when a skeleton array cannot be converted into a lattice graph."""


@dataclass(frozen=True)
class SkeletonNode:
    """One junction or free end recovered from the skeleton.

    ``position`` is the XYZ centroid of the voxel cluster, so it is fractional
    whenever the cluster holds more than one voxel.
    """

    id: int
    position: tuple[float, float, float]
    voxel_count: int
    max_degree: int
    kind: str  # "junction" | "endpoint" | "isolated"


@dataclass(frozen=True)
class SkeletonStrut:
    """One traced centerline path between two distinct nodes."""

    id: int
    junction0: int
    junction1: int
    length_voxels: float
    path_voxel_count: int


@dataclass(frozen=True)
class SkeletonGraph:
    """The recovered lattice plus counters describing what was discarded."""

    nodes: tuple[SkeletonNode, ...]
    struts: tuple[SkeletonStrut, ...]
    shape_zyx: tuple[int, int, int]
    statistics: Mapping[str, Any]


def _validate(skeleton: Any) -> NDArray[np.bool_]:
    """Coerce ``skeleton`` to a 3D boolean array, rejecting unusable input."""

    array = np.asarray(skeleton)
    if array.ndim != 3:
        raise SkeletonGraphError(
            f"skeleton must be a 3D [z, y, x] array; got ndim={array.ndim}, shape={array.shape}"
        )
    if array.dtype == np.bool_:
        return array
    if np.issubdtype(array.dtype, np.complexfloating):
        raise SkeletonGraphError(f"skeleton dtype must be real; got {array.dtype}")
    if not (np.issubdtype(array.dtype, np.number) or array.dtype == np.bool_):
        raise SkeletonGraphError(f"skeleton dtype must be numeric or boolean; got {array.dtype}")
    foreground = array != 0
    if np.issubdtype(array.dtype, np.inexact):
        # NaN != 0 is True, so drop non-finite voxels explicitly.
        foreground &= np.isfinite(array)
    return foreground


def _adjacency(
    coords: NDArray[np.int64], shape: tuple[int, int, int]
) -> tuple[NDArray[np.int64], NDArray[np.int32], NDArray[np.float64]]:
    """Build a CSR 26-neighbour adjacency over the skeleton voxel list.

    ``coords`` must be ascending in ``(z, y, x)`` order, which is exactly what
    ``np.argwhere`` returns, because membership tests use ``searchsorted`` on the
    packed linear index.
    """

    depth, height, width = shape
    count = len(coords)
    keys = (coords[:, 0] * height + coords[:, 1]) * width + coords[:, 2]

    row_parts: list[NDArray[np.int64]] = []
    column_parts: list[NDArray[np.int64]] = []
    length_parts: list[NDArray[np.float64]] = []

    for offset_index, (dz, dy, dx) in enumerate(_OFFSETS):
        neighbour_z = coords[:, 0] + dz
        neighbour_y = coords[:, 1] + dy
        neighbour_x = coords[:, 2] + dx
        inside = (
            (neighbour_z >= 0)
            & (neighbour_z < depth)
            & (neighbour_y >= 0)
            & (neighbour_y < height)
            & (neighbour_x >= 0)
            & (neighbour_x < width)
        )
        if not inside.any():
            continue
        source = np.flatnonzero(inside)
        candidate = (
            (neighbour_z[inside] * height + neighbour_y[inside]) * width + neighbour_x[inside]
        )
        position = np.searchsorted(keys, candidate)
        np.clip(position, 0, count - 1, out=position)
        present = keys[position] == candidate
        if not present.any():
            continue
        row_parts.append(source[present])
        column_parts.append(position[present])
        length_parts.append(
            np.full(int(present.sum()), _STEP_LENGTH[offset_index], dtype=np.float64)
        )

    if not row_parts:
        indptr = np.zeros(count + 1, dtype=np.int64)
        return indptr, np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float64)

    rows = np.concatenate(row_parts)
    columns = np.concatenate(column_parts)
    lengths = np.concatenate(length_parts)

    order = np.argsort(rows, kind="stable")
    rows = rows[order]
    columns = columns[order].astype(np.int32, copy=False)
    lengths = lengths[order]
    indptr = np.searchsorted(rows, np.arange(count + 1)).astype(np.int64, copy=False)
    return indptr, columns, lengths


def _cluster_nodes(
    node_voxels: NDArray[np.int64],
    indptr: NDArray[np.int64],
    columns: NDArray[np.int32],
    is_node: NDArray[np.bool_],
) -> tuple[NDArray[np.int32], int]:
    """Group adjacent node voxels into clusters via breadth-first search."""

    node_of = np.full(len(is_node), -1, dtype=np.int32)
    cluster_count = 0
    queue: deque[int] = deque()
    for seed in node_voxels:
        seed_index = int(seed)
        if node_of[seed_index] != -1:
            continue
        node_of[seed_index] = cluster_count
        queue.append(seed_index)
        while queue:
            current = queue.popleft()
            for neighbour in columns[indptr[current] : indptr[current + 1]]:
                neighbour_index = int(neighbour)
                if is_node[neighbour_index] and node_of[neighbour_index] == -1:
                    node_of[neighbour_index] = cluster_count
                    queue.append(neighbour_index)
        cluster_count += 1
    return node_of, cluster_count


def skeleton_to_lattice(
    skeleton: Any,
    *,
    merge_radius_voxels: float = 0.0,
    min_strut_length_voxels: float = 0.0,
    dissolve_degree2_nodes: bool = False,
    max_skeleton_voxels: int | None = None,
) -> SkeletonGraph:
    """Recover junctions and struts from a 3D binary skeleton.

    Args:
        skeleton: 3D ``[z, y, x]`` array; nonzero finite voxels are the skeleton.
        merge_radius_voxels: Contract struts shorter than this into a single
            node. A physical junction spans several voxels and splits into
            sub-clusters, so leaving this at 0 typically over-counts junctions.
            Choose a value well above the junction blob diameter (roughly twice
            the strut radius) and well below the real strut length.
        min_strut_length_voxels: Struts shorter than this arc length are dropped,
            applied after merging.
        dissolve_degree2_nodes: Remove nodes carrying exactly two struts and
            splice those struts into one. A sharp bend in the centerline yields
            degree-3 voxels under 26-connectivity (three mutually adjacent
            voxels form a triangle), so bends surface as spurious two-strut
            nodes; this removes them. Leave it off when a two-strut node may be
            physically real -- in a lattice with missing struts, a junction that
            lost all but two of its struts is exactly the signal of interest,
            and dissolving it splices two real struts into one phantom.
        max_skeleton_voxels: Optional guard; exceeding it raises rather than
            attempting a run that would not finish.

    Returns:
        A :class:`SkeletonGraph`. Node positions are XYZ in voxel units.

    Raises:
        SkeletonGraphError: The array is not a usable 3D skeleton, or the voxel
            guard was exceeded.
    """

    if not math.isfinite(min_strut_length_voxels) or min_strut_length_voxels < 0:
        raise SkeletonGraphError(
            f"min_strut_length_voxels must be finite and nonnegative; got {min_strut_length_voxels!r}"
        )
    if not math.isfinite(merge_radius_voxels) or merge_radius_voxels < 0:
        raise SkeletonGraphError(
            f"merge_radius_voxels must be finite and nonnegative; got {merge_radius_voxels!r}"
        )

    foreground = _validate(skeleton)
    shape = (int(foreground.shape[0]), int(foreground.shape[1]), int(foreground.shape[2]))

    coords = np.argwhere(foreground).astype(np.int64, copy=False)
    voxel_count = len(coords)
    if max_skeleton_voxels is not None and voxel_count > max_skeleton_voxels:
        raise SkeletonGraphError(
            f"skeleton holds {voxel_count} voxels, exceeding max_skeleton_voxels={max_skeleton_voxels}"
        )
    if voxel_count == 0:
        return SkeletonGraph(
            nodes=(),
            struts=(),
            shape_zyx=shape,
            statistics={
                "skeleton_voxels": 0,
                "node_voxels": 0,
                "path_voxels": 0,
                "endpoint_nodes": 0,
                "junction_nodes": 0,
                "isolated_nodes": 0,
                "nodes_merged": 0,
                "degree2_nodes_dissolved": 0,
                "self_loops_dropped": 0,
                "duplicate_pairs_collapsed": 0,
                "short_struts_dropped": 0,
                "unreached_path_voxels": 0,
            },
        )

    indptr, columns, lengths = _adjacency(coords, shape)
    degree = np.diff(indptr).astype(np.int64, copy=False)

    is_node = degree != 2
    node_voxels = np.flatnonzero(is_node)
    node_of, cluster_count = _cluster_nodes(node_voxels, indptr, columns, is_node)

    # Node geometry: centroid of each cluster, in ZYX, then converted to XYZ.
    sums = np.zeros((cluster_count, 3), dtype=np.float64)
    counts = np.zeros(cluster_count, dtype=np.int64)
    max_degree = np.zeros(cluster_count, dtype=np.int64)
    cluster_ids = node_of[node_voxels]
    np.add.at(sums, cluster_ids, coords[node_voxels].astype(np.float64))
    np.add.at(counts, cluster_ids, 1)
    np.maximum.at(max_degree, cluster_ids, degree[node_voxels])
    # Trace every degree-2 run exactly once. Each interior path voxel belongs to
    # a single strut, so a visited flag prevents rediscovering a path from its
    # far end.
    visited_path = np.zeros(voxel_count, dtype=bool)
    candidates: list[tuple[int, int, float, int]] = []
    direct_pairs: set[tuple[int, int]] = set()
    self_loops = 0

    for voxel in node_voxels:
        start = int(voxel)
        origin = int(node_of[start])
        for slot in range(int(indptr[start]), int(indptr[start + 1])):
            neighbour = int(columns[slot])
            step = float(lengths[slot])

            if is_node[neighbour]:
                # Two node clusters touching directly: a zero-interior strut.
                target = int(node_of[neighbour])
                if target == origin:
                    continue
                pair = (min(origin, target), max(origin, target))
                if pair in direct_pairs:
                    continue
                direct_pairs.add(pair)
                candidates.append((pair[0], pair[1], step, 0))
                continue

            if visited_path[neighbour]:
                continue

            previous, current = start, neighbour
            visited_path[current] = True
            total = step
            interior = 1
            while True:
                following = -1
                following_step = 0.0
                for inner in range(int(indptr[current]), int(indptr[current + 1])):
                    option = int(columns[inner])
                    if option != previous:
                        following = option
                        following_step = float(lengths[inner])
                        break
                if following < 0:
                    break  # dead end; the run terminates without a second node
                total += following_step
                if is_node[following]:
                    current = following
                    break
                visited_path[following] = True
                interior += 1
                previous, current = current, following

            if not is_node[current]:
                continue
            target = int(node_of[current])
            if target == origin:
                self_loops += 1
                continue
            candidates.append((min(origin, target), max(origin, target), total, interior))

    # Collapse parallel paths between the same node pair, keeping the shortest.
    shortest: dict[tuple[int, int], tuple[float, int]] = {}
    duplicates = 0
    for first, second, total, interior in candidates:
        pair = (first, second)
        existing = shortest.get(pair)
        if existing is None:
            shortest[pair] = (total, interior)
        else:
            duplicates += 1
            if total < existing[0]:
                shortest[pair] = (total, interior)

    # A physical junction is a blob several voxels across, but the clustering
    # above merges only *directly adjacent* node voxels. Sub-clusters of a single
    # junction therefore survive as separate nodes joined by a stub far shorter
    # than any real strut. Contract those stubs so one junction becomes one node.
    merged_nodes = 0
    if merge_radius_voxels > 0 and shortest:
        parent = list(range(cluster_count))

        def find(item: int) -> int:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for (first, second), (total, _interior) in shortest.items():
            if total < merge_radius_voxels:
                root_first, root_second = find(first), find(second)
                if root_first != root_second:
                    parent[max(root_first, root_second)] = min(root_first, root_second)
                    merged_nodes += 1

        roots = np.array([find(index) for index in range(cluster_count)], dtype=np.int64)
        _, remapped = np.unique(roots, return_inverse=True)
        remapped = remapped.reshape(-1)
        merged_count = int(remapped.max()) + 1 if cluster_count else 0

        merged_sums = np.zeros((merged_count, 3), dtype=np.float64)
        merged_counts = np.zeros(merged_count, dtype=np.int64)
        merged_degree = np.zeros(merged_count, dtype=np.int64)
        np.add.at(merged_sums, remapped, sums)
        np.add.at(merged_counts, remapped, counts)
        np.maximum.at(merged_degree, remapped, max_degree)
        sums, counts, max_degree = merged_sums, merged_counts, merged_degree
        cluster_count = merged_count

        contracted: dict[tuple[int, int], tuple[float, int]] = {}
        for (first, second), value in shortest.items():
            left, right = int(remapped[first]), int(remapped[second])
            if left == right:
                continue
            pair = (min(left, right), max(left, right))
            existing = contracted.get(pair)
            if existing is None or value[0] < existing[0]:
                contracted[pair] = value
        shortest = contracted

    dissolved_nodes = 0
    if dissolve_degree2_nodes and shortest:
        incident: dict[int, set[tuple[int, int]]] = {}
        for pair in shortest:
            incident.setdefault(pair[0], set()).add(pair)
            incident.setdefault(pair[1], set()).add(pair)

        alive = np.ones(cluster_count, dtype=bool)
        queue = deque(cluster for cluster, pairs in incident.items() if len(pairs) == 2)
        while queue:
            cluster = queue.popleft()
            pairs = incident.get(cluster)
            if pairs is None or len(pairs) != 2 or not alive[cluster]:
                continue
            first, second = tuple(pairs)
            far_first = first[0] if first[1] == cluster else first[1]
            far_second = second[0] if second[1] == cluster else second[1]
            if far_first == far_second:
                # Dissolving would leave a self-loop; keep the node instead.
                continue
            length = shortest[first][0] + shortest[second][0]
            interior = shortest[first][1] + shortest[second][1] + int(counts[cluster])
            for pair in (first, second):
                del shortest[pair]
                incident[pair[0]].discard(pair)
                incident[pair[1]].discard(pair)
            joined = (min(far_first, far_second), max(far_first, far_second))
            existing = shortest.get(joined)
            if existing is None or length < existing[0]:
                shortest[joined] = (length, interior)
            incident.setdefault(joined[0], set()).add(joined)
            incident.setdefault(joined[1], set()).add(joined)
            incident.pop(cluster, None)
            alive[cluster] = False
            dissolved_nodes += 1
            # Neighbour degrees are unchanged by the swap, but a chain of
            # degree-2 nodes only becomes reachable once its head is gone.
            for neighbour in (far_first, far_second):
                if len(incident.get(neighbour, ())) == 2:
                    queue.append(neighbour)

        if dissolved_nodes:
            surviving = int(alive.sum())
            relabel = np.full(cluster_count, -1, dtype=np.int64)
            relabel[alive] = np.arange(surviving, dtype=np.int64)
            sums, counts, max_degree = sums[alive], counts[alive], max_degree[alive]
            cluster_count = surviving
            shortest = {
                (
                    min(int(relabel[pair[0]]), int(relabel[pair[1]])),
                    max(int(relabel[pair[0]]), int(relabel[pair[1]])),
                ): value
                for pair, value in shortest.items()
            }

    centroids_xyz = zyx_to_xyz(sums / counts[:, None])
    nodes: list[SkeletonNode] = []
    for cluster in range(cluster_count):
        highest = int(max_degree[cluster])
        if highest == 0:
            kind = "isolated"
        elif highest == 1:
            kind = "endpoint"
        else:
            kind = "junction"
        x, y, z = centroids_xyz[cluster]
        nodes.append(
            SkeletonNode(
                id=cluster,
                position=(float(x), float(y), float(z)),
                voxel_count=int(counts[cluster]),
                max_degree=highest,
                kind=kind,
            )
        )

    struts: list[SkeletonStrut] = []
    dropped_short = 0
    for pair in sorted(shortest):
        total, interior = shortest[pair]
        if not math.isfinite(total):
            dropped_short += 1
            continue
        if total < min_strut_length_voxels:
            dropped_short += 1
            continue
        struts.append(
            SkeletonStrut(
                id=len(struts),
                junction0=pair[0],
                junction1=pair[1],
                length_voxels=float(total),
                path_voxel_count=int(interior),
            )
        )

    path_voxels = int(voxel_count - len(node_voxels))
    statistics = {
        "skeleton_voxels": int(voxel_count),
        "node_voxels": int(len(node_voxels)),
        "path_voxels": path_voxels,
        "endpoint_nodes": sum(1 for node in nodes if node.kind == "endpoint"),
        "junction_nodes": sum(1 for node in nodes if node.kind == "junction"),
        "isolated_nodes": sum(1 for node in nodes if node.kind == "isolated"),
        "nodes_merged": int(merged_nodes),
        "degree2_nodes_dissolved": int(dissolved_nodes),
        "self_loops_dropped": int(self_loops),
        "duplicate_pairs_collapsed": int(duplicates),
        "short_struts_dropped": int(dropped_short),
        # Closed rings with no junction are never entered by the walk above.
        "unreached_path_voxels": int(path_voxels - int(visited_path.sum())),
    }

    return SkeletonGraph(
        nodes=tuple(nodes), struts=tuple(struts), shape_zyx=shape, statistics=statistics
    )


def build_lattice_payload(
    graph: SkeletonGraph, *, source: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Render a :class:`SkeletonGraph` as a lattice JSON payload.

    The result parses with ``Components.lattice_graph.parse_lattice_graph``.
    Design-only fields carried by the reference lattice JSONs -- ``indices``,
    ``unit_cell_edge_idx``, ``unit_cells`` and ``thickness`` -- are omitted
    rather than fabricated: none of them can be recovered from a CT skeleton.
    Measured geometry is reported as ``length_voxels`` so it is never mistaken
    for the design-unit ``thickness`` of the reference files.
    """

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "coordinate_order": "xyz",
        "units": "voxels",
        "array_order": "zyx",
        "shape_zyx": list(graph.shape_zyx),
        "junctions": [
            {
                "id": node.id,
                "position": [node.position[0], node.position[1], node.position[2]],
                "kind": node.kind,
                "skeleton_voxel_count": node.voxel_count,
                "skeleton_max_degree": node.max_degree,
            }
            for node in graph.nodes
        ],
        "struts": [
            {
                "id": strut.id,
                "junction0": strut.junction0,
                "junction1": strut.junction1,
                "length_voxels": strut.length_voxels,
                "path_voxel_count": strut.path_voxel_count,
            }
            for strut in graph.struts
        ],
        "statistics": dict(graph.statistics),
    }
    if source is not None:
        payload["source"] = dict(source)
    return payload
