#!/usr/bin/env python3
"""Stage 7: run the detector's CT comparator on the rotation the CT supports."""
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
from Components.lattice_graph import load_lattice_graph
from Components.paths import data_path
from Components.cad_strut_mapping import build_registered_centerline_atlas
from Components.strut_comparison import compare_strut_local

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)
arb = json.load(open(TMP / "arbiter.json"))
missing = data_path("missing_struts")
graph = load_lattice_graph(
    missing / "registered_jsons" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)
atlas = build_registered_centerline_atlas(graph, axial_bins=45)
strut_ids = atlas["strut_ids"]
e0, e1 = atlas["endpoint0_xyz"], atlas["endpoint1_xyz"]
index_of = {int(v): i for i, v in enumerate(strut_ids)}

volume = read_tiff(
    missing / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
    mmap_mode="r",
)
EMPTY = np.zeros((0, 3), dtype=np.float64)
RADIUS = 3.6717664968970167

for rotation in ("-x-z-y", "+z+x+y"):
    ids = arb[rotation]["absent_ids"]
    rows = []
    for sid in ids:
        idx = index_of[sid]
        res = compare_strut_local(
            volume, e0[idx], e1[idx], EMPTY,
            expected_present_override=True, expected_radius_voxels=RADIUS,
        )
        rows.append(res["has_error"])
    t = sum(r is True for r in rows)
    f = sum(r is False for r in rows)
    n = sum(r is None for r in rows)
    tag = "  <== CT-supported" if rotation == "-x-z-y" else "  <== pipeline hardcoded"
    print(f"rotation {rotation}: omitted={len(ids)}  detector flags error={t}  "
          f"calls healthy={f}  undecided={n}   sensitivity={t/len(ids):.1%}{tag}")

    mids = np.array([(e0[index_of[s]] + e1[index_of[s]]) / 2 for s in ids])
    print(f"    spatial spread of that set (voxels): "
          f"X {mids[:,0].min():.0f}-{mids[:,0].max():.0f}  "
          f"Y {mids[:,1].min():.0f}-{mids[:,1].max():.0f}  "
          f"Z {mids[:,2].min():.0f}-{mids[:,2].max():.0f}")
