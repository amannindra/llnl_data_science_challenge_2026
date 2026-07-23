"""
Interactively view a CT .tif stack (e.g. the 9x9x9 octet lattice) in napari.

The TIFF is a ~1 GB uint16 volume (761 x 815 x 837 for the 9x9x9 lattice), so it
is opened with tifffile.memmap -- disk-backed and lazy, nothing is fully loaded
into RAM. napari gives you a z-slider (2D) plus a 3D volume-render toggle.

Run inside the DSC conda env:
    /Users/amannindra/miniconda3/envs/DSC/bin/python Scripts/view_tif_napari.py
    # or, with the env active:  python Scripts/view_tif_napari.py

Optionally point it at a different stack:
    python Scripts/view_tif_napari.py --path "data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"

Requires: napari + a Qt backend (pyqt5). Install once:
    /Users/amannindra/miniconda3/envs/DSC/bin/pip install "napari[pyqt5]"
"""
import argparse
import os
import sys

import numpy as np
import tifffile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TIF = os.path.join(ROOT, "data", "9x9x9_octet_lattice", "9x9x9_octet_lattice.tif")


def robust_contrast(vol, n_slices=40, pct=(1.0, 99.6)):
    """Estimate display contrast limits from a sample of slices (avoids reading 1 GB)."""
    idx = np.linspace(0, vol.shape[0] - 1, min(n_slices, vol.shape[0])).astype(int)
    sample = np.stack([vol[z].astype(np.float32) for z in idx])
    lo, hi = np.percentile(sample, pct)
    return float(lo), float(hi)


def main():
    parser = argparse.ArgumentParser(description="View a CT .tif stack in napari.")
    parser.add_argument("--path", default=DEFAULT_TIF, help="Path to the .tif stack.")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"ERROR: file not found: {args.path}\n"
                 f"       (is it still a git-lfs pointer? run `git lfs pull`)")

    size_mb = os.path.getsize(args.path) / 1e6
    if size_mb < 1:
        sys.exit(f"ERROR: {args.path} is only {size_mb:.3f} MB -- looks like an "
                 f"unpulled git-lfs pointer. Run `git lfs pull` first.")

    try:
        import napari
    except ImportError:
        sys.exit('ERROR: napari not installed in this env.\n'
                 '       /Users/amannindra/miniconda3/envs/DSC/bin/pip install "napari[pyqt5]"')

    print(f"Opening (lazy/memmap): {args.path}  ({size_mb:.0f} MB)")
    vol = tifffile.memmap(args.path)          # disk-backed, not loaded into RAM
    print(f"  volume shape={vol.shape} dtype={vol.dtype}")

    lo, hi = robust_contrast(vol)
    print(f"  contrast limits = ({lo:.0f}, {hi:.0f})")

    viewer = napari.Viewer(title=os.path.basename(args.path))
    viewer.add_image(
        vol,
        name=os.path.basename(args.path),
        colormap="gray",
        contrast_limits=(lo, hi),
        rendering="mip",          # used when you flip to 3D
        multiscale=False,
    )
    print("  napari open. Scroll the z-slider; click the 2D/3D toggle "
          "(bottom-left) for a volume render. Close the window to exit.")
    napari.run()


if __name__ == "__main__":
    main()
