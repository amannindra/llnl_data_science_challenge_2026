"""Validated lattice-graph parsing and deterministic physical-node welding.

The project JSON stores one junction record per *unit-cell occurrence*.  Shared
physical junctions therefore have distinct record IDs (and cell-local
``indices``) but coincident XYZ positions.  This module deliberately welds by
``position`` and retains the record IDs that contributed to every welded node
and edge.

All functions are side-effect free except :func:`load_lattice_graph`, whose only
side effect is reading the requested JSON file.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .asset_io import AssetNotMaterializedError, detect_lfs_pointer


class LatticeGraphError(ValueError):
    """Raised when a lattice payload violates the supported schema."""


@dataclass(frozen=True)
class Junction:
    """One source junction record; ``position`` is always XYZ."""

    id: int
    position: tuple[float, float, float]
    indices: tuple[float, float, float] | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class Strut:
    """One source strut record with its original endpoint orientation."""

    id: int
    junction0: int
    junction1: int
    thickness: float | None
    unit_cell_edge_idx: int | None
    metadata: Mapping[str, Any]

    @property
    def endpoints(self) -> tuple[int, int]:
        """Return the endpoint IDs in deterministic undirected order."""

        return normalize_strut_endpoints(self.junction0, self.junction1)


@dataclass(frozen=True)
class UnitCell:
    """A source unit-cell record and its referenced strut IDs."""

    id: int
    strut_ids: tuple[int, ...]
    indices: tuple[int, int, int] | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class LatticeGraph:
    """Canonical, ID-sorted representation of a lattice JSON payload."""

    junctions: tuple[Junction, ...]
    struts: tuple[Strut, ...]
    unit_cells: tuple[UnitCell, ...]
    metadata: Mapping[str, Any]

    def junction_by_id(self) -> dict[int, Junction]:
        return {junction.id: junction for junction in self.junctions}

    def strut_by_id(self) -> dict[int, Strut]:
        return {strut.id: strut for strut in self.struts}


@dataclass(frozen=True)
class WeldedNode:
    """One physical node and the source records welded into it."""

    id: int
    position: tuple[float, float, float]
    source_junction_ids: tuple[int, ...]


@dataclass(frozen=True)
class WeldedStrut:
    """One physical undirected edge with complete source-strut provenance."""

    id: int
    node0: int
    node1: int
    source_strut_ids: tuple[int, ...]
    source_thicknesses: tuple[float | None, ...]

    @property
    def endpoints(self) -> tuple[int, int]:
        return self.node0, self.node1


@dataclass(frozen=True)
class WeldedGraph:
    """A position-welded graph plus mappings back to every source record."""

    nodes: tuple[WeldedNode, ...]
    struts: tuple[WeldedStrut, ...]
    junction_to_node: Mapping[int, int]
    dangling_strut_ids: tuple[int, ...]
    self_loop_strut_ids: tuple[int, ...]
    tolerance: float
    source_graph: LatticeGraph


@dataclass(frozen=True)
class ComponentSummary:
    """Connectivity summary including isolated welded nodes."""

    component_count: int
    component_sizes: tuple[int, ...]
    largest_component_size: int
    largest_component_fraction: float
    isolated_node_ids: tuple[int, ...]


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool):
        raise LatticeGraphError(f"{context} must be an integer, not bool")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LatticeGraphError(f"{context} must be an integer") from exc
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LatticeGraphError(f"{context} must be numeric") from exc
    if not math.isfinite(numeric) or numeric != number:
        raise LatticeGraphError(f"{context} must be a finite integer")
    return number


def _xyz(value: Any, context: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise LatticeGraphError(f"{context} must contain exactly three coordinates")
    try:
        coords = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LatticeGraphError(f"{context} coordinates must be numeric") from exc
    if not all(math.isfinite(item) for item in coords):
        raise LatticeGraphError(f"{context} coordinates must be finite")
    return coords  # type: ignore[return-value]


def _records(payload: Mapping[str, Any], key: str, *, optional: bool = False) -> list[Any]:
    value = payload.get(key, [] if optional else None)
    if not isinstance(value, list):
        qualifier = "an array" if key in payload else "present as an array"
        raise LatticeGraphError(f"top-level {key!r} must be {qualifier}")
    return value


def _extra(record: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in known}


def normalize_strut_endpoints(endpoint0: Any, endpoint1: Any) -> tuple[int, int]:
    """Normalize an undirected strut's source endpoint IDs.

    Equal endpoint IDs are retained so that callers can diagnose self-loops
    instead of silently losing malformed provenance.
    """

    first = _integer(endpoint0, "strut endpoint 0")
    second = _integer(endpoint1, "strut endpoint 1")
    return (first, second) if first <= second else (second, first)


def parse_lattice_graph(
    payload: Mapping[str, Any], *, strict_references: bool = True
) -> LatticeGraph:
    """Parse an in-memory project lattice payload into canonical records.

    ``unit_cell_edge_idx`` and ``unit_cells`` are optional because the project's
    1x1x1 and multi-cell exports differ in those details.  Unknown fields are
    retained in each record's ``metadata`` mapping.
    """

    if not isinstance(payload, Mapping):
        raise LatticeGraphError("lattice payload must be a JSON object")

    junctions: list[Junction] = []
    for offset, raw in enumerate(_records(payload, "junctions")):
        if not isinstance(raw, Mapping):
            raise LatticeGraphError(f"junctions[{offset}] must be an object")
        jid = _integer(raw.get("id"), f"junctions[{offset}].id")
        position = _xyz(raw.get("position"), f"junctions[{offset}].position")
        indices = None if "indices" not in raw else _xyz(
            raw["indices"], f"junctions[{offset}].indices"
        )
        junctions.append(Junction(jid, position, indices, _extra(raw, {"id", "position", "indices"})))

    struts: list[Strut] = []
    for offset, raw in enumerate(_records(payload, "struts")):
        if not isinstance(raw, Mapping):
            raise LatticeGraphError(f"struts[{offset}] must be an object")
        sid = _integer(raw.get("id"), f"struts[{offset}].id")
        if "junction0" in raw and "junction1" in raw:
            endpoint0 = _integer(raw["junction0"], f"struts[{offset}].junction0")
            endpoint1 = _integer(raw["junction1"], f"struts[{offset}].junction1")
        elif (
            isinstance(raw.get("endpoints"), Sequence)
            and not isinstance(raw["endpoints"], (str, bytes))
            and len(raw["endpoints"]) == 2
        ):
            endpoint0 = _integer(raw["endpoints"][0], f"struts[{offset}].endpoints[0]")
            endpoint1 = _integer(raw["endpoints"][1], f"struts[{offset}].endpoints[1]")
        else:
            raise LatticeGraphError(f"struts[{offset}] is missing its two endpoint IDs")
        thickness = None
        if "thickness" in raw:
            try:
                thickness = float(raw["thickness"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise LatticeGraphError(f"struts[{offset}].thickness must be numeric") from exc
            if not math.isfinite(thickness) or thickness < 0:
                raise LatticeGraphError(f"struts[{offset}].thickness must be finite and nonnegative")
        edge_idx = None if "unit_cell_edge_idx" not in raw else _integer(
            raw["unit_cell_edge_idx"], f"struts[{offset}].unit_cell_edge_idx"
        )
        known = {"id", "junction0", "junction1", "endpoints", "thickness", "unit_cell_edge_idx"}
        struts.append(Strut(sid, endpoint0, endpoint1, thickness, edge_idx, _extra(raw, known)))

    cells: list[UnitCell] = []
    for offset, raw in enumerate(_records(payload, "unit_cells", optional=True)):
        if not isinstance(raw, Mapping):
            raise LatticeGraphError(f"unit_cells[{offset}] must be an object")
        cid = _integer(raw.get("id"), f"unit_cells[{offset}].id")
        raw_struts = raw.get("struts")
        if not isinstance(raw_struts, list):
            raise LatticeGraphError(f"unit_cells[{offset}].struts must be an array")
        cell_struts = tuple(
            _integer(item, f"unit_cells[{offset}].struts") for item in raw_struts
        )
        indices = None
        if "indices" in raw:
            xyz = _xyz(raw["indices"], f"unit_cells[{offset}].indices")
            indices = tuple(_integer(item, f"unit_cells[{offset}].indices") for item in xyz)
        cells.append(UnitCell(cid, cell_struts, indices, _extra(raw, {"id", "struts", "indices"})))

    for label, ids in (
        ("junction", [record.id for record in junctions]),
        ("strut", [record.id for record in struts]),
        ("unit-cell", [record.id for record in cells]),
    ):
        if len(ids) != len(set(ids)):
            raise LatticeGraphError(f"duplicate {label} IDs are not allowed")

    junctions.sort(key=lambda record: record.id)
    struts.sort(key=lambda record: record.id)
    cells.sort(key=lambda record: record.id)
    if strict_references:
        junction_ids = {record.id for record in junctions}
        dangling = sorted(
            (strut.id, endpoint)
            for strut in struts
            for endpoint in (strut.junction0, strut.junction1)
            if endpoint not in junction_ids
        )
        if dangling:
            raise LatticeGraphError(f"struts reference missing junctions: {dangling[:5]}")
        strut_ids = {record.id for record in struts}
        dangling_cells = sorted(
            (cell.id, strut_id)
            for cell in cells
            for strut_id in cell.strut_ids
            if strut_id not in strut_ids
        )
        if dangling_cells:
            raise LatticeGraphError(f"unit cells reference missing struts: {dangling_cells[:5]}")

    top_metadata = _extra(payload, {"junctions", "struts", "unit_cells"})
    return LatticeGraph(tuple(junctions), tuple(struts), tuple(cells), top_metadata)


_JUNCTION_RE = re.compile(
    r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"position"\s*:\s*\[([^\]]+)\]\s*,'
    r'\s*"indices"\s*:\s*\[([^\]]+)\]', re.S
)
_STRUT_RE = re.compile(
    r'\{\s*"id"\s*:\s*(\d+)\s*,(?:\s*"unit_cell_edge_idx"\s*:\s*(\d+)\s*,)?'
    r'\s*"junction0"\s*:\s*(\d+)\s*,\s*"junction1"\s*:\s*(\d+)\s*,'
    r'\s*"thickness"\s*:\s*([-+\d.eE]+)', re.S
)
_CELL_RE = re.compile(
    r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"struts"\s*:\s*\[([^\]]*)\]\s*,'
    r'\s*"indices"\s*:\s*\[([^\]]+)\]', re.S
)


def _numbers(text: str, converter: type[int] | type[float]) -> list[int] | list[float]:
    return [converter(token) for token in re.split(r"[,\s]+", text.strip()) if token]


def _tolerant_payload(text: str) -> dict[str, list[dict[str, Any]]]:
    junctions = [
        {"id": int(jid), "position": _numbers(position, float), "indices": _numbers(indices, float)}
        for jid, position, indices in _JUNCTION_RE.findall(text)
    ]
    struts = []
    for sid, edge_idx, endpoint0, endpoint1, thickness in _STRUT_RE.findall(text):
        record: dict[str, Any] = {
            "id": int(sid), "junction0": int(endpoint0), "junction1": int(endpoint1),
            "thickness": float(thickness),
        }
        if edge_idx:
            record["unit_cell_edge_idx"] = int(edge_idx)
        struts.append(record)
    cells = [
        {"id": int(cid), "struts": _numbers(struts_text, int), "indices": _numbers(indices, int)}
        for cid, struts_text, indices in _CELL_RE.findall(text)
    ]
    if not junctions and not struts and not cells:
        raise LatticeGraphError("tolerant parsing could not recover any lattice records")
    return {"junctions": junctions, "struts": struts, "unit_cells": cells}


def load_lattice_graph(
    path: str | os.PathLike[str], *, strict_references: bool = True, tolerant: bool = False
) -> LatticeGraph:
    """Read and parse a lattice JSON file.

    ``tolerant=True`` is intended only for the deliberately damaged project copy:
    intact records are recovered after a JSON syntax error and reference checks
    should normally be disabled by its caller.
    """

    source = Path(path)
    pointer = detect_lfs_pointer(source)
    if pointer is not None:
        raise AssetNotMaterializedError(
            f"Git-LFS lattice asset is not materialized: {pointer.path}"
        )
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise LatticeGraphError(f"cannot read lattice JSON {source}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        if not tolerant:
            raise LatticeGraphError(
                f"invalid JSON in {source} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        payload = _tolerant_payload(text)
    return parse_lattice_graph(payload, strict_references=strict_references)


def weld_coincident_nodes(graph: LatticeGraph, *, tolerance: float = 1e-6) -> WeldedGraph:
    """Weld junction positions separated by at most ``tolerance`` XYZ units.

    Clustering is deterministic and transitive.  A spatial hash avoids the
    quadratic all-pairs comparison, and cluster/node IDs are assigned by the
    smallest source junction ID.  ``tolerance=0`` requests exact-position welds.
    """

    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LatticeGraphError("weld tolerance must be numeric") from exc
    if not math.isfinite(tolerance) or tolerance < 0:
        raise LatticeGraphError("weld tolerance must be finite and nonnegative")

    records = list(graph.junctions)
    parent = list(range(len(records)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    if tolerance == 0:
        first_at: dict[tuple[float, float, float], int] = {}
        for index, record in enumerate(records):
            if record.position in first_at:
                union(index, first_at[record.position])
            else:
                first_at[record.position] = index
    else:
        buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        tolerance_sq = tolerance * tolerance
        neighbor_offsets = tuple(
            (dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
        )
        for index, record in enumerate(records):
            key = tuple(math.floor(value / tolerance) for value in record.position)
            for dx, dy, dz in neighbor_offsets:
                neighbor = (key[0] + dx, key[1] + dy, key[2] + dz)
                for other in buckets.get(neighbor, ()):
                    distance_sq = sum(
                        (record.position[axis] - records[other].position[axis]) ** 2
                        for axis in range(3)
                    )
                    if distance_sq <= tolerance_sq:
                        union(index, other)
            buckets[key].append(index)

    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        members[find(index)].append(index)
    groups = sorted(members.values(), key=lambda group: records[min(group)].id)

    nodes: list[WeldedNode] = []
    junction_to_node: dict[int, int] = {}
    for node_id, group in enumerate(groups):
        group.sort(key=lambda index: records[index].id)
        source_ids = tuple(records[index].id for index in group)
        centroid = tuple(
            math.fsum(records[index].position[axis] for index in group) / len(group)
            for axis in range(3)
        )
        nodes.append(WeldedNode(node_id, centroid, source_ids))
        junction_to_node.update((source_id, node_id) for source_id in source_ids)

    grouped_struts: dict[tuple[int, int], list[Strut]] = defaultdict(list)
    dangling: list[int] = []
    self_loops: list[int] = []
    for strut in graph.struts:
        if strut.junction0 not in junction_to_node or strut.junction1 not in junction_to_node:
            dangling.append(strut.id)
            continue
        endpoints = normalize_strut_endpoints(
            junction_to_node[strut.junction0], junction_to_node[strut.junction1]
        )
        if endpoints[0] == endpoints[1]:
            self_loops.append(strut.id)
        else:
            grouped_struts[endpoints].append(strut)

    welded_struts: list[WeldedStrut] = []
    for edge_id, endpoints in enumerate(sorted(grouped_struts)):
        sources = sorted(grouped_struts[endpoints], key=lambda strut: strut.id)
        welded_struts.append(WeldedStrut(
            edge_id, endpoints[0], endpoints[1],
            tuple(strut.id for strut in sources),
            tuple(strut.thickness for strut in sources),
        ))
    return WeldedGraph(
        tuple(nodes), tuple(welded_struts), junction_to_node, tuple(sorted(dangling)),
        tuple(sorted(self_loops)), tolerance, graph,
    )


def connected_components(graph: WeldedGraph) -> tuple[tuple[int, ...], ...]:
    """Return deterministic connected components, including isolated nodes."""

    adjacency = {node.id: set() for node in graph.nodes}
    for strut in graph.struts:
        adjacency[strut.node0].add(strut.node1)
        adjacency[strut.node1].add(strut.node0)
    unseen = set(adjacency)
    components: list[tuple[int, ...]] = []
    while unseen:
        start = min(unseen)
        queue = deque([start])
        unseen.remove(start)
        component: list[int] = []
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in sorted(adjacency[node]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        components.append(tuple(sorted(component)))
    return tuple(components)


def summarize_components(graph: WeldedGraph) -> ComponentSummary:
    """Summarize welded connectivity without discarding isolated nodes."""

    components = connected_components(graph)
    sizes = tuple(len(component) for component in components)
    largest = max(sizes, default=0)
    isolated = tuple(component[0] for component in components if len(component) == 1)
    fraction = largest / len(graph.nodes) if graph.nodes else 0.0
    return ComponentSummary(len(components), sizes, largest, fraction, isolated)
