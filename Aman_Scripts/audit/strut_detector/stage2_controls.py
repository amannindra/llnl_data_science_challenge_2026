#!/usr/bin/env python3
"""Stage 2: positive/negative controls for the CT side of the detector.

Positive control: the 94 struts absent from 0.5.stl were removed in CAD before
printing, so the CT volume genuinely has no material there.  Running the CT
comparator on those centerlines with expected_present_override=True must return
has_error=True.  Anything else is a proven false negative.

Negative control: a deterministic spatially-stratified random sample of struts
that ARE present in 0.5.stl.
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
strut_ids = cache["strut_ids"]
e0 = cache["endpoint0"]
e1 = cache["endpoint1"]
removed_ids = set(int(v) for v in cache["removed_ids"])
scale = float(cache["scale"][0])

expected_radius = 0.5 * 0.424 / 2.28 * scale
print("expected_radius_voxels", expected_radius)

missing = data_path("missing_struts")
tiff = missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
volume = read_tiff(tiff, mmap_mode="r")
print("volume", volume.shape, volume.dtype)

removed_mask = np.array([int(i) in removed_ids for i in strut_ids])
kept_index = np.flatnonzero(~removed_mask)
rng = np.random.default_rng(20260728)
sample_index = np.sort(rng.choice(kept_index, size=400, replace=False))
control_index = np.flatnonzero(removed_mask)

EMPTY = np.zeros((0, 3), dtype=np.float64)


def run(indices, label):
    rows = []
    for n, idx in enumerate(indices, start=1):
        res = compare_strut_local(
            volume,
            e0[idx],
            e1[idx],
            EMPTY,
            expected_present_override=True,
            expected_radius_voxels=expected_radius,
        )
        mid = (np.asarray(e0[idx]) + np.asarray(e1[idx])) / 2.0
        rows.append({
            "strut_id": int(strut_ids[idx]),
            "has_error": res["has_error"],
            "reason": res["decision_reason"],
            "realized": res.get("realized_axial_fraction"),
            "gap": res.get("longest_unrealized_gap_voxels"),
            "bridge": res.get("bridge_connected_26"),
            "agreement": res.get("perturbation_agreement"),
            "mid_xyz": [float(v) for v in mid],
        })
        if n % 50 == 0:
            print(f"  {label} {n}/{len(indices)}", flush=True)
    return rows


control = run(control_index, "control")
sample = run(sample_index, "sample")

out = TMP / "control_results.json"
out.write_text(json.dumps({"control": control, "sample": sample}, indent=1))


def summarize(rows, name):
    t = sum(r["has_error"] is True for r in rows)
    f = sum(r["has_error"] is False for r in rows)
    n = sum(r["has_error"] is None for r in rows)
    print(f"{name}: n={len(rows)} error={t} healthy={f} undecided={n}")
    return t, f, n


print()
summarize(control, "POSITIVE CONTROL (94 CAD-removed, truly absent)")
summarize(sample, "RANDOM SAMPLE (present in 0.5.stl)")
print("\ncontrol realized fractions:",
      sorted(round(r["realized"], 3) for r in control if r["realized"] is not None))
print("wrote", out)
