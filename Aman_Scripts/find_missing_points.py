#!/usr/bin/env python
"""
find_missing_points.py -- defect detector for a *damaged* registered lattice JSON.

Problem
-------
`210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json` is the IDEAL
registered octet-truss graph (every junction and strut present).  In a real
workflow we never get that ideal file -- we get something like
`... Slices copy.json`, where junction records (points) have been lost.  This
script finds those missing points USING ONLY THE DAMAGED FILE, then (because we
happen to have the ideal file here) validates its own answer against ground
truth and finishes with explicit PASS/FAIL checks covering all three
top-level arrays: junctions, struts, AND unit_cells.

How detection works WITHOUT the ideal file
------------------------------------------
The file format is machine-generated and highly redundant, and a perfect octet
lattice is completely predictable.  Three independent structures are exploited:

1.  TEMPLATE:  an N x N x N octet truss has a known node set -- cell corners at
    integer lattice coordinates and face centers at half-integer coordinates
    (3,430 unique physical nodes and 18,468 unique struts for N=9).  Every
    junction record carries its own global lattice coordinate in `indices`, so
    "expected minus present" directly yields the missing physical points.
2.  ID ARITHMETIC:  junction ids are structured, id = cell_id*14 + local_slot
    (14 records per unit cell: 8 corners + 6 face centers).  Gaps in the id
    sequence pinpoint each deleted record, and the (cell, slot) decomposition
    predicts exactly where the deleted record used to sit.
3.  AFFINE FRAME:  positions are an affine image of the lattice coordinates
    (the similarity registration), so a least-squares fit position ~= A@index+t
    on the SURVIVING records converts every predicted missing lattice
    coordinate into a CT voxel position.

The damaged file may not even be valid JSON (hand-deleting a record can eat a
closing brace), so parsing falls back to a tolerant regex extractor that pulls
every intact record out of the raw text.

Outputs (Scripts/outputs/)
--------------------------
  defect_report.json         machine-readable full report (feeds the napari viz)
  defect_missing_points.csv  one row per missing physical point
  defect_missing_struts.csv  one row per missing / anchor-less strut
  defect_overview.png        3D + projection figure of the damage

Run
---
  ~/miniconda3/envs/DSC/bin/python Scripts/find_missing_points.py
"""

import argparse
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

try:  # Package import.
    from .Components.asset_io import load_json
    from .Components.paths import data_path, find_repository_root, output_path
    from .Components.reporting import write_json
except ImportError:  # Direct execution.
    from Components.asset_io import load_json
    from Components.paths import data_path, find_repository_root, output_path
    from Components.reporting import write_json


ROOT = str(find_repository_root(__file__))
OUT = str(output_path(root=ROOT))
REG_DIR = str(data_path("missing_struts", "registered_jsons", root=ROOT))
IDEAL = os.path.join(REG_DIR, "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
DAMAGED = os.path.join(REG_DIR, "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices copy.json")

RECORDS_PER_CELL = 14           # 8 cell corners + 6 face centers
EDGES_PER_CELL = 36             # 24 corner-FC + 12 FC-FC (octahedron) edges


# ===========================================================================
# Loading -- strict JSON first, tolerant regex extraction if the file is broken
# ===========================================================================
_JUNCTION_RE = re.compile(
    r'\{\s*"id":\s*(\d+),\s*"position":\s*\[\s*([^\]]+?)\s*\],'
    r'\s*"indices":\s*\[\s*([^\]]+?)\s*\]', re.S)
_STRUT_RE = re.compile(
    r'\{\s*"id":\s*(\d+),\s*"unit_cell_edge_idx":\s*(\d+),'
    r'\s*"junction0":\s*(\d+),\s*"junction1":\s*(\d+),'
    r'\s*"thickness":\s*([-\d.eE+]+)', re.S)
_CELL_RE = re.compile(
    r'\{\s*"id":\s*(\d+),\s*"struts":\s*\[\s*([^\]]+?)\s*\],'
    r'\s*"indices":\s*\[\s*([^\]]+?)\s*\]', re.S)


def _floats(text):
    return [float(tok) for tok in re.split(r"[,\s]+", text.strip()) if tok]


def _ints(text):
    return [int(tok) for tok in re.split(r"[,\s]+", text.strip()) if tok]


def tolerant_extract(text):
    """Pull every intact record out of raw (possibly syntactically broken) text."""
    junctions = [
        {"id": int(i), "position": _floats(p), "indices": _floats(x)}
        for i, p, x in _JUNCTION_RE.findall(text)
    ]
    struts = [
        {"id": int(i), "unit_cell_edge_idx": int(e),
         "junction0": int(a), "junction1": int(b), "thickness": float(t)}
        for i, e, a, b, t in _STRUT_RE.findall(text)
    ]
    unit_cells = [
        {"id": int(i), "struts": _ints(s), "indices": _ints(x)}
        for i, s, x in _CELL_RE.findall(text)
    ]
    return {"junctions": junctions, "struts": struts, "unit_cells": unit_cells}


def load_graph(path):
    """Return (graph_dict, parse_mode, syntax_error_or_None)."""
    with open(path) as f:
        text = f.read()
    try:
        return json.loads(text), "strict", None
    except json.JSONDecodeError as exc:
        return tolerant_extract(text), "tolerant", f"line {exc.lineno} col {exc.colno}: {exc.msg}"


# ===========================================================================
# Lattice template + coordinate machinery
# ===========================================================================
def key_of(indices):
    """Lattice coordinate -> integer weld key (doubled so face centers land on ints)."""
    return tuple(int(round(2.0 * v)) for v in indices)


def cell_node_keys(ci, cj, ck):
    """The 14 node keys of unit cell (ci,cj,ck): 8 corners + 6 face centers."""
    i, j, k = 2 * ci, 2 * cj, 2 * ck
    corners = [(i + a, j + b, k + c) for a in (0, 2) for b in (0, 2) for c in (0, 2)]
    faces = [(i + 1, j + 1, k), (i + 1, j + 1, k + 2),
             (i + 1, j, k + 1), (i + 1, j + 2, k + 1),
             (i, j + 1, k + 1), (i + 2, j + 1, k + 1)]
    return corners + faces


def octet_template(n_cells):
    """Expected (node_keys, edge_pairs) for a full n^3 octet lattice."""
    nodes, edges = set(), set()
    for ci, cj, ck in itertools.product(range(n_cells), repeat=3):
        keys = cell_node_keys(ci, cj, ck)
        nodes.update(keys)
        # An octet edge is any node pair in the cell at squared key-distance 2
        # (= sqrt(0.5) cell units): 24 corner-FC + 12 FC-FC pairs, nothing else.
        for a, b in itertools.combinations(keys, 2):
            d2 = sum((ax - bx) ** 2 for ax, bx in zip(a, b))
            if d2 == 2:
                edges.add((min(a, b), max(a, b)))
    return nodes, edges


def fit_affine(indices, positions):
    """Least-squares fit positions ~= [indices, 1] @ B.  Returns (B, max residual)."""
    X = np.column_stack([indices, np.ones(len(indices))])
    B, *_ = np.linalg.lstsq(X, positions, rcond=None)
    resid = np.abs(X @ B - positions).max()
    return B, float(resid)


def key_to_position(keys, B):
    """Weld keys (2x lattice coords) -> voxel positions via the fitted frame."""
    arr = np.asarray(list(keys), float) / 2.0
    if len(arr) == 0:
        return np.zeros((0, 3))
    return np.column_stack([arr, np.ones(len(arr))]) @ B


# ===========================================================================
# The detector -- uses ONLY the damaged graph
# ===========================================================================
def detect(graph):
    """Find missing points / struts from the damaged graph alone.

    IMPORTANT COORDINATE FACT: a junction record's `indices` are LOCAL to its
    parent unit cell (values 0 / 0.5 / 1).  The global lattice coordinate is
    recovered through the structured record id (id = cell_id*14 + slot):
        global_key = 2*cell_indices(id // 14) + 2*local_indices
    which is also exactly why the same physical node appears as several records
    (one per touching cell, each with different local indices).
    """
    junctions, struts, cells = graph["junctions"], graph["struts"], graph["unit_cells"]

    # --- grid extent from the unit_cells section (points were deleted, not cells)
    cell_idx = {c["id"]: tuple(c["indices"]) for c in cells}
    n_cells = max(max(v) for v in cell_idx.values()) + 1
    expected_nodes, expected_edges = octet_template(n_cells)

    # --- globalize every surviving record: local indices -> global weld key ---
    id_to_key = {}
    for j in junctions:
        cell = j["id"] // RECORDS_PER_CELL
        local = key_of(j["indices"])                      # local offset, doubled
        id_to_key[j["id"]] = tuple(2 * c + o for c, o in zip(cell_idx[cell], local))
    records_by_key = defaultdict(list)
    for j in junctions:
        records_by_key[id_to_key[j["id"]]].append(j["id"])

    # --- lattice frame: GLOBAL lattice coordinate -> voxel position -----------
    idx = np.array([id_to_key[j["id"]] for j in junctions], float) / 2.0
    pos = np.array([j["position"] for j in junctions], float)
    B, resid = fit_affine(idx, pos)

    # --- id arithmetic: learn the local-slot -> offset table from survivors ---
    slot_votes = defaultdict(Counter)
    for j in junctions:
        slot_votes[j["id"] % RECORDS_PER_CELL][key_of(j["indices"])] += 1
    slot_offset = {s: v.most_common(1)[0][0] for s, v in slot_votes.items()}
    slot_consistent = all(len(v) == 1 for v in slot_votes.values())

    # --- deleted junction RECORDS (id gaps), each mapped back to its key ------
    n_expected_records = RECORDS_PER_CELL * len(cells)
    missing_record_ids = sorted(set(range(n_expected_records)) - set(id_to_key))
    missing_record_key = {}
    for rid in missing_record_ids:
        cell, slot = rid // RECORDS_PER_CELL, rid % RECORDS_PER_CELL
        missing_record_key[rid] = tuple(
            2 * c + o for c, o in zip(cell_idx[cell], slot_offset[slot]))

    # --- missing PHYSICAL points (template minus present) ---------------------
    missing_keys = sorted(expected_nodes - set(records_by_key))
    partially_deleted = sorted(
        rid for rid, k in missing_record_key.items() if k in records_by_key)

    # --- struts: resolve every endpoint (surviving id or reconstructed one) ---
    full_id_to_key = dict(id_to_key)
    full_id_to_key.update(missing_record_key)
    present_pairs, dangling_refs = {}, []
    for s in struts:
        a, b = s["junction0"], s["junction1"]
        if a not in id_to_key or b not in id_to_key:
            dangling_refs.append(s["id"])
        pair = (min(full_id_to_key[a], full_id_to_key[b]),
                max(full_id_to_key[a], full_id_to_key[b]))
        present_pairs[pair] = s["id"]

    missing_pairs = sorted(expected_edges - set(present_pairs))        # record gone
    missing_key_set = set(missing_keys)
    anchorless_pairs = sorted(                                          # record kept,
        p for p in present_pairs if p[0] in missing_key_set or p[1] in missing_key_set)

    # --- unit cells that reference strut ids that no longer exist -------------
    strut_ids = {s["id"] for s in struts}
    cells_with_dangling = sorted(
        c["id"] for c in cells if any(sid not in strut_ids for sid in c["struts"]))

    unit_cell_audit = audit_unit_cells(graph)

    return {
        "B": B, "fit_residual": resid, "n_cells": n_cells,
        "cell_voxels": float(np.mean(np.linalg.norm(B[:3], axis=1))),
        "expected_nodes": expected_nodes, "expected_edges": expected_edges,
        "records_by_key": dict(records_by_key), "id_to_key": id_to_key,
        "slot_offset": slot_offset, "slot_consistent": slot_consistent,
        "missing_record_ids": missing_record_ids,
        "missing_record_key": missing_record_key,
        "missing_keys": missing_keys,
        "partially_deleted_record_ids": partially_deleted,
        "present_pairs": present_pairs,
        "missing_pairs": missing_pairs,
        "anchorless_pairs": anchorless_pairs,
        "dangling_strut_ids": sorted(dangling_refs),
        "cells_with_dangling_strut_refs": cells_with_dangling,
        "unit_cell_audit": unit_cell_audit,
    }


def audit_unit_cells(graph):
    """Self-contained integrity audit of the unit_cells section (the THIRD
    top-level array -- junctions and struts are audited above; this is the
    "other thing").  Uses only the graph passed in, no ideal file needed.

    A plain record-count comparison (729 == 729) can miss two real defect
    shapes:
      1. GRID COMPLETENESS -- a cell could be duplicated while a different
         cell's (i,j,k) slot goes missing, leaving the total count unchanged.
      2. STRUT-LIST INTEGRITY -- a cell's "struts" id list could be silently
         shortened (entries spliced out) WITHOUT deleting the underlying
         strut record, which is invisible to the id-gap/template checks
         above since those only look at strut RECORDS, not cell membership
         lists.  Expected list length is learned per macro-block role
         (corner/edge/face/interior of the whole NxNxN block of cells --
         the same corner/edge/face/interior idea as the node taxonomy,
         applied one level up to the cells grid) via majority vote among
         survivors, so no ideal file is required to spot an outlier.
    """
    cells = graph["unit_cells"]
    cell_idx = {c["id"]: tuple(c["indices"]) for c in cells}
    n = max(max(v) for v in cell_idx.values()) + 1 if cell_idx else 0

    expected_combos = set(itertools.product(range(n), repeat=3))
    actual_combos = list(cell_idx.values())
    duplicate_combos = sorted(c for c, cnt in Counter(actual_combos).items() if cnt > 1)
    missing_combos = sorted(expected_combos - set(actual_combos))
    grid_complete = (not duplicate_combos and not missing_combos
                     and len(cell_idx) == n ** 3)

    def role(ijk):
        # Convention observed in the data: a shared edge between this cell and
        # its neighbor at index+1 along an axis is stored on the LOWER-index
        # cell, so only being AT THE MAX index (no "next" neighbor to hand the
        # edge to) inflates a cell's own strut-list length; being at index 0
        # is not special (it still always has a next neighbor along that axis
        # since n > 1).
        at_max = sum(c == n - 1 for c in ijk)
        return at_max

    by_role = defaultdict(list)
    for c in cells:
        by_role[role(tuple(c["indices"]))].append(len(c["struts"]))
    expected_len = {r: Counter(lens).most_common(1)[0][0] for r, lens in by_role.items()}
    length_outliers = sorted(
        c["id"] for c in cells
        if len(c["struts"]) != expected_len[role(tuple(c["indices"]))])

    return {
        "n_cells": n,
        "grid_complete": grid_complete,
        "duplicate_combos": duplicate_combos,
        "missing_combos": missing_combos,
        "role_expected_length": expected_len,
        "length_outlier_cell_ids": length_outliers,
    }


# ===========================================================================
# Ground-truth validation -- ONLY for scoring the detector, never for detecting
# ===========================================================================
def validate(det, ideal, damaged):
    ideal_j = {j["id"]: j for j in ideal["junctions"]}
    ideal_s = {s["id"]: s for s in ideal["struts"]}
    dam_j = {j["id"]: j for j in damaged["junctions"]}
    dam_s = {s["id"]: s for s in damaged["struts"]}

    removed_j = sorted(set(ideal_j) - set(dam_j))
    removed_s = sorted(set(ideal_s) - set(dam_s))

    # Any surviving record silently modified?  (defects should be deletions only)
    mutated_j = [i for i in dam_j if dam_j[i] != ideal_j.get(i)]
    mutated_s = [i for i in dam_s if dam_s[i] != ideal_s.get(i)]

    # Globalize ideal record indices exactly like detect() does (indices are
    # cell-local; the record id encodes the parent cell).
    ideal_cell_idx = {c["id"]: tuple(c["indices"]) for c in ideal["unit_cells"]}
    ideal_id_to_key = {
        i: tuple(2 * c + o for c, o in
                 zip(ideal_cell_idx[i // RECORDS_PER_CELL], key_of(j["indices"])))
        for i, j in ideal_j.items()}

    # Physical nodes whose ideal records were ALL deleted
    ideal_records_by_key = defaultdict(set)
    for i, k in ideal_id_to_key.items():
        ideal_records_by_key[k].add(i)
    removed_set = set(removed_j)
    truth_missing_keys = sorted(
        k for k, ids in ideal_records_by_key.items() if ids <= removed_set)
    truth_missing_pairs = sorted(
        (min(ideal_id_to_key[ideal_s[i]["junction0"]], ideal_id_to_key[ideal_s[i]["junction1"]]),
         max(ideal_id_to_key[ideal_s[i]["junction0"]], ideal_id_to_key[ideal_s[i]["junction1"]]))
        for i in removed_s)

    def prf(found, truth):
        found, truth = set(found), set(truth)
        tp = len(found & truth)
        precision = tp / len(found) if found else 1.0
        recall = tp / len(truth) if truth else 1.0
        return precision, recall

    point_p, point_r = prf(det["missing_keys"], truth_missing_keys)
    record_p, record_r = prf(det["missing_record_ids"], removed_j)
    strut_p, strut_r = prf(det["missing_pairs"], truth_missing_pairs)

    return {
        "removed_junction_record_ids": removed_j,
        "removed_strut_record_ids": removed_s,
        "mutated_junction_ids": mutated_j, "mutated_strut_ids": mutated_s,
        "truth_missing_keys": truth_missing_keys,
        "truth_missing_pairs": truth_missing_pairs,
        "metrics": {
            "point_precision": point_p, "point_recall": point_r,
            "record_precision": record_p, "record_recall": record_r,
            "strut_precision": strut_p, "strut_recall": strut_r,
        },
    }


# ===========================================================================
# Outputs
# ===========================================================================
def write_outputs(det, val, parse_mode, syntax_error):
    os.makedirs(OUT, exist_ok=True)
    B = det["B"]
    miss_pos = key_to_position(det["missing_keys"], B)

    # ---- missing points CSV --------------------------------------------------
    points_csv = os.path.join(OUT, "defect_missing_points.csv")
    with open(points_csv, "w") as f:
        f.write("lat_i,lat_j,lat_k,vox_x,vox_y,vox_z,deleted_record_ids\n")
        for k, p in zip(det["missing_keys"], miss_pos):
            rids = [r for r, kk in det["missing_record_key"].items() if kk == k]
            f.write(f"{k[0]/2},{k[1]/2},{k[2]/2},"
                    f"{p[0]:.3f},{p[1]:.3f},{p[2]:.3f},"
                    f"{';'.join(map(str, sorted(rids)))}\n")

    # ---- missing struts CSV ----------------------------------------------------
    struts_csv = os.path.join(OUT, "defect_missing_struts.csv")
    with open(struts_csv, "w") as f:
        f.write("kind,lat0_i,lat0_j,lat0_k,lat1_i,lat1_j,lat1_k,"
                "x0,y0,z0,x1,y1,z1\n")
        for kind, pairs in (("record_deleted", det["missing_pairs"]),
                            ("anchor_missing", det["anchorless_pairs"])):
            for a, b in pairs:
                pa, pb = key_to_position([a, b], B)
                f.write(f"{kind},{a[0]/2},{a[1]/2},{a[2]/2},"
                        f"{b[0]/2},{b[1]/2},{b[2]/2},"
                        f"{pa[0]:.3f},{pa[1]:.3f},{pa[2]:.3f},"
                        f"{pb[0]:.3f},{pb[1]:.3f},{pb[2]:.3f}\n")

    # ---- machine-readable report (feeds the napari visualization later) -------
    report = {
        "defective_file": DAMAGED, "reference_file": IDEAL,
        "parse_mode": parse_mode,
        "syntax_error": syntax_error,
        "grid": f"{det['n_cells']}x{det['n_cells']}x{det['n_cells']}",
        "cell_voxels": det["cell_voxels"],
        "affine_fit_residual_vox": det["fit_residual"],
        "counts": {
            "surviving_junction_records": len(det["id_to_key"]),
            "deleted_junction_records": len(det["missing_record_ids"]),
            "missing_physical_points": len(det["missing_keys"]),
            "partially_deleted_records": len(det["partially_deleted_record_ids"]),
            "missing_strut_records": len(det["missing_pairs"]),
            "anchorless_struts": len(det["anchorless_pairs"]),
            "dangling_strut_endpoint_refs": len(det["dangling_strut_ids"]),
            "cells_with_dangling_strut_refs": len(det["cells_with_dangling_strut_refs"]),
        },
        "unit_cells_audit": det["unit_cell_audit"],
        "missing_points": [
            {"lattice": [c / 2 for c in k], "position_xyz_vox": p.tolist()}
            for k, p in zip(det["missing_keys"], miss_pos)],
        "deleted_record_ids": det["missing_record_ids"],
        "missing_struts": [
            {"kind": kind, "lattice0": [c / 2 for c in a], "lattice1": [c / 2 for c in b],
             "pos0": key_to_position([a], det["B"])[0].tolist(),
             "pos1": key_to_position([b], det["B"])[0].tolist()}
            for kind, pairs in (("record_deleted", det["missing_pairs"]),
                                ("anchor_missing", det["anchorless_pairs"]))
            for a, b in pairs],
        "validation": {
            "removed_junction_record_ids": val["removed_junction_record_ids"],
            "removed_strut_record_ids": val["removed_strut_record_ids"],
            "mutated_records": len(val["mutated_junction_ids"]) + len(val["mutated_strut_ids"]),
            "metrics": val["metrics"],
        },
    }
    report_path = os.path.join(OUT, "defect_report.json")
    write_json(report_path, report)
    return report_path, points_csv, struts_csv


def render_figure(det):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    B = det["B"]
    present_pairs = det["present_pairs"]
    missing_keys = det["missing_keys"]
    miss_pos = key_to_position(missing_keys, B)
    anchorless = set(det["anchorless_pairs"])
    deleted = set(det["missing_pairs"])

    fig = plt.figure(figsize=(17, 8))
    ax3 = fig.add_subplot(121, projection="3d")
    ax2 = fig.add_subplot(122)

    healthy = [p for p in present_pairs if p not in anchorless]
    for pair_set, color, lw, alpha in ((healthy, "lightgray", 0.3, 0.25),
                                       (sorted(anchorless), "orange", 1.6, 0.95),
                                       (sorted(deleted), "red", 2.0, 0.95)):
        for a, b in pair_set:
            pa, pb = key_to_position([a, b], B)
            ax3.plot([pa[0], pb[0]], [pa[1], pb[1]], [pa[2], pb[2]],
                     color=color, lw=lw, alpha=alpha)
            ax2.plot([pa[0], pb[0]], [pa[1], pb[1]], color=color, lw=lw, alpha=alpha)
    if len(miss_pos):
        ax3.scatter(miss_pos[:, 0], miss_pos[:, 1], miss_pos[:, 2],  # type: ignore[arg-type]
                    color="red", s=60, marker="x", depthshade=False)
        ax2.scatter(miss_pos[:, 0], miss_pos[:, 1], color="red", s=80, marker="x",
                    zorder=5)
    ax3.set_title("3D: red X = missing points, orange = anchor-less struts")
    ax3.view_init(elev=22, azim=40)
    ax2.set_title("XY projection")
    ax2.invert_yaxis()
    ax2.set_aspect("equal")
    fig.suptitle(
        f"Defects found in damaged JSON: {len(missing_keys)} missing points, "
        f"{len(deleted)} deleted struts, {len(anchorless)} anchor-less struts",
        fontsize=14)
    plt.tight_layout()
    fig_path = os.path.join(OUT, "defect_overview.png")
    plt.savefig(fig_path, dpi=120, bbox_inches="tight")
    plt.close()
    return fig_path


# ===========================================================================
# Final checks
# ===========================================================================
def run_checks(det, val, ideal, damaged, ideal_text, artifacts, parse_mode, syntax_error):
    checks = []

    def check(name, passed, detail):
        checks.append((name, bool(passed), detail))

    # 1. Inputs and parse modes
    check("inputs & parse mode",
          os.path.getsize(IDEAL) > 1e6 and os.path.getsize(DAMAGED) > 1e6
          and parse_mode in ("strict", "tolerant"),
          f"ideal=strict, damaged={parse_mode} (syntax error: {syntax_error})")

    # 2. Tolerant extractor reproduces the strict parse on the IDEAL file
    tol = tolerant_extract(ideal_text)
    same = (
        len(tol["junctions"]) == len(ideal["junctions"])
        and len(tol["struts"]) == len(ideal["struts"])
        and len(tol["unit_cells"]) == len(ideal["unit_cells"])
        and all(a == b for a, b in zip(tol["junctions"], ideal["junctions"]))
        and all(a == b for a, b in zip(tol["struts"], ideal["struts"]))
        and all(a == b for a, b in zip(tol["unit_cells"], ideal["unit_cells"]))
    )
    check("regex extractor fidelity (vs strict parse of ideal)", same,
          f"{len(tol['junctions'])}/{len(tol['struts'])}/{len(tol['unit_cells'])} records identical")

    # 3. Junction-id arithmetic (id = cell*14 + slot) holds everywhere:
    #    every slot has ONE local offset across all survivors, and the 14
    #    learned offsets are exactly the octet cell template (8 corners + 6
    #    face centers of the unit cube).
    canonical = set(cell_node_keys(0, 0, 0))
    ok3 = (det["slot_consistent"]
           and len(det["slot_offset"]) == RECORDS_PER_CELL
           and set(det["slot_offset"].values()) == canonical
           and all(j["id"] // RECORDS_PER_CELL < len(damaged["unit_cells"])
                   for j in damaged["junctions"]))
    check("id arithmetic id=cell*14+slot", ok3,
          f"{len(det['slot_offset'])} slots learned, single-offset={det['slot_consistent']}, "
          f"offsets == octet cell template: {set(det['slot_offset'].values()) == canonical}")

    # 4. Affine frame quality
    check("affine index->position fit", det["fit_residual"] < 0.01
          and abs(det["cell_voxels"] - 78.98) < 1.0,
          f"max residual {det['fit_residual']:.2e} vox, cell={det['cell_voxels']:.2f} vox")

    # 5. Template + zero false positives on the clean ideal file
    nodes, edges = det["expected_nodes"], det["expected_edges"]
    det_ideal = detect(ideal)
    check("template counts & clean run on ideal",
          len(nodes) == 3430 and len(edges) == 18468
          and not det_ideal["missing_keys"] and not det_ideal["missing_record_ids"]
          and not det_ideal["missing_pairs"] and not det_ideal["anchorless_pairs"],
          f"template {len(nodes)} nodes/{len(edges)} edges; ideal run: 0 defects")

    # 6. Conservation + finiteness + positions inside the lattice bbox
    miss_pos = key_to_position(det["missing_keys"], det["B"])
    ipos = np.array([j["position"] for j in ideal["junctions"]])
    lo, hi = ipos.min(0) - 5, ipos.max(0) + 5
    check("conservation & sane predicted positions",
          len(det["records_by_key"]) + len(det["missing_keys"]) == 3430
          and len(det["present_pairs"]) + len(det["missing_pairs"]) == 18468
          and np.isfinite(miss_pos).all()
          and ((miss_pos >= lo) & (miss_pos <= hi)).all(),
          f"{len(det['records_by_key'])}+{len(det['missing_keys'])}=3430 nodes, "
          f"{len(det['present_pairs'])}+{len(det['missing_pairs'])}=18468 struts")

    # 7. Independent detectors agree (id-gaps vs lattice template)
    keys_from_ids = {k for k in det["missing_record_key"].values()
                     if k not in det["records_by_key"]}
    dangle_ok = all(
        (s["junction0"] in det["missing_record_key"]) or (s["junction1"] in det["missing_record_key"])
        for s in damaged["struts"] if s["id"] in set(det["dangling_strut_ids"]))
    check("cross-detector agreement", keys_from_ids == set(det["missing_keys"]) and dangle_ok,
          f"id-gap keys == template keys ({len(keys_from_ids)}), "
          f"dangling refs all explained: {dangle_ok}")

    # 8. Ground truth: missing POINTS perfect
    m = val["metrics"]
    check("ground truth: points P=R=1",
          m["point_precision"] == 1.0 and m["point_recall"] == 1.0
          and m["record_precision"] == 1.0 and m["record_recall"] == 1.0,
          f"points P={m['point_precision']:.3f} R={m['point_recall']:.3f}, "
          f"records P={m['record_precision']:.3f} R={m['record_recall']:.3f}")

    # 9. Ground truth: struts perfect + damage is deletions-only
    check("ground truth: struts P=R=1, no mutations",
          m["strut_precision"] == 1.0 and m["strut_recall"] == 1.0
          and not val["mutated_junction_ids"] and not val["mutated_strut_ids"],
          f"struts P={m['strut_precision']:.3f} R={m['strut_recall']:.3f}, "
          f"mutated records: {len(val['mutated_junction_ids']) + len(val['mutated_strut_ids'])}")

    # 10. Artifacts on disk, consistent, round-trippable
    ok10, details = True, []
    for path in artifacts:
        ok10 &= os.path.exists(path) and os.path.getsize(path) > 0
        details.append(os.path.basename(path))
    with open(artifacts[0]) as f:
        rep = json.load(f)                       # round-trip
    n_csv = sum(1 for _ in open(artifacts[1])) - 1
    ok10 &= n_csv == rep["counts"]["missing_physical_points"] == len(det["missing_keys"])
    check("artifacts written & self-consistent", ok10,
          f"{', '.join(details)}; csv rows={n_csv}")

    # 11. unit_cells (the THIRD top-level array) audited directly: grid is a
    # complete non-duplicated coverage, no cell's strut-list length is an
    # outlier for its role, and the same audit is clean on the ideal file too
    # (rules out false positives from the role/majority-vote logic itself).
    ua = det["unit_cell_audit"]
    ua_ideal = audit_unit_cells(ideal)
    check("unit_cells: grid completeness & strut-list integrity",
          ua["grid_complete"] and not ua["length_outlier_cell_ids"]
          and ua_ideal["grid_complete"] and not ua_ideal["length_outlier_cell_ids"],
          f"damaged: {ua['n_cells']}^3 grid complete={ua['grid_complete']}, "
          f"length outliers={len(ua['length_outlier_cell_ids'])}; "
          f"ideal: grid complete={ua_ideal['grid_complete']}, "
          f"length outliers={len(ua_ideal['length_outlier_cell_ids'])}")

    return checks


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Detect missing junctions/struts in a damaged lattice JSON.")
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("DEFECT DETECTION -- damaged registered lattice JSON")
    print("=" * 70)

    with open(IDEAL, encoding="utf-8") as f:
        ideal_text = f.read()
    ideal = load_json(IDEAL)

    damaged, mode, err = load_graph(DAMAGED)
    print(f"damaged file parse : {mode}" + (f"  (JSON broken at {err})" if err else ""))
    print(f"records surviving  : {len(damaged['junctions'])} junctions, "
          f"{len(damaged['struts'])} struts, {len(damaged['unit_cells'])} cells")

    det = detect(damaged)
    print(f"\nlattice frame      : {det['n_cells']}^3 cells, "
          f"cell={det['cell_voxels']:.2f} vox, fit residual {det['fit_residual']:.2e}")
    print(f"deleted records    : {len(det['missing_record_ids'])} junction records "
          f"{det['missing_record_ids']}")
    print(f"MISSING POINTS     : {len(det['missing_keys'])} physical junctions")
    shown = det["missing_keys"][:40]
    for k, p in zip(shown, key_to_position(shown, det["B"])):
        print(f"   lattice ({k[0]/2:>4},{k[1]/2:>4},{k[2]/2:>4})  "
              f"voxel ({p[0]:7.1f},{p[1]:7.1f},{p[2]:7.1f})")
    if len(det["missing_keys"]) > 40:
        print(f"   ... and {len(det['missing_keys']) - 40} more (see CSV)")
    print(f"partially deleted  : {len(det['partially_deleted_record_ids'])} records "
          f"(node survives elsewhere) {det['partially_deleted_record_ids']}")
    print(f"MISSING STRUTS     : {len(det['missing_pairs'])} strut records deleted")
    print(f"anchor-less struts : {len(det['anchorless_pairs'])} (record present, "
          f"endpoint physically missing)")
    print(f"dangling strut refs: {len(det['dangling_strut_ids'])}, "
          f"cells w/ dangling strut ids: {len(det['cells_with_dangling_strut_refs'])}")
    ua = det["unit_cell_audit"]
    print(f"unit_cells audit   : grid complete={ua['grid_complete']} "
          f"(dup={len(ua['duplicate_combos'])}, missing={len(ua['missing_combos'])}), "
          f"strut-list length outliers={len(ua['length_outlier_cell_ids'])} "
          f"(expected/role {ua['role_expected_length']})")

    val = validate(det, ideal, damaged)
    mm = val["metrics"]
    print(f"\nvalidation vs ideal: {len(val['removed_junction_record_ids'])} junction "
          f"records and {len(val['removed_strut_record_ids'])} strut records were removed")
    print(f"detector metrics   : points P={mm['point_precision']:.3f}/R={mm['point_recall']:.3f}  "
          f"records P={mm['record_precision']:.3f}/R={mm['record_recall']:.3f}  "
          f"struts P={mm['strut_precision']:.3f}/R={mm['strut_recall']:.3f}")

    artifacts = list(write_outputs(det, val, mode, err))
    if not args.no_figure:
        artifacts.append(render_figure(det))
    print("\noutputs            : " + ", ".join(os.path.basename(a) for a in artifacts))

    checks = run_checks(det, val, ideal, damaged, ideal_text, artifacts, mode, err)
    print("\n" + "=" * 70)
    print(f"FINAL CHECKS ({len(checks)})")
    print("=" * 70)
    failed = 0
    for n, (name, passed, detail) in enumerate(checks, 1):
        status = "PASS" if passed else "FAIL"
        failed += not passed
        print(f"CHECK {n:>2} [{status}] {name}\n          {detail}")
    print("=" * 70)
    print(f"{len(checks) - failed}/{len(checks)} checks passed"
          + ("" if not failed else f"  <-- {failed} FAILED"))
    return failed


if __name__ == "__main__":
    sys.exit(main())
