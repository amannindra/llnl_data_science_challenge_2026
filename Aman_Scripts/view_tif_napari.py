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
import sys
from pathlib import Path

import numpy as np

try:  # Package import.
    from .Components.asset_io import (
        AssetNotMaterializedError,
        inspect_tiff,
        read_tiff,
    )
    from .Components.paths import data_path, find_repository_root
except ImportError:  # Direct execution.
    from Components.asset_io import AssetNotMaterializedError, inspect_tiff, read_tiff
    from Components.paths import data_path, find_repository_root


ROOT = find_repository_root(__file__)
DEFAULT_TIF = data_path(
    "9x9x9_octet_lattice", "9x9x9_octet_lattice.tif", root=ROOT
)


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

    path = Path(args.path).expanduser().resolve(strict=False)
    try:
        metadata = inspect_tiff(path)
    except (FileNotFoundError, IsADirectoryError, AssetNotMaterializedError, OSError) as exc:
        sys.exit(f"ERROR: cannot open TIFF: {exc}")

    try:
        import napari
    except ImportError:
        sys.exit('ERROR: napari not installed in this env.\n'
                 '       /Users/amannindra/miniconda3/envs/DSC/bin/pip install "napari[pyqt5]"')

    size_mb = path.stat().st_size / 1e6
    print(f"Opening (lazy/memmap): {path}  ({size_mb:.0f} MB)")
    try:
        vol = read_tiff(path)                 # disk-backed, not loaded into RAM
    except ValueError as exc:
        sys.exit(f"ERROR: TIFF cannot be memory-mapped safely: {exc}")
    print(f"  volume shape={vol.shape} dtype={vol.dtype}")
    print(f"  axes={metadata.axes}, pages={metadata.page_count}")

    lo, hi = robust_contrast(vol)
    print(f"  contrast limits = ({lo:.0f}, {hi:.0f})")

    viewer = napari.Viewer(title=path.name)
    viewer.add_image(
        vol,
        name=path.name,
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
