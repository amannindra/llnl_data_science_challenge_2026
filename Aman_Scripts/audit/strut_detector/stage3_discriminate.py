#!/usr/bin/env python3
"""Stage 3: does the CT actually contain material ON the removed centerlines?

Compares, for the 94 CAD-removed struts and 400 present struts:
  - core occupancy: fraction of axial stations whose CENTER voxel >= threshold
  - r<=1 occupancy, r<=2 occupancy
  - the detector's own r<=5.67 disk criterion (>=9 of ~101 voxels)

If core occupancy separates the two populations but the detector's criterion does
not, the detector's sampling corridor is too permissive.
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

from Components.asset_io import read_tiff
from Components.paths import data_path

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)
cache = np.load(TMP / "cad_map.npz")
strut_ids = cache["strut_ids"]
e0, e1 = cache["endpoint0"], cache["endpoint1"]
removed_ids = set(int(v) for v in cache["removed_ids"])

THRESH = 40054.0
missing = data_path("missing_struts")
volume = read_tiff(
    missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
    mmap_mode="r",
)
shape_xyz = np.asarray(volume.shape[::-1])


def ball_offsets(radius):
    e = int(np.ceil(radius))
    a = np.arange(-e, e + 1)
    zz, yy, xx = np.meshgrid(a, a, a, indexing="ij")
    m = xx * xx + yy * yy + zz * zz <= radius * radius + 1e-9
    return np.stack((xx[m], yy[m], zz[m]), axis=1)


OFFSETS = {r: ball_offsets(r) for r in (0.0, 1.0, 2.0, 3.0)}


def occupancy(idx):
    a, b = np.asarray(e0[idx]), np.asarray(e1[idx])
    length = float(np.linalg.norm(b - a))
    frac = 0.10 + 0.80 * (np.arange(45) + 0.5) / 45
    centers = a + frac[:, None] * (b - a)
    base = np.floor(centers + 0.5).astype(np.int64)
    out = {}
    for r, off in OFFSETS.items():
        cand = base[:, None, :] + off[None, :, :]
        ok = np.all((cand >= 0) & (cand < shape_xyz), axis=2)
        hit = np.zeros(len(centers), dtype=bool)
        for i in range(len(centers)):
            sel = cand[i, ok[i]]
            if sel.size:
                hit[i] = np.any(volume[sel[:, 2], sel[:, 1], sel[:, 0]] >= THRESH)
        out[r] = float(np.mean(hit))
    # mean intensity right on the centerline
    ok0 = np.all((base >= 0) & (base < shape_xyz), axis=1)
    vals = volume[base[ok0][:, 2], base[ok0][:, 1], base[ok0][:, 0]].astype(float)
    out["mean_core_intensity"] = float(np.mean(vals)) if vals.size else float("nan")
    out["length"] = length
    return out


removed_mask = np.array([int(i) in removed_ids for i in strut_ids])
control_index = np.flatnonzero(removed_mask)
rng = np.random.default_rng(20260728)
sample_index = np.sort(rng.choice(np.flatnonzero(~removed_mask), size=400, replace=False))

res = {}
for name, indices in (("control", control_index), ("sample", sample_index)):
    rows = []
    for n, idx in enumerate(indices, 1):
        o = occupancy(idx)
        o["strut_id"] = int(strut_ids[idx])
        rows.append(o)
        if n % 100 == 0:
            print(f"  {name} {n}/{len(indices)}", flush=True)
    res[name] = rows

(TMP / "discriminate.json").write_text(json.dumps(res, indent=1))

print(f"\nthreshold={THRESH:.0f}  (n_control=94, n_sample=400)")
print(f"{'radius':>22} | {'CAD-REMOVED median':>19} | {'PRESENT median':>15}")
for r in (0.0, 1.0, 2.0, 3.0):
    c = np.median([x[r] for x in res["control"]])
    s = np.median([x[r] for x in res["sample"]])
    print(f"  occupancy r<={r:>4.1f} vox | {c:>19.3f} | {s:>15.3f}")
for key in ("mean_core_intensity", "length"):
    c = np.median([x[key] for x in res["control"]])
    s = np.median([x[key] for x in res["sample"]])
    print(f"{key:>22} | {c:>19.1f} | {s:>15.1f}")

c0 = np.array([x[0.0] for x in res["control"]])
s0 = np.array([x[0.0] for x in res["sample"]])
print(f"\ncore (r=0) occupancy >= 0.8:  removed {np.mean(c0>=0.8):.1%}   present {np.mean(s0>=0.8):.1%}")
print(f"core (r=0) occupancy <= 0.2:  removed {np.mean(c0<=0.2):.1%}   present {np.mean(s0<=0.2):.1%}")
