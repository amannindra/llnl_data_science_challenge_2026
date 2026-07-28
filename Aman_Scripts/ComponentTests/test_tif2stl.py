"""Adversarial checks for the tif2stl validation package."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import numpy as np

from _harness import Checker, finish

from Components.asset_io import AssetNotMaterializedError, inspect_stl
from Components.coordinates import apply_transform, homogeneous_matrix, rotation_matrix_xyz
from Components.lattice_graph import load_lattice_graph, parse_lattice_graph
from Components.paths import data_path
from tif2stl import (
    fraction_inside_mask,
    mask_bounds_zyx,
    mask_overlap,
    paired_junction_positions,
    per_slab_overlap,
    proper_cube_rotations,
    read_stl_triangles,
    similarity_transform,
    stl_enclosed_volume,
    stl_to_design_matrix,
    subdivide_triangles,
    triangle_surface_points,
    voxelize_stl,
    window_slices_zyx,
)
from tif2stl.validate import sample_stl_points_mm, score_orientations
from tif2stl import visualize as viz

_RECORD = np.dtype([
    ("normal", "<f4", (3,)),
    ("vertices", "<f4", (3, 3)),
    ("attributes", "<u2"),
])


def cube_triangles(lower, upper):
    lower = np.asarray(lower, dtype=np.float64)
    upper = np.asarray(upper, dtype=np.float64)
    corner = lambda x, y, z: np.where([x, y, z], upper, lower)  # noqa: E731
    quads = [
        (corner(0, 0, 0), corner(0, 1, 0), corner(1, 1, 0), corner(1, 0, 0)),  # -Z
        (corner(0, 0, 1), corner(1, 0, 1), corner(1, 1, 1), corner(0, 1, 1)),  # +Z
        (corner(0, 0, 0), corner(1, 0, 0), corner(1, 0, 1), corner(0, 0, 1)),  # -Y
        (corner(0, 1, 0), corner(0, 1, 1), corner(1, 1, 1), corner(1, 1, 0)),  # +Y
        (corner(0, 0, 0), corner(0, 0, 1), corner(0, 1, 1), corner(0, 1, 0)),  # -X
        (corner(1, 0, 0), corner(1, 1, 0), corner(1, 1, 1), corner(1, 0, 1)),  # +X
    ]
    triangles = []
    for a, b, c, d in quads:
        triangles.append([a, b, c])
        triangles.append([a, c, d])
    return np.asarray(triangles, dtype=np.float64)


def write_binary_stl(path, triangles):
    triangles = np.asarray(triangles, dtype=np.float64)
    records = np.zeros(len(triangles), dtype=_RECORD)
    records["vertices"] = triangles.astype("<f4")
    with open(path, "wb") as handle:
        handle.write(b"\0" * 80)
        handle.write(struct.pack("<I", len(triangles)))
        records.tofile(handle)
    return Path(path)


def write_ascii_stl(path, triangles):
    lines = ["solid synthetic"]
    for triangle in np.asarray(triangles, dtype=np.float64):
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        for vertex in triangle:
            lines.append(f"      vertex {vertex[0]} {vertex[1]} {vertex[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid synthetic")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(path)


def graph_from_positions(positions_by_id):
    payload = {
        "junctions": [
            {"id": jid, "position": list(map(float, position))}
            for jid, position in sorted(positions_by_id.items())
        ],
        "struts": [],
        "unit_cells": [],
    }
    return parse_lattice_graph(payload)


def signed_volume(triangles):
    v0, v1, v2 = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum()) / 6.0


def main() -> int:
    checker = Checker("tif2stl STL-vs-TIFF validation", minimum_checks=10)
    rng = np.random.default_rng(20260727)

    with tempfile.TemporaryDirectory() as scratch_name:
        scratch = Path(scratch_name)
        cube = cube_triangles((1.0, 2.0, 3.0), (3.0, 5.0, 7.0))
        binary_cube = write_binary_stl(scratch / "cube.stl", cube)
        ascii_cube = write_ascii_stl(scratch / "cube_ascii.stl", cube)

        # --- stl_geometry: streaming readers -----------------------------
        chunks = list(read_stl_triangles(binary_cube, chunk_faces=5))
        checker.equal("binary chunking yields 5+5+2 triangles",
                      [len(chunk) for chunk in chunks], [5, 5, 2])
        merged = np.concatenate(chunks)
        checker.check(
            "binary vertices span the exact cube bounds",
            np.allclose(merged.reshape(-1, 3).min(axis=0), (1, 2, 3))
            and np.allclose(merged.reshape(-1, 3).max(axis=0), (3, 5, 7)),
        )
        ascii_merged = np.concatenate(list(read_stl_triangles(ascii_cube, chunk_faces=4)))
        checker.equal("ascii parse recovers all 12 facets", len(ascii_merged), 12)
        checker.close("ascii signed volume matches binary",
                      signed_volume(ascii_merged), signed_volume(merged))
        checker.close("stl_enclosed_volume of 2x3x4 cube is 24",
                      stl_enclosed_volume(binary_cube), 24.0)
        checker.raises("missing STL raises FileNotFoundError",
                       FileNotFoundError, lambda: list(read_stl_triangles(scratch / "nope.stl")))
        checker.raises("directory path raises IsADirectoryError",
                       IsADirectoryError, lambda: list(read_stl_triangles(scratch)))
        pointer = scratch / "pointer.stl"
        pointer.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{'a' * 64}\nsize 42\n", encoding="utf-8",
        )
        checker.raises("LFS pointer raises AssetNotMaterializedError",
                       AssetNotMaterializedError, lambda: list(read_stl_triangles(pointer)))
        poisoned = cube.copy()
        poisoned[3, 1, 2] = np.nan
        bad_binary = write_binary_stl(scratch / "nan.stl", poisoned)
        checker.raises("nonfinite binary vertex raises ValueError",
                       ValueError, lambda: list(read_stl_triangles(bad_binary)))
        torn = scratch / "torn.stl"
        torn.write_text(
            "solid torn\n facet normal 0 0 0\n outer loop\n"
            " vertex 0 0 0\n vertex 1 0 0\n endloop\n endfacet\nendsolid torn\n",
            encoding="utf-8",
        )
        checker.raises("ascii facet with 2 vertices raises ValueError",
                       ValueError, lambda: list(read_stl_triangles(torn)))
        checker.raises("chunk_faces=0 raises ValueError",
                       ValueError, read_stl_triangles, binary_cube, chunk_faces=0)

        # --- stl_geometry: densification ---------------------------------
        big = np.asarray([[[0.0, 0.0, 0.0], [8.0, 0.0, 0.0], [0.0, 8.0, 0.0]]])
        dense = subdivide_triangles(big, 1.0)
        edge_lengths = np.stack([
            np.linalg.norm(dense[:, 1] - dense[:, 0], axis=1),
            np.linalg.norm(dense[:, 2] - dense[:, 1], axis=1),
            np.linalg.norm(dense[:, 0] - dense[:, 2], axis=1),
        ])
        checker.check("subdivision bounds every edge by max_edge",
                      float(edge_lengths.max()) <= 1.0 + 1e-12,
                      f"max edge {edge_lengths.max():.4f}")
        areas = 0.5 * np.linalg.norm(
            np.cross(dense[:, 1] - dense[:, 0], dense[:, 2] - dense[:, 0]), axis=1
        )
        checker.close("subdivision preserves total area", float(areas.sum()), 32.0)
        untouched = subdivide_triangles(big, 100.0)
        checker.check("no split when edges already satisfy max_edge",
                      untouched.shape == (1, 3, 3) and np.allclose(untouched, big))
        checker.raises("subdivide rejects nonpositive max_edge",
                       ValueError, subdivide_triangles, big, 0.0)
        checker.raises("subdivide rejects malformed shapes",
                       ValueError, subdivide_triangles, np.zeros((2, 3, 2)), 1.0)
        checker.raises("subdivide rejects nonfinite triangles",
                       ValueError, subdivide_triangles, np.full((1, 3, 3), np.nan), 1.0)
        checker.raises("subdivide enforces the triangle budget",
                       ValueError, subdivide_triangles, big, 0.01, max_triangles=100)
        points = triangle_surface_points(cube)
        checker.equal("surface points = 3 vertices + 1 centroid per triangle",
                      points.shape, (len(cube) * 4, 3))
        checker.check("empty triangle set yields (0, 3) points",
                      triangle_surface_points(np.zeros((0, 3, 3))).shape == (0, 3))

        # --- metrics ------------------------------------------------------
        base = np.zeros((4, 4, 4), dtype=bool)
        base[1:3, 1:3, 1:3] = True
        checker.check("identical masks score dice=iou=1",
                      (lambda m: m.dice == 1.0 and m.iou == 1.0)(mask_overlap(base, base)))
        shifted = np.zeros_like(base)
        shifted[3, 3, 3] = True
        disjoint = mask_overlap(base, shifted)
        checker.check("disjoint masks score dice=0 with additive union",
                      disjoint.dice == 0.0 and disjoint.union_voxels == 9)
        half_a = np.array([[1, 1, 0, 0]], dtype=np.uint8)
        half_b = np.array([[0, 1, 1, 0]], dtype=np.uint8)
        checker.close("known half overlap scores dice=0.5",
                      mask_overlap(half_a, half_b).dice, 0.5)
        empty = np.zeros((2, 2), dtype=bool)
        both_empty = mask_overlap(empty, empty)
        checker.check("two empty masks agree perfectly by convention",
                      both_empty.dice == 1.0 and both_empty.a_in_b_fraction == 1.0)
        one_empty = mask_overlap(empty, np.ones((2, 2), dtype=bool))
        checker.check("one empty mask scores zero everywhere",
                      one_empty.dice == 0.0 and one_empty.a_in_b_fraction == 0.0)
        checker.raises("mask shape mismatch raises ValueError",
                       ValueError, mask_overlap, np.zeros((2, 2)), np.zeros((3, 2)))
        checker.raises("NaN float mask raises ValueError",
                       ValueError, mask_overlap, np.full((2, 2), np.nan), np.zeros((2, 2)))
        checker.raises("string mask dtype raises ValueError",
                       ValueError, mask_overlap, np.array([["x", "y"]]), np.zeros((1, 2)))
        bounds = mask_bounds_zyx(base)
        checker.equal("mask bounds are half-open per axis",
                      bounds, ((1, 1, 1), (3, 3, 3)))
        checker.check("empty mask has no bounds",
                      mask_bounds_zyx(np.zeros((3, 3), dtype=bool)) is None)
        slab_a = np.zeros((5, 2, 2), dtype=bool)
        slab_a[0] = True
        rows = per_slab_overlap(slab_a, slab_a, slab_depth=2)
        checker.check(
            "per-slab rows cover [0,2),[2,4),[4,5) with correct dice",
            [row["z_start"] for row in rows] == [0, 2, 4]
            and rows[0]["dice"] == 1.0 and rows[1]["dice"] == 1.0
            and rows[-1]["z_stop"] == 5,
        )
        checker.raises("per-slab rejects nonpositive slab_depth",
                       ValueError, per_slab_overlap, slab_a, slab_a, slab_depth=0)
        checker.raises("per-slab rejects non-3D masks",
                       ValueError, per_slab_overlap, np.zeros((2, 2)), np.zeros((2, 2)))

        # --- registration -------------------------------------------------
        source = rng.uniform(-10.0, 10.0, size=(50, 3))
        rotation = rotation_matrix_xyz((10.0, 20.0, 30.0), degrees=True)
        target = 2.5 * source @ rotation.T + np.array([1.0, -2.0, 3.0])
        fit = similarity_transform(source, target)
        checker.close("Umeyama recovers the known scale", fit.scale, 2.5,
                      relative_tolerance=1e-9)
        checker.check("Umeyama recovers rotation and translation",
                      np.allclose(fit.rotation, rotation, atol=1e-9)
                      and np.allclose(fit.translation, (1.0, -2.0, 3.0), atol=1e-8))
        checker.check("fit residuals vanish on exact correspondences",
                      fit.rms_error < 1e-9 and fit.max_error < 1e-8,
                      f"rms={fit.rms_error:.2e}")
        checker.check("fit matrix reproduces targets via apply_transform",
                      np.allclose(apply_transform(source, fit.matrix), target, atol=1e-8))
        expected_angle = float(np.degrees(np.arccos((np.trace(rotation) - 1.0) / 2.0)))
        checker.close("rotation_angle_degrees matches the axis-angle magnitude",
                      fit.rotation_angle_degrees, expected_angle, relative_tolerance=1e-6)
        rigid_target = source @ rotation.T + 5.0
        rigid = similarity_transform(source, rigid_target, with_scale=False)
        checker.check("with_scale=False pins scale to 1 and still fits",
                      rigid.scale == 1.0 and rigid.rms_error < 1e-9)
        checker.raises("fewer than 3 correspondences raise ValueError",
                       ValueError, similarity_transform, source[:2], target[:2])
        checker.raises("mismatched point counts raise ValueError",
                       ValueError, similarity_transform, source[:5], target[:6])
        line = np.outer(np.arange(5.0), np.ones(3))
        checker.raises("collinear correspondences raise ValueError",
                       ValueError, similarity_transform, line, line * 2.0)
        checker.raises("coincident source points raise ValueError",
                       ValueError, similarity_transform, np.ones((4, 3)), target[:4])
        checker.raises("nonfinite coordinates raise ValueError",
                       ValueError, similarity_transform,
                       np.full((4, 3), np.nan), target[:4])
        stl_map = stl_to_design_matrix(mm_per_design_unit=2.0,
                                       stl_center_xyz=(1.0, 2.0, 3.0))
        centered = apply_transform(np.array([[1.0, 2.0, 3.0], [3.0, 2.0, 3.0]]), stl_map)
        checker.check("stl_to_design maps centre to (9,9,9) and 2 mm to 1 unit",
                      np.allclose(centered[0], (9.0, 9.0, 9.0))
                      and np.allclose(centered[1], (10.0, 9.0, 9.0)))
        checker.raises("stl_to_design rejects nonpositive mm scale",
                       ValueError, lambda: stl_to_design_matrix(mm_per_design_unit=0.0))
        graph_a = graph_from_positions({0: (0, 0, 0), 1: (2, 0, 0), 2: (0, 2, 0), 3: (0, 0, 2)})
        graph_b = graph_from_positions({0: (1, 1, 1), 1: (5, 1, 1), 2: (1, 5, 1), 3: (1, 1, 5)})
        paired_source, paired_target = paired_junction_positions(graph_a, graph_b)
        pair_fit = similarity_transform(paired_source, paired_target)
        checker.check("paired junctions align by id and refit their transform",
                      paired_source.shape == (4, 3)
                      and abs(pair_fit.scale - 2.0) < 1e-9
                      and np.allclose(pair_fit.translation, (1.0, 1.0, 1.0), atol=1e-9))
        graph_c = graph_from_positions({10: (0, 0, 0), 11: (1, 0, 0), 12: (0, 1, 0)})
        checker.raises("graphs sharing <3 junction ids raise ValueError",
                       ValueError, paired_junction_positions, graph_a, graph_c)

        # --- orientation resolution ---------------------------------------
        rotations = proper_cube_rotations()
        names = [name for name, _ in rotations]
        checker.check("proper_cube_rotations yields 24 uniquely named candidates",
                      len(rotations) == 24 and len(set(names)) == 24)
        checker.check(
            "every candidate is orthogonal with determinant +1",
            all(
                np.allclose(matrix @ matrix.T, np.eye(3))
                and abs(np.linalg.det(matrix) - 1.0) < 1e-12
                for _, matrix in rotations
            ),
        )
        checker.check("identity rotation '+x+y+z' is listed first",
                      names[0] == "+x+y+z" and np.array_equal(rotations[0][1], np.eye(3)))
        by_name = dict(rotations)
        checker.check(
            "'+x+z-y' maps (a, b, c) to (a, c, -b) as its name reads",
            np.allclose(by_name["+x+z-y"] @ np.array([1.0, 2.0, 3.0]), (1.0, 3.0, -2.0)),
        )
        swap = stl_to_design_matrix(mm_per_design_unit=2.0,
                                    stl_center_xyz=(1.0, 2.0, 3.0),
                                    rotation=by_name["+x+z-y"])
        swapped = apply_transform(np.array([[3.0, 2.0, 3.0], [1.0, 4.0, 3.0]]), swap)
        checker.check(
            "stl_to_design applies the rotation about the lattice centre",
            np.allclose(swapped[0], (10.0, 9.0, 9.0))
            and np.allclose(swapped[1], (9.0, 9.0, 8.0)),
        )
        checker.raises("stl_to_design rejects a malformed rotation",
                       ValueError, lambda: stl_to_design_matrix(
                           mm_per_design_unit=1.0, rotation=np.zeros((2, 2))))
        probe_mask = np.zeros((1, 2, 3), dtype=bool)
        probe_mask[0, 1, 2] = True
        checker.close(
            "fraction_inside_mask indexes XYZ points into the ZYX mask",
            fraction_inside_mask(probe_mask, np.array([[2.5, 1.5, 0.5]]),
                                 origin_xyz=(0.0, 0.0, 0.0), pitch=1.0),
            1.0,
        )
        trio = np.array([[0.5, 0.5, 0.5], [1.5, 0.5, 0.5], [0.5, 0.5, 9.9]])
        corner_mask = np.zeros((2, 2, 2), dtype=bool)
        corner_mask[0, 0, 0] = True
        checker.close(
            "out-of-grid points count as misses in the denominator",
            fraction_inside_mask(corner_mask, trio,
                                 origin_xyz=(0.0, 0.0, 0.0), pitch=1.0),
            1.0 / 3.0,
        )
        checker.raises("fraction_inside_mask rejects empty point sets",
                       ValueError, fraction_inside_mask, corner_mask,
                       np.zeros((0, 3)), origin_xyz=(0.0, 0.0, 0.0), pitch=1.0)
        checker.raises("fraction_inside_mask rejects nonpositive pitch",
                       ValueError, fraction_inside_mask, corner_mask,
                       trio, origin_xyz=(0.0, 0.0, 0.0), pitch=0.0)
        window = window_slices_zyx(
            np.array([[2.2, 3.2, 4.2], [5.8, 3.4, 4.9]]),
            origin_xyz=(0.0, 0.0, 0.0), pitch=1.0,
            shape_zyx=(10, 10, 10), padding_cells=2,
        )
        checker.equal("window slices pad the point bounds in ZYX order",
                      window, (slice(2, 7), slice(1, 6), slice(0, 8)))
        clamped = window_slices_zyx(
            np.array([[9.5, 0.2, 9.5]]),
            origin_xyz=(0.0, 0.0, 0.0), pitch=1.0,
            shape_zyx=(10, 10, 10), padding_cells=2,
        )
        checker.equal("window slices clamp to the grid bounds",
                      clamped, (slice(7, 10), slice(0, 3), slice(7, 10)))
        checker.raises("window rejects negative padding",
                       ValueError, window_slices_zyx, trio,
                       origin_xyz=(0.0, 0.0, 0.0), pitch=1.0,
                       shape_zyx=(4, 4, 4), padding_cells=-1)
        slab_stl = write_binary_stl(scratch / "slab.stl",
                                    cube_triangles((-3.0, -1.0, -0.5), (3.0, 1.0, 0.5)))
        sample_once = sample_stl_points_mm(str(slab_stl), chunk_faces=4, chunk_stride=1)
        sample_again = sample_stl_points_mm(str(slab_stl), chunk_faces=4, chunk_stride=1)
        capped = sample_stl_points_mm(str(slab_stl), chunk_faces=4, chunk_stride=1,
                                      max_points=10)
        checker.check("STL point sampling is deterministic and honours max_points",
                      np.array_equal(sample_once, sample_again)
                      and 0 < len(capped) <= 10)
        planted = by_name["+x+z-y"]
        planted_map = stl_to_design_matrix(mm_per_design_unit=1.0, rotation=planted)
        planted_mask = voxelize_stl(
            slab_stl, pitch=1.0, transform=planted_map,
            origin_xyz=(-0.5, -0.5, -0.5), grid_shape_zyx=(19, 19, 19),
        ).grid
        scores = score_orientations(
            planted_mask, sample_once,
            fit_matrix=np.eye(4), mm_per_design_unit=1.0,
            stl_center=(0.0, 0.0, 0.0), design_center=(9.0, 9.0, 9.0),
            downsample=1,
        )
        box_preserving = {"+x+z-y", "+x-z+y", "-x+z+y", "-x-z-y"}
        identity_score = next(row["score"] for row in scores if row["name"] == "+x+y+z")
        checker.check(
            "orientation scoring recovers the planted y<->z rotation",
            scores[0]["name"] in box_preserving
            and scores[0]["score"] > 0.9
            and identity_score < scores[0]["score"] - 0.05,
            f"best={scores[0]['name']}@{scores[0]['score']:.3f}, "
            f"identity@{identity_score:.3f}",
        )

        # --- visualize helpers --------------------------------------------
        plane = np.array([[True, False], [False, True]])
        tinted = viz.plane_rgb(plane, viz.STL_COLOR)
        checker.check(
            "plane_rgb paints foreground with the color and background dark",
            tuple(tinted[0, 0]) == viz.STL_COLOR
            and tuple(tinted[0, 1]) == viz.BACKGROUND,
        )
        ct_plane = np.array([[True, True, False, False]])
        stl_plane = np.array([[False, True, True, False]])
        agreement = viz.overlay_rgb(ct_plane, stl_plane)
        checker.check(
            "overlay_rgb follows the red/green/yellow/background convention",
            tuple(agreement[0, 0]) == viz.CT_ONLY
            and tuple(agreement[0, 1]) == viz.BOTH
            and tuple(agreement[0, 2]) == viz.STL_ONLY
            and tuple(agreement[0, 3]) == viz.BACKGROUND,
        )
        checker.raises("overlay_rgb rejects mismatched plane shapes",
                       ValueError, viz.overlay_rgb, ct_plane, np.zeros((2, 2), dtype=bool))
        panel = viz.compose_panel(stl_plane, ct_plane)
        expected_width = 3 * 4 + 4 * viz.MARGIN
        expected_height = 1 + 2 * viz.MARGIN + viz.LABEL_BAND
        checker.equal("compose_panel lays out three tiles with margins and label band",
                      panel.shape, (expected_height, expected_width, 3))

        # --- voxelize -----------------------------------------------------
        solid_cube = write_binary_stl(scratch / "solid.stl",
                                      cube_triangles((0.0, 0.0, 0.0), (8.0, 8.0, 8.0)))
        double = homogeneous_matrix(scale=2.0)
        voxelized = voxelize_stl(solid_cube, pitch=1.0, transform=double)
        checker.check(
            "filled 16-cell cube volume is within 20% of 4096 cells",
            abs(voxelized.occupied_voxels - 4096) / 4096 < 0.2,
            f"occupied={voxelized.occupied_voxels}",
        )
        checker.equal("no surface point falls outside an auto-fitted grid",
                      voxelized.points_outside, 0)
        span = mask_bounds_zyx(voxelized.grid)
        extents = [stop - start for start, stop in zip(span[0], span[1])]
        checker.check("voxelized extent spans ~16 cells per axis",
                      all(15 <= extent <= 18 for extent in extents), f"extents={extents}")
        shell = voxelize_stl(solid_cube, pitch=1.0, transform=double, fill=False)
        checker.check("fill=False leaves a hollow shell (fewer cells than solid)",
                      0 < shell.occupied_voxels < voxelized.occupied_voxels,
                      f"shell={shell.occupied_voxels}")
        repeat = voxelize_stl(solid_cube, pitch=1.0, transform=double)
        checker.check("voxelization is deterministic across runs",
                      np.array_equal(voxelized.grid, repeat.grid))
        cropped = voxelize_stl(solid_cube, pitch=1.0, transform=double,
                               origin_xyz=(-0.5, -0.5, -0.5), grid_shape_zyx=(4, 4, 4))
        checker.check("caller-supplied small grid counts escaping points",
                      cropped.points_outside > 0 and cropped.grid.shape == (4, 4, 4))
        checker.raises("voxelize rejects nonpositive pitch",
                       ValueError, voxelize_stl, solid_cube, pitch=0.0)
        checker.raises("origin without grid shape raises ValueError",
                       ValueError, voxelize_stl, solid_cube, pitch=1.0,
                       origin_xyz=(0.0, 0.0, 0.0))
        checker.raises("grid voxel budget is enforced",
                       ValueError, voxelize_stl, solid_cube, pitch=0.05,
                       transform=double, max_grid_voxels=1000)
        empty_stl = write_binary_stl(scratch / "empty.stl", np.zeros((0, 3, 3)))
        checker.raises("empty STL raises ValueError",
                       ValueError, voxelize_stl, empty_stl, pitch=1.0)

    # --- real project assets ---------------------------------------------
    design_path = data_path("missing_struts", "octet_truss_9x9x9.json")
    registered_path = data_path(
        "missing_struts", "registered_jsons",
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json",
    )
    stl_path = data_path("missing_struts", "stls", "0.5.stl")
    design_graph = load_lattice_graph(design_path)
    registered_graph = load_lattice_graph(registered_path)
    design_points, registered_points = paired_junction_positions(design_graph, registered_graph)
    checker.equal("design and registered JSONs pair all 10,206 junctions",
                  design_points.shape, (10206, 3))
    real_fit = similarity_transform(design_points, registered_points)
    checker.close("design->CT scale is 39.4888 voxels per design unit",
                  real_fit.scale, 39.488809, relative_tolerance=1e-4)
    checker.check("design->CT registration is exact (rms < 0.01 voxel)",
                  real_fit.rms_error < 0.01, f"rms={real_fit.rms_error:.3e}")
    checker.check("part tilt in the CT frame is under 1 degree",
                  real_fit.rotation_angle_degrees < 1.0,
                  f"angle={real_fit.rotation_angle_degrees:.4f} deg")
    checker.check(
        "registered junctions sit inside the (837, 815, 761) XYZ grid",
        bool(
            (registered_points.min(axis=0) > 0).all()
            and (registered_points.max(axis=0) < np.array([837.0, 815.0, 761.0])).all()
        ),
    )
    stl_metadata = inspect_stl(stl_path)
    checker.equal("0.5.stl is the expected 3,498,656-triangle binary mesh",
                  (stl_metadata.encoding, stl_metadata.triangles), ("binary", 3498656))
    extent_x = stl_metadata.bounding_box_max[0] - stl_metadata.bounding_box_min[0]
    checker.close("0.5.stl X extent implies ~2.305 mm per design unit",
                  extent_x / 18.0, 2.305154, relative_tolerance=1e-3)

    return checker.done()


if __name__ == "__main__":
    finish(main())
