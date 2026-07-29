#!/usr/bin/env python3
"""Stage 6: let the CT arbitrate between the 24 candidate rotations.

For each proper cube rotation we recompute the set of graph IDs that 0.5.stl
omits, then measure the mean raw CT intensity in a radius-2 cylinder around each
of those centerlines.  A strut that was really removed before printing must be
dark.  The correct rotation is the one whose omitted set is dark in CT.
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

from Components.asset_io import inspect_stl, read_tiff
from Components.coordinates import compose_transforms
from Components.lattice_graph import load_lattice_graph
from Components.paths import data_path
from Components.cad_strut_mapping import build_registered_centerline_atlas
from tif2stl.registration import (
    paired_junction_positions, proper_cube_rotations, similarity_transform,
    stl_to_design_matrix,
)

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)
missing = data_path("missing_struts")
registered_json = missing / "registered_jsons" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"

design_graph = load_lattice_graph(missing / "octet_truss_9x9x9.json")
registered_graph = load_lattice_graph(registered_json)
dp, rp = paired_junction_positions(design_graph, registered_graph)
fit = similarity_transform(dp, rp)
meta = inspect_stl(missing / "stls" / "0.5.stl")
stl_center = (np.asarray(meta.bounding_box_min, float) + np.asarray(meta.bounding_box_max, float)) / 2.0
design_center = np.repeat(9.0, 3)

atlas = build_registered_centerline_atlas(registered_graph, axial_bins=45)
centers_ct = np.ascontiguousarray(atlas["centers_xyz"].reshape(-1, 3))
strut_ids = atlas["strut_ids"]
n_struts, n_bins = atlas["centers_xyz"].shape[:2]

pts_mm = np.load(TMP / "stl05_centroids.npy")
tree = cKDTree(pts_mm, balanced_tree=False, compact_nodes=False)

volume = read_tiff(
    missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
    mmap_mode="r",
)
shape_xyz = np.asarray(volume.shape[::-1])
e0, e1 = atlas["endpoint0_xyz"], atlas["endpoint1_xyz"]

a = np.arange(-2, 3)
zz, yy, xx = np.meshgrid(a, a, a, indexing="ij")
m = xx * xx + yy * yy + zz * zz <= 4 + 1e-9
BALL = np.stack((xx[m], yy[m], zz[m]), axis=1)


def mean_core_intensity(idx):
    frac = 0.10 + 0.80 * (np.arange(45) + 0.5) / 45
    centers = e0[idx] + frac[:, None] * (e1[idx] - e0[idx])
    base = np.floor(centers + 0.5).astype(np.int64)
    cand = (base[:, None, :] + BALL[None, :, :]).reshape(-1, 3)
    ok = np.all((cand >= 0) & (cand < shape_xyz), axis=1)
    sel = cand[ok]
    if not sel.size:
        return float("nan")
    return float(np.mean(volume[sel[:, 2], sel[:, 1], sel[:, 0]].astype(np.float64)))


rng = np.random.default_rng(7)
baseline_idx = rng.choice(n_struts, size=200, replace=False)
baseline = np.array([mean_core_intensity(i) for i in baseline_idx])
print(f"BASELINE 200 random struts: mean core intensity median={np.median(baseline):.0f} "
      f"p10={np.percentile(baseline,10):.0f} p90={np.percentile(baseline,90):.0f}\n")

rows = {}
for name, rot in sorted(dict(proper_cube_rotations()).items()):
    stl_to_design = stl_to_design_matrix(
        mm_per_design_unit=2.28, stl_center_xyz=tuple(stl_center),
        design_center_xyz=tuple(design_center), rotation=rot,
    )
    matrix = compose_transforms(stl_to_design, fit.matrix)
    inverse = np.linalg.inv(matrix)
    stations_mm = (centers_ct @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
    radius_mm = 9.0 / float(np.linalg.norm(matrix[:3, 0]))
    distance, _ = tree.query(stations_mm, k=1, distance_upper_bound=radius_mm, workers=-1)
    covered = np.isfinite(distance).reshape(n_struts, n_bins).mean(axis=1)
    absent = np.flatnonzero(covered < 0.8)
    intensities = np.array([mean_core_intensity(i) for i in absent])
    rows[name] = {
        "absent_count": int(absent.size),
        "absent_ids": [int(v) for v in strut_ids[absent]],
        "median_core_intensity": float(np.median(intensities)),
        "fraction_darker_than_baseline_p10": float(
            np.mean(intensities < np.percentile(baseline, 10))
        ),
    }
    flag = "  <== pipeline" if name == "+z+x+y" else ""
    print(f"{name:>8}  omitted={absent.size:3d}  median_core_CT={np.median(intensities):8.0f}  "
          f"frac_dark={rows[name]['fraction_darker_than_baseline_p10']:.2f}{flag}")

(TMP / "arbiter.json").write_text(json.dumps(rows, indent=1))
best = min(rows.items(), key=lambda kv: kv[1]["median_core_intensity"])
print(f"\ndarkest omitted set: {best[0]}  median_core_CT={best[1]['median_core_intensity']:.0f}")
print(f"pipeline choice   : +z+x+y  median_core_CT={rows['+z+x+y']['median_core_intensity']:.0f}")
print(f"baseline (present): median_core_CT={np.median(baseline):.0f}")
