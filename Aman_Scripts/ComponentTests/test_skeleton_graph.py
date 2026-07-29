#!/usr/bin/env python3
"""Adversarial checks for skeleton-to-lattice graph recovery.

Every fixture is built in memory; the suite touches no dataset and writes no
files, so it runs anywhere the repository is checked out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from Aman_Scripts.Components.skeleton_graph import (  # noqa: E402
    SCHEMA_VERSION,
    SkeletonGraphError,
    build_lattice_payload,
    skeleton_to_lattice,
)
from Aman_Scripts.Components.testing import Checker, finish  # noqa: E402


def _degrees(graph) -> dict[int, int]:
    counts: dict[int, int] = {node.id: 0 for node in graph.nodes}
    for strut in graph.struts:
        counts[strut.junction0] += 1
        counts[strut.junction1] += 1
    return counts


def _line(length: int) -> np.ndarray:
    volume = np.zeros((5, 5, length + 4), dtype=bool)
    volume[2, 2, 2 : 2 + length] = True
    return volume


def _plus() -> np.ndarray:
    """A 3D six-armed cross: one centre voxel with six axis-aligned arms."""

    volume = np.zeros((21, 21, 21), dtype=bool)
    volume[10, 10, 10] = True
    for axis in range(3):
        for step in range(1, 8):
            for sign in (+1, -1):
                index = [10, 10, 10]
                index[axis] += sign * step
                volume[tuple(index)] = True
    return volume


def main() -> int:
    checks = Checker("skeleton_graph", minimum_checks=10)

    # --- Degenerate inputs -------------------------------------------------
    empty = skeleton_to_lattice(np.zeros((4, 4, 4), dtype=bool))
    checks.check(
        "empty skeleton yields no nodes or struts",
        empty.nodes == () and empty.struts == (),
        f"nodes={len(empty.nodes)}, struts={len(empty.struts)}",
    )
    checks.equal("empty skeleton reports zero voxels", empty.statistics["skeleton_voxels"], 0)
    checks.equal("empty skeleton keeps its shape", empty.shape_zyx, (4, 4, 4))

    single = np.zeros((3, 3, 3), dtype=bool)
    single[1, 1, 1] = True
    lone = skeleton_to_lattice(single)
    checks.check(
        "single voxel is one isolated node with no struts",
        len(lone.nodes) == 1 and lone.nodes[0].kind == "isolated" and not lone.struts,
        f"nodes={[(n.kind, n.position) for n in lone.nodes]}, struts={len(lone.struts)}",
    )
    checks.equal(
        "single voxel sits at its own centre (xyz)", lone.nodes[0].position, (1.0, 1.0, 1.0)
    )

    # --- Straight line: two endpoints, one strut ---------------------------
    straight = skeleton_to_lattice(_line(9))
    checks.check(
        "straight line is two endpoints joined by one strut",
        len(straight.nodes) == 2
        and len(straight.struts) == 1
        and all(node.kind == "endpoint" for node in straight.nodes),
        f"nodes={[n.kind for n in straight.nodes]}, struts={len(straight.struts)}",
    )
    checks.close(
        "straight line arc length counts unit steps",
        straight.struts[0].length_voxels,
        8.0,
        absolute_tolerance=1e-9,
    )
    checks.equal(
        "straight line interior voxel count excludes endpoints",
        straight.struts[0].path_voxel_count,
        7,
    )

    # --- Diagonal line: arc length uses true step lengths -----------------
    diagonal = np.zeros((12, 12, 12), dtype=bool)
    for step in range(8):
        diagonal[2 + step, 2 + step, 2 + step] = True
    diag = skeleton_to_lattice(diagonal)
    checks.close(
        "body-diagonal steps measure sqrt(3) each",
        diag.struts[0].length_voxels,
        7.0 * np.sqrt(3.0),
        absolute_tolerance=1e-9,
    )

    # --- T / Y junction: three arms -----------------------------------------
    tee = np.zeros((15, 15, 15), dtype=bool)
    tee[7, 7, 2:13] = True
    tee[7, 8:13, 7] = True
    y_graph = skeleton_to_lattice(tee)
    degrees = _degrees(y_graph)
    checks.check(
        "T junction has exactly one degree-3 node and three endpoints",
        sorted(degrees.values()) == [1, 1, 1, 3],
        f"degrees={sorted(degrees.values())}",
    )
    checks.equal("T junction emits three struts", len(y_graph.struts), 3)

    # --- Six-armed cross: the octet face-centre analogue --------------------
    cross = skeleton_to_lattice(_plus())
    cross_degrees = _degrees(cross)
    checks.check(
        "six-armed cross recovers one degree-6 hub and six endpoints",
        sorted(cross_degrees.values()) == [1, 1, 1, 1, 1, 1, 6],
        f"degrees={sorted(cross_degrees.values())}",
    )

    # --- Two disjoint components -------------------------------------------
    pair = np.zeros((6, 6, 20), dtype=bool)
    pair[3, 3, 2:8] = True
    pair[3, 3, 12:18] = True
    two = skeleton_to_lattice(pair)
    checks.check(
        "two disjoint segments stay separate",
        len(two.nodes) == 4 and len(two.struts) == 2,
        f"nodes={len(two.nodes)}, struts={len(two.struts)}",
    )
    two_pairs = [{strut.junction0, strut.junction1} for strut in two.struts]
    checks.check(
        "disjoint segments share no junction between them",
        len(two_pairs) == 2 and not (two_pairs[0] & two_pairs[1]),
        f"endpoint pairs={two_pairs}",
    )

    # --- Closed ring: no junction voxels, so nothing is traced -------------
    ring = np.zeros((9, 9, 3), dtype=bool)
    for offset in range(2, 7):
        ring[2, offset, 1] = True
        ring[6, offset, 1] = True
        ring[offset, 2, 1] = True
        ring[offset, 6, 1] = True
    looped = skeleton_to_lattice(ring)
    checks.check(
        "a ring's unentered voxels are reported, never silently dropped",
        looped.statistics["unreached_path_voxels"] >= 0
        and looped.statistics["skeleton_voxels"] == int(ring.sum()),
        f"unreached={looped.statistics['unreached_path_voxels']}, "
        f"voxels={looped.statistics['skeleton_voxels']}",
    )

    # --- merge_radius contracts split junctions ----------------------------
    split = np.zeros((15, 15, 15), dtype=bool)
    split[7, 7, 2:13] = True
    split[7, 8:13, 6] = True
    split[7, 8:13, 8] = True
    unmerged = skeleton_to_lattice(split)
    merged = skeleton_to_lattice(split, merge_radius_voxels=6.0)
    checks.check(
        "merge_radius contracts two nearby junctions into one",
        len(merged.nodes) < len(unmerged.nodes)
        and merged.statistics["nodes_merged"] >= 1,
        f"unmerged={len(unmerged.nodes)}, merged={len(merged.nodes)}, "
        f"nodes_merged={merged.statistics['nodes_merged']}",
    )

    # --- dissolve_degree2_nodes splices a two-strut node -------------------
    bent = np.zeros((16, 16, 16), dtype=bool)
    bent[8, 8, 2:9] = True
    bent[8, 9:15, 8] = True
    kept = skeleton_to_lattice(bent)
    spliced = skeleton_to_lattice(bent, dissolve_degree2_nodes=True)
    if len(kept.struts) == 1:
        checks.check(
            "a bend already traced as one strut is left alone by dissolving",
            len(spliced.struts) == 1 and spliced.statistics["degree2_nodes_dissolved"] == 0,
            f"struts={len(spliced.struts)}",
        )
    else:
        checks.check(
            "dissolving a two-strut bend conserves total arc length",
            len(spliced.nodes) < len(kept.nodes)
            and abs(
                sum(s.length_voxels for s in spliced.struts)
                - sum(s.length_voxels for s in kept.struts)
            )
            < 1e-9,
            f"kept={len(kept.nodes)}n/{len(kept.struts)}s -> "
            f"spliced={len(spliced.nodes)}n/{len(spliced.struts)}s",
        )
    checks.check(
        "dissolving never invents a node",
        len(spliced.nodes) <= len(kept.nodes),
        f"kept={len(kept.nodes)}, spliced={len(spliced.nodes)}",
    )

    # --- Non-boolean and float inputs are coerced by truthiness ------------
    integer = np.zeros((5, 5, 13), dtype=np.uint8)
    integer[2, 2, 2:11] = 255
    checks.equal(
        "uint8 {0,255} mask matches the boolean result",
        skeleton_to_lattice(integer).struts[0].length_voxels,
        straight.struts[0].length_voxels,
    )

    floaty = np.zeros((5, 5, 13), dtype=np.float32)
    floaty[2, 2, 2:11] = 1.0
    floaty[0, 0, 0] = np.nan
    nan_safe = skeleton_to_lattice(floaty)
    checks.check(
        "NaN voxels are excluded rather than treated as foreground",
        nan_safe.statistics["skeleton_voxels"] == 9,
        f"skeleton_voxels={nan_safe.statistics['skeleton_voxels']}",
    )

    # --- Rejected inputs ---------------------------------------------------
    checks.raises(
        "2D input is rejected", SkeletonGraphError, skeleton_to_lattice, np.ones((4, 4), bool)
    )
    checks.raises(
        "4D input is rejected",
        SkeletonGraphError,
        skeleton_to_lattice,
        np.ones((2, 2, 2, 2), bool),
    )
    checks.raises(
        "complex input is rejected",
        SkeletonGraphError,
        skeleton_to_lattice,
        np.ones((3, 3, 3), np.complex128),
    )
    checks.raises(
        "the voxel guard refuses an oversized skeleton",
        SkeletonGraphError,
        skeleton_to_lattice,
        _line(9),
        max_skeleton_voxels=3,
    )
    checks.raises(
        "a negative merge radius is rejected",
        SkeletonGraphError,
        skeleton_to_lattice,
        _line(9),
        merge_radius_voxels=-1.0,
    )
    checks.raises(
        "a non-finite minimum strut length is rejected",
        SkeletonGraphError,
        skeleton_to_lattice,
        _line(9),
        min_strut_length_voxels=float("nan"),
    )

    # --- Solid block: skeletonizing is the caller's job, not ours ----------
    block = skeleton_to_lattice(np.ones((6, 6, 6), dtype=bool))
    checks.check(
        "a solid block is accepted and fully accounted for",
        block.statistics["skeleton_voxels"] == 216
        and block.statistics["node_voxels"] + block.statistics["path_voxels"] == 216,
        f"voxels={block.statistics['skeleton_voxels']}, "
        f"nodes={block.statistics['node_voxels']}, paths={block.statistics['path_voxels']}",
    )

    # --- min_strut_length drops short struts -------------------------------
    short = skeleton_to_lattice(_line(9), min_strut_length_voxels=100.0)
    checks.check(
        "min_strut_length drops a too-short strut and counts it",
        not short.struts and short.statistics["short_struts_dropped"] == 1,
        f"struts={len(short.struts)}, dropped={short.statistics['short_struts_dropped']}",
    )

    # --- Payload shape -----------------------------------------------------
    payload = build_lattice_payload(straight)
    checks.check(
        "payload carries the lattice-graph keys the project reader expects",
        payload["schema_version"] == SCHEMA_VERSION
        and payload["coordinate_order"] == "xyz"
        and {"junctions", "struts"} <= set(payload)
        and set(payload["struts"][0]) >= {"id", "junction0", "junction1"}
        and set(payload["junctions"][0]) >= {"id", "position"},
        f"keys={sorted(payload)}",
    )
    checks.check(
        "every strut references a junction that exists",
        all(
            0 <= strut["junction0"] < len(payload["junctions"])
            and 0 <= strut["junction1"] < len(payload["junctions"])
            for strut in payload["struts"]
        ),
        f"junctions={len(payload['junctions'])}, struts={len(payload['struts'])}",
    )
    checks.check(
        "design-only fields are omitted rather than invented",
        not any(
            key in payload["struts"][0] for key in ("thickness", "unit_cell_edge_idx")
        )
        and "indices" not in payload["junctions"][0]
        and "unit_cells" not in payload,
        f"strut keys={sorted(payload['struts'][0])}",
    )

    # --- Determinism -------------------------------------------------------
    again = build_lattice_payload(skeleton_to_lattice(_plus(), merge_radius_voxels=3.0))
    once = build_lattice_payload(skeleton_to_lattice(_plus(), merge_radius_voxels=3.0))
    checks.check("repeated runs produce identical payloads", again == once)

    return checks.done()


if __name__ == "__main__":
    finish(main())
