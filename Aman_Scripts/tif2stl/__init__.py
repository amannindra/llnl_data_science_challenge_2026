"""TIFF-vs-STL validation: does the CT scan match the design mesh?

Importing this package performs no file I/O.  Run the end-to-end check with:

    conda run -n DSC python Aman_Scripts/tif2stl/validate.py --help
"""

from tif2stl.metrics import (
    OverlapMetrics,
    fraction_inside_mask,
    mask_bounds_zyx,
    mask_overlap,
    per_slab_overlap,
    window_slices_zyx,
)
from tif2stl.registration import (
    SimilarityFit,
    paired_junction_positions,
    proper_cube_rotations,
    similarity_transform,
    stl_to_design_matrix,
)
from tif2stl.stl_geometry import (
    read_stl_triangles,
    stl_enclosed_volume,
    subdivide_triangles,
    triangle_surface_points,
)
from tif2stl.voxelize import VoxelizedSurface, voxelize_stl

__all__ = [
    "OverlapMetrics",
    "SimilarityFit",
    "VoxelizedSurface",
    "fraction_inside_mask",
    "mask_bounds_zyx",
    "mask_overlap",
    "paired_junction_positions",
    "per_slab_overlap",
    "proper_cube_rotations",
    "read_stl_triangles",
    "similarity_transform",
    "stl_enclosed_volume",
    "stl_to_design_matrix",
    "subdivide_triangles",
    "triangle_surface_points",
    "voxelize_stl",
    "window_slices_zyx",
]
