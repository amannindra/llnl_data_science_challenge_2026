#!/usr/bin/env python3
"""Deterministic adversarial checks for ``Components.lattice_graph``."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Scripts.Components.lattice_graph import (  # noqa: E402
    LatticeGraphError,
    connected_components,
    load_lattice_graph,
    normalize_strut_endpoints,
    parse_lattice_graph,
    summarize_components,
    weld_coincident_nodes,
)
from Scripts.Components.asset_io import AssetNotMaterializedError  # noqa: E402


class Checker:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        passed = bool(condition)
        self.results.append({"name": name, "passed": passed, "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    def raises(self, name: str, exception: type[BaseException], function) -> None:
        try:
            function()
        except exception:
            self.check(name, True)
        except Exception as exc:  # noqa: BLE001 - test must report wrong exception
            self.check(name, False, f"wrong exception {type(exc).__name__}: {exc}")
        else:
            self.check(name, False, "no exception")

    def finish(self) -> int:
        passed = sum(bool(item["passed"]) for item in self.results)
        summary = {"suite": "lattice_graph", "passed": passed, "failed": len(self.results) - passed,
                   "total": len(self.results), "results": self.results}
        print(json.dumps(summary, sort_keys=True))
        return 0 if passed == len(self.results) and len(self.results) >= 12 else 1


def fixture() -> dict[str, object]:
    """Small graph with a duplicate physical node, duplicate edge, and isolate."""

    return {
        "format": "synthetic-test",
        "junctions": [
            {"id": 20, "position": [3.0, 0.0, 0.0], "indices": [1, 1, 1]},
            {"id": 10, "position": [0.0, 0.0, 0.0], "indices": [0, 0, 0], "tag": "origin"},
            {"id": 7, "position": [1.0000004, 0.0, 0.0], "indices": [0.5, 0, 0]},
            {"id": 2, "position": [1.0, 0.0, 0.0], "indices": [1, 0, 0]},
            {"id": 30, "position": [9.0, 9.0, 9.0], "indices": [0, 0, 0]},
        ],
        "struts": [
            {"id": 9, "junction0": 7, "junction1": 20, "thickness": 0.2},
            {"id": 5, "unit_cell_edge_idx": 8, "junction0": 2, "junction1": 10,
             "thickness": 0.1, "quality": "known"},
            {"id": 3, "junction0": 10, "junction1": 7, "thickness": 0.1},
            {"id": 12, "junction0": 2, "junction1": 7, "thickness": 0.1},
        ],
        "unit_cells": [
            {"id": 0, "struts": [3, 5, 9, 12], "indices": [0, 0, 0], "name": "cell"}
        ],
    }


def main() -> int:
    checks = Checker()
    graph = parse_lattice_graph(fixture())

    checks.check("parser canonicalizes junction order", [item.id for item in graph.junctions] == [2, 7, 10, 20, 30])
    checks.check("parser canonicalizes strut order", [item.id for item in graph.struts] == [3, 5, 9, 12])
    checks.check("XYZ positions become immutable triples", graph.junctions[0].position == (1.0, 0.0, 0.0))
    checks.check("optional unit_cell_edge_idx is preserved", graph.strut_by_id()[5].unit_cell_edge_idx == 8)
    checks.check("absent unit_cell_edge_idx stays None", graph.strut_by_id()[3].unit_cell_edge_idx is None)
    checks.check("unknown record metadata is preserved", graph.junction_by_id()[10].metadata.get("tag") == "origin")
    checks.check("unknown top-level metadata is preserved", graph.metadata.get("format") == "synthetic-test")
    checks.check("endpoint normalization is orientation independent",
                 normalize_strut_endpoints(10, 2) == normalize_strut_endpoints(2, 10) == (2, 10))
    checks.raises("non-integral endpoint IDs are rejected", LatticeGraphError,
                  lambda: normalize_strut_endpoints(1.5, 2))
    string_endpoints = fixture()
    string_endpoints["struts"] = [{"id": 1, "endpoints": "12", "thickness": 0.1}]
    string_endpoints["unit_cells"] = []
    checks.raises("string endpoint pair is rejected", LatticeGraphError,
                  lambda: parse_lattice_graph(string_endpoints))

    welded = weld_coincident_nodes(graph, tolerance=1e-6)
    checks.check("coincident records weld to four physical nodes", len(welded.nodes) == 4)
    paired_node = welded.junction_to_node[2]
    checks.check("weld preserves all source-junction provenance",
                 welded.nodes[paired_node].source_junction_ids == (2, 7))
    checks.check("welded centroid is deterministic",
                 welded.nodes[paired_node].position == (1.0000002000000001, 0.0, 0.0))
    duplicate_edge = next(edge for edge in welded.struts if edge.source_strut_ids == (3, 5))
    checks.check("duplicate physical edges retain both source struts", duplicate_edge.endpoints == (0, 1))
    checks.check("collapsed source edge is reported as self-loop", welded.self_loop_strut_ids == (12,))

    components = connected_components(welded)
    summary = summarize_components(welded)
    checks.check("connectivity includes isolated nodes", sorted(map(len, components)) == [1, 3])
    checks.check("component summary reports largest fraction", summary.component_count == 2 and summary.largest_component_fraction == 0.75)
    checks.check("component summary identifies the isolate", summary.isolated_node_ids == (3,))

    exact = weld_coincident_nodes(graph, tolerance=0)
    checks.check("zero tolerance means exact-position welding", len(exact.nodes) == 5)
    checks.raises("negative weld tolerance is rejected", LatticeGraphError,
                  lambda: weld_coincident_nodes(graph, tolerance=-1))

    reversed_payload = fixture()
    reversed_payload["junctions"] = list(reversed(reversed_payload["junctions"]))  # type: ignore[index]
    reversed_payload["struts"] = list(reversed(reversed_payload["struts"]))  # type: ignore[index]
    reordered = weld_coincident_nodes(parse_lattice_graph(reversed_payload), tolerance=1e-6)
    checks.check("input record order cannot change weld result",
                 [(node.position, node.source_junction_ids) for node in reordered.nodes]
                 == [(node.position, node.source_junction_ids) for node in welded.nodes])

    transitive_payload = {
        "junctions": [
            {"id": 0, "position": [0, 0, 0]},
            {"id": 1, "position": [0.75, 0, 0]},
            {"id": 2, "position": [1.5, 0, 0]},
        ],
        "struts": [],
    }
    transitive = weld_coincident_nodes(parse_lattice_graph(transitive_payload), tolerance=1.0)
    checks.check("welding is transitive across tolerance neighbors", len(transitive.nodes) == 1)

    duplicate_ids = fixture()
    duplicate_ids["junctions"] = list(duplicate_ids["junctions"]) + [  # type: ignore[index]
        {"id": 2, "position": [99, 99, 99]}
    ]
    checks.raises("duplicate junction IDs are rejected", LatticeGraphError,
                  lambda: parse_lattice_graph(duplicate_ids))

    dangling = fixture()
    dangling["struts"] = list(dangling["struts"]) + [  # type: ignore[index]
        {"id": 99, "junction0": 10, "junction1": 404, "thickness": 0.1}
    ]
    checks.raises("dangling endpoints fail strict parsing", LatticeGraphError,
                  lambda: parse_lattice_graph(dangling))
    permissive = parse_lattice_graph(dangling, strict_references=False)
    checks.check("damaged graphs support explicit permissive parsing", permissive.strut_by_id()[99].junction1 == 404)
    permissive_welded = weld_coincident_nodes(permissive)
    checks.check("permissive welding preserves dangling strut provenance",
                 permissive_welded.dangling_strut_ids == (99,))

    with tempfile.TemporaryDirectory() as temporary:
        malformed = Path(temporary) / "recover.json"
        malformed.write_text(
            'BROKEN {"id":0,"position":[0,0,0],"indices":[0,0,0]} '
            '{"id":1,"position":[1,0,0],"indices":[1,0,0]} '
            '{"id":0,"junction0":0,"junction1":1,"thickness":0.1} '
            '{"id":0,"struts":[0],"indices":[0,0,0]}', encoding="utf-8"
        )
        recovered = load_lattice_graph(malformed, tolerant=True, strict_references=False)
        checks.check("tolerant loader recovers intact records from damaged JSON",
                     (len(recovered.junctions), len(recovered.struts), len(recovered.unit_cells)) == (2, 1, 1))
        checks.raises("strict loader reports malformed JSON", LatticeGraphError,
                      lambda: load_lattice_graph(malformed))
        pointer = Path(temporary) / "pointer.json"
        pointer.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{'a' * 64}\nsize 12345\n",
            encoding="utf-8",
        )
        checks.raises("lattice loader preserves LFS-not-materialized error contract",
                      AssetNotMaterializedError, lambda: load_lattice_graph(pointer))

    real_small = load_lattice_graph(ROOT / "data" / "unitcell" / "polyhedron_1x1x1.json")
    checks.check("real 1x1x1 project schema parses", (len(real_small.junctions), len(real_small.struts), len(real_small.unit_cells)) == (14, 12, 1))
    checks.check("real 1x1x1 optional edge index is absent", real_small.struts[0].unit_cell_edge_idx is None)

    real_multi = load_lattice_graph(ROOT / "data" / "octet_truss_8x8x8" / "octet_truss_8x8x8.json")
    checks.check("real multi-cell project schema parses", (len(real_multi.junctions), len(real_multi.struts), len(real_multi.unit_cells)) == (7168, 13056, 512))
    checks.check("real multi-cell edge index is retained", real_multi.struts[0].unit_cell_edge_idx is not None)
    real_welded = weld_coincident_nodes(real_multi, tolerance=1e-9)
    checks.check("real 8x8x8 duplicate records weld to 2,457 physical nodes",
                 len(real_welded.nodes) == 2457, f"nodes={len(real_welded.nodes)}")
    real_connectivity = summarize_components(real_welded)
    checks.check("real 8x8x8 welded graph is one connected component",
                 real_connectivity.component_count == 1,
                 f"components={real_connectivity.component_count}")

    registered_path = (ROOT / "data" / "missing_struts" / "registered_jsons"
                       / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
    registered = load_lattice_graph(registered_path)
    registered_welded = weld_coincident_nodes(registered, tolerance=1e-6)
    checks.check("real registered 9x9x9 graph welds to 3,430 physical nodes",
                 len(registered_welded.nodes) == 3430,
                 f"nodes={len(registered_welded.nodes)}")
    checks.check("real registered 9x9x9 graph remains connected after welding",
                 summarize_components(registered_welded).component_count == 1)

    damaged_path = registered_path.with_name(
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices copy.json"
    )
    damaged = load_lattice_graph(damaged_path, tolerant=True, strict_references=False)
    checks.check("real damaged JSON tolerant parse recovers expected junction records",
                 len(damaged.junctions) == 10196, f"junctions={len(damaged.junctions)}")
    checks.check("real damaged JSON tolerant parse recovers struts and unit cells",
                 (len(damaged.struts), len(damaged.unit_cells)) == (18394, 729),
                 f"struts={len(damaged.struts)}, cells={len(damaged.unit_cells)}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
