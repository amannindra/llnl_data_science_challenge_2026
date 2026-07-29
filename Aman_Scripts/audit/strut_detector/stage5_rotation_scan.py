#!/usr/bin/env python3
"""Stage 5: is the hardcoded STL rotation '+z+x+y' identifiable?

The pipeline picks one of the 24 proper cube rotations by hardcoded constant and
never tests the other 23.  An octet lattice in a cube is highly symmetric, so
several rotations may map the mesh onto the graph equally well while PERMUTING
which graph ID each physical strut receives.

For every rotation we recompute which strut IDs 0.5.stl omits, then ask the CT
which candidate set actually has no material.
"""
from pathlib import Path
import json
import os
import sys
import numpy as np

SCRIPTS = Path(os.environ.get("DSC_SCRIPTS_DIR", Path(__file__).resolve().parents[2]))
if not (SCRIPTS / "Components" / "strut_pipeline.py").exists():
    raise SystemExit(
        f"{SCRIPTS} has no Components/strut_pipeline.py. The audited modules are\n"
        "not yet committed to main; point DSC_SCRIPTS_DIR at the working checkout:\n"
        "  DSC_SCRIPTS_DIR=/path/to/repo/Aman_Scripts conda run -n DSC python " + __file__
    )
sys.path.insert(0, str(SCRIPTS))

from scipy.spatial import cKDTree

from Components.asset_io import inspect_stl
from Components.coordinates import compose_transforms
from Components.lattice_graph import load_lattice_graph
from Components.paths import data_path
from Components.cad_strut_mapping import build_registered_centerline_atlas
from tif2stl.registration import (
    paired_junction_positions, proper_cube_rotations, similarity_transform,
    stl_to_design_matrix,
)
from tif2stl.stl_geometry import read_stl_triangles

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)
missing = data_path("missing_struts")
stl05 = missing / "stls" / "0.5.stl"
design_json = missing / "octet_truss_9x9x9.json"
registered_json = missing / "registered_jsons" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"

design_graph = load_lattice_graph(design_json)
registered_graph = load_lattice_graph(registered_json)
dp, rp = paired_junction_positions(design_graph, registered_graph)
fit = similarity_transform(dp, rp)
meta = inspect_stl(stl05)
lower = np.asarray(meta.bounding_box_min, float)
upper = np.asarray(meta.bounding_box_max, float)
stl_center = (lower + upper) / 2.0
design_center = np.repeat(18.0 / 2.0, 3)

atlas = build_registered_centerline_atlas(registered_graph, axial_bins=45)
centers_ct = np.ascontiguousarray(atlas["centers_xyz"].reshape(-1, 3))
strut_ids = atlas["strut_ids"]
n_struts, n_bins = atlas["centers_xyz"].shape[:2]

# --- stream the specimen mesh once, in its own mm frame ---------------------
cache = TMP / "stl05_centroids.npy"
if cache.exists():
    pts_mm = np.load(cache)
else:
    chunks = []
    for tri in read_stl_triangles(stl05, chunk_faces=200_000):
        chunks.append(tri.mean(axis=1).astype(np.float32))
    pts_mm = np.concatenate(chunks, axis=0)
    np.save(cache, pts_mm)
print("specimen triangle centroids:", pts_mm.shape)
tree = cKDTree(pts_mm, balanced_tree=False, compact_nodes=False)

results = {}
for name, rot in sorted(dict(proper_cube_rotations()).items()):
    stl_to_design = stl_to_design_matrix(
        mm_per_design_unit=2.28,
        stl_center_xyz=tuple(stl_center),
        design_center_xyz=tuple(design_center),
        rotation=rot,
    )
    matrix = compose_transforms(stl_to_design, fit.matrix)
    inverse = np.linalg.inv(matrix)
    stations_mm = (centers_ct @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
    vox_per_mm = float(np.linalg.norm(matrix[:3, 0]))
    radius_mm = 9.0 / vox_per_mm
    distance, _ = tree.query(stations_mm, k=1, distance_upper_bound=radius_mm, workers=-1)
    covered = np.isfinite(distance).reshape(n_struts, n_bins).mean(axis=1)
    absent = covered <= 0.20
    results[name] = {
        "covered_median": float(np.median(covered)),
        "fully_covered_struts": int(np.sum(covered >= 0.8)),
        "absent_count": int(np.sum(absent)),
        "absent_ids": [int(v) for v in strut_ids[absent]],
    }
    print(f"{name:>8}  median_cov={np.median(covered):.3f}  "
          f"covered>=0.8: {np.sum(covered>=0.8):6d}/{n_struts}  absent: {np.sum(absent):5d}")

(TMP / "rotation_scan.json").write_text(json.dumps(results, indent=1))

print("\n--- rotations that fit the graph well (>=95% struts covered) ---")
good = {k: v for k, v in results.items() if v["fully_covered_struts"] >= 0.95 * n_struts}
for k, v in sorted(good.items()):
    print(f"  {k}: absent={v['absent_count']}")
if len(good) > 1:
    keys = sorted(good)
    base = set(good[keys[0]]["absent_ids"])
    for k in keys[1:]:
        other = set(good[k]["absent_ids"])
        print(f"  overlap {keys[0]} vs {k}: {len(base & other)} shared of {len(base)}/{len(other)}")
