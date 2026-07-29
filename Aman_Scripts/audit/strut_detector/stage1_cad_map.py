#!/usr/bin/env python3
"""Stage 1: reproduce the registration + CAD-omission map and cache it."""
from pathlib import Path
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

TMP = Path(__file__).resolve().parent / "_cache"
TMP.mkdir(exist_ok=True)

from Components.paths import data_path
from Components.strut_pipeline import build_stl_to_ct_registration, prepare_cad_strut_map

missing = data_path("missing_struts")
stl05 = missing / "stls" / "0.5.stl"
stl0 = missing / "stls" / "0.stl"
design = missing / "octet_truss_9x9x9.json"
registered = missing / "registered_jsons" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"

reg = build_stl_to_ct_registration(stl05, design, registered)
print("registration matrix:\n", reg["matrix"])
print("scale vox/unit", reg["design_to_ct_scale_voxels_per_unit"])
print("rot deg", reg["design_to_ct_rotation_degrees"])
print("residual xz mm", reg["surface_extent_residual_xz_mm"])

cad = prepare_cad_strut_map(stl0, stl05, registered, reg["matrix"], progress=print)
intent = cad["intent"]
atlas = cad["atlas"]
print("removed_count", intent["removed_count"], "gap", intent["cluster_gap"], "thr", intent["split_threshold"])

out = TMP / "cad_map.npz"
np.savez_compressed(
    out,
    matrix=reg["matrix"],
    strut_ids=atlas["strut_ids"],
    endpoint0=atlas["endpoint0_xyz"],
    endpoint1=atlas["endpoint1_xyz"],
    median_drop=intent["median_coverage_drop"],
    removed_ids=intent["removed_strut_ids"],
    specimen_cov=np.asarray(cad["specimen_surface"]["coverage"]).mean(axis=1),
    complete_cov=np.asarray(cad["complete_surface"]["coverage"]).mean(axis=1),
    scale=np.asarray([reg["design_to_ct_scale_voxels_per_unit"]]),
)
print("wrote", out)
