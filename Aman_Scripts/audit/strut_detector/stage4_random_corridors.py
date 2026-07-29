#!/usr/bin/env python3
"""Stage 4: specificity floor.

The detector calls an axial bin "realized" when >= minimum_material_samples
voxels inside a radius-5.67 disk (~101 voxels) exceed the threshold.  The
specimen's global foreground fraction at Otsu is ~11.3%, i.e. ~11.4 of those 101
voxels are material ON AVERAGE ANYWHERE INSIDE THE PART.

So: feed the detector corridors that correspond to NO strut at all -- random
segments of true strut length, placed inside the lattice interior.  A sound
detector must flag essentially all of them.
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
from Components.strut_comparison import compare_strut_local

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)
cache = np.load(TMP / "cad_map.npz")
e0, e1 = cache["endpoint0"], cache["endpoint1"]
scale = float(cache["scale"][0])
expected_radius = 0.5 * 0.424 / 2.28 * scale

missing = data_path("missing_struts")
volume = read_tiff(
    missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
    mmap_mode="r",
)
EMPTY = np.zeros((0, 3), dtype=np.float64)
THRESH = 40054.0

# Interior of the lattice, from the registered junction cloud.
allpts = np.concatenate([e0, e1], axis=0)
lo = allpts.min(axis=0) + 60.0
hi = allpts.max(axis=0) - 60.0
median_length = float(np.median(np.linalg.norm(e1 - e0, axis=1)))
print("lattice interior box xyz", lo.round(1), hi.round(1), "strut length", round(median_length, 2))

# --- measured base rate of material inside the interior box -----------------
sub = volume[int(lo[2]):int(hi[2]), int(lo[1]):int(hi[1]), int(lo[0]):int(hi[0])]
frac = float(np.mean(sub[::3, ::3, ::3] >= THRESH))
print(f"interior foreground fraction at threshold {THRESH:.0f}: {frac:.4%}")
disk_voxels = 101
print(f"expected material voxels in a radius-5.67 disk by chance: {frac*disk_voxels:.1f}")
print(f"detector requires >= 9 to call the bin realized\n")

rng = np.random.default_rng(4242)
rows = []
N = 250
for n in range(N):
    start = lo + rng.random(3) * (hi - lo)
    direction = rng.normal(size=3)
    direction /= np.linalg.norm(direction)
    end = start + direction * median_length
    if np.any(end < lo) or np.any(end > hi):
        continue
    res = compare_strut_local(
        volume, start, end, EMPTY,
        expected_present_override=True,
        expected_radius_voxels=expected_radius,
    )
    rows.append({
        "has_error": res["has_error"],
        "realized": res.get("realized_axial_fraction"),
        "reason": res["decision_reason"],
    })
    if (n + 1) % 50 == 0:
        print(f"  random corridor {n+1}/{N}", flush=True)

(TMP / "random_corridors.json").write_text(json.dumps(rows, indent=1))
t = sum(r["has_error"] is True for r in rows)
f = sum(r["has_error"] is False for r in rows)
u = sum(r["has_error"] is None for r in rows)
print(f"\nRANDOM NON-STRUT CORRIDORS: n={len(rows)}  flagged_error={t}  "
      f"called_HEALTHY={f}  undecided={u}")
print(f"false 'healthy' rate on pure noise geometry: {f/max(len(rows),1):.1%}")
vals = sorted(r["realized"] for r in rows if r["realized"] is not None)
if vals:
    print("realized_axial_fraction deciles:",
          [round(v, 2) for v in np.percentile(vals, [10, 25, 50, 75, 90])])
