#!/usr/bin/env python3
"""Adversarial checks for raw-TIFF profiling, surface extraction, and PLY I/O."""

from __future__ import annotations

import json
import stat
import tempfile
from pathlib import Path

import numpy as np
import tifffile

from _harness import Checker, finish

from Components.tiff_mesh import (
    BoundsZYX,
    MeshChunks,
    ResourceEstimate,
    TIFFMeshError,
    estimate_resources,
    extract_surface_slabbed,
    foreground_profile,
    inspect_binary_ply,
    otsu_threshold_from_histogram,
    streaming_integer_histogram,
    validate_foreground_profile,
    validate_resources,
    validate_scalar_volume,
    write_binary_ply,
)
from export_tiff_mesh import convert_tiff_to_ply, parse_spacing, parse_threshold


def cube_volume() -> np.ndarray:
    """Return an asymmetric binary cuboid whose expected XYZ bounds are known."""

    volume = np.zeros((10, 12, 14), dtype=np.uint16)
    volume[2:7, 3:9, 4:11] = 100
    return volume


def triangle_signature(mesh: MeshChunks) -> list[tuple[tuple[float, ...], ...]]:
    """Return face geometry independent of vertex numbering or face ordering."""

    vertices = np.concatenate(mesh.vertices_xyz, axis=0)
    faces = np.concatenate(mesh.faces, axis=0)
    signatures = []
    for face in faces:
        points = [tuple(float(item) for item in vertices[index]) for index in face]
        signatures.append(tuple(sorted(points)))
    return sorted(signatures)


def run() -> int:
    """Execute more than ten independent checks and return zero only on success."""

    check = Checker("TIFF to MeshLab conversion", minimum_checks=20)
    volume = cube_volume()

    check.equal("valid scalar volume reports ZYX shape", validate_scalar_volume(volume), volume.shape)
    check.raises(
        "2D input is rejected", TIFFMeshError, validate_scalar_volume,
        np.zeros((4, 4), dtype=np.uint8),
    )
    check.raises(
        "nonnumeric input is rejected", TIFFMeshError, validate_scalar_volume,
        np.full((2, 2, 2), "x", dtype="U1"),
    )
    nonfinite = np.zeros((2, 2, 2), dtype=np.float32)
    nonfinite[0, 0, 0] = np.nan
    check.raises("nonfinite input is rejected", TIFFMeshError, validate_scalar_volume, nonfinite)

    histogram, offset = streaming_integer_histogram(volume, chunk_depth=3)
    check.equal("uint16 histogram offset is zero", offset, 0)
    check.equal("streamed histogram counts every voxel", int(histogram.sum()), volume.size)
    check.equal("streamed histogram preserves foreground count", int(histogram[100]), 5 * 6 * 7)
    check.equal("Otsu separates a two-level volume", otsu_threshold_from_histogram(histogram), 0.0)
    check.raises(
        "empty histogram cannot produce Otsu", TIFFMeshError,
        otsu_threshold_from_histogram, np.zeros(8, dtype=np.uint64),
    )

    profile = foreground_profile(volume, 50, chunk_depth=2, padding=1)
    check.equal("foreground voxel count is exact", profile.foreground_voxels, 5 * 6 * 7)
    check.equal("foreground crop includes requested padding", profile.bounds, BoundsZYX((1, 2, 3), (8, 10, 12)))
    check.check("surface transition estimate is positive", profile.axis_transition_faces > 0)
    check.equal("triangle estimate is twice transitions", profile.estimated_triangles, 2 * profile.axis_transition_faces)
    validate_foreground_profile(profile)
    check.check("plausible sparse foreground passes quality gate", True)
    mostly_full = np.ones((5, 5, 5), dtype=np.uint8)
    too_dense = foreground_profile(mostly_full, 0, padding=0)
    check.raises("dense threshold is rejected", TIFFMeshError, validate_foreground_profile, too_dense)
    check.raises("empty threshold is rejected", TIFFMeshError, foreground_profile, volume, 1000)

    resources = estimate_resources(profile)
    check.check("PLY estimate includes vertices and triangles", resources.estimated_ply_bytes > 0)
    validate_resources(resources, free_disk_bytes=resources.required_free_disk_bytes)
    check.check("exact disk requirement passes", True)
    check.raises(
        "insufficient disk is rejected", TIFFMeshError, validate_resources,
        resources, free_disk_bytes=resources.required_free_disk_bytes - 1,
    )

    mesh_one = extract_surface_slabbed(
        volume, 50, BoundsZYX((0, 0, 0), volume.shape), slab_depth=20
    )
    mesh_many = extract_surface_slabbed(
        volume, 50, BoundsZYX((0, 0, 0), volume.shape), slab_depth=2
    )
    check.check("binary cuboid creates a nonempty closed surface", mesh_one.face_count > 0)
    check.equal("slab extraction preserves vertex count", mesh_many.vertex_count, mesh_one.vertex_count)
    check.equal("slab extraction preserves face count", mesh_many.face_count, mesh_one.face_count)
    check.check(
        "slab extraction preserves triangle geometry",
        triangle_signature(mesh_many) == triangle_signature(mesh_one),
    )
    check.check("shared slab vertices are actually reused", mesh_many.seam_vertices_reused > 0)
    check.equal("ZYX is converted to expected XYZ minimum", mesh_one.bounds_min_xyz, (3.5, 2.5, 1.5))
    check.equal("ZYX is converted to expected XYZ maximum", mesh_one.bounds_max_xyz, (10.5, 8.5, 6.5))

    scaled = extract_surface_slabbed(
        volume, 50, BoundsZYX((0, 0, 0), volume.shape), slab_depth=3,
        voxel_spacing_xyz=(2, 3, 4),
    )
    check.equal("XYZ voxel spacing scales minimum", scaled.bounds_min_xyz, (7.0, 7.5, 6.0))
    check.equal("XYZ voxel spacing scales maximum", scaled.bounds_max_xyz, (21.0, 25.5, 26.0))
    check.raises(
        "nonpositive spacing is rejected", ValueError, extract_surface_slabbed,
        volume, 50, BoundsZYX((0, 0, 0), volume.shape), voxel_spacing_xyz=(1, 0, 1),
    )

    disconnected = volume.copy()
    disconnected[8, 1, 1] = 100
    disconnected_mesh = extract_surface_slabbed(
        disconnected, 50, BoundsZYX((0, 0, 0), disconnected.shape), slab_depth=2
    )
    check.check("disconnected material is preserved by default", disconnected_mesh.bounds_min_xyz[0] < mesh_one.bounds_min_xyz[0])

    single = np.zeros((5, 5, 5), dtype=np.uint8)
    single[2, 2, 2] = 1
    single_mesh = extract_surface_slabbed(
        single, 0.5, BoundsZYX((0, 0, 0), single.shape), slab_depth=1
    )
    check.check("single foreground voxel produces a surface", single_mesh.face_count > 0)

    check.equal("automatic threshold parser remains symbolic", parse_threshold("AUTO"), "auto")
    check.equal("explicit threshold parser returns float", parse_threshold("123.5"), 123.5)
    check.equal("spacing parser uses XYZ order", parse_spacing("2,3,4"), (2.0, 3.0, 4.0))

    with tempfile.TemporaryDirectory(prefix="tiff_mesh_tests_") as temporary:
        base = Path(temporary)
        ply_path = base / "cube.ply"
        write_binary_ply(ply_path, mesh_many, comments=("synthetic cube",))
        metadata = inspect_binary_ply(ply_path)
        check.equal("PLY header vertex count is correct", metadata.vertex_count, mesh_many.vertex_count)
        check.equal("PLY header face count is correct", metadata.face_count, mesh_many.face_count)
        check.equal("PLY payload bounds are correct", metadata.bounds_min_xyz, mesh_many.bounds_min_xyz)
        check.check("binary PLY has a nontrivial payload", metadata.bytes > 1024)
        check.equal(
            "new PLY uses normal user-readable permissions",
            stat.S_IMODE(ply_path.stat().st_mode), 0o644,
        )

        truncated = base / "truncated.ply"
        truncated.write_bytes(ply_path.read_bytes()[:-7])
        check.raises("truncated PLY is rejected", TIFFMeshError, inspect_binary_ply, truncated)

        invalid_mesh = MeshChunks(
            vertices_xyz=(np.zeros((3, 3), dtype=np.float32),),
            faces=(np.array([[0, 1, 3]], dtype=np.uint32),),
            vertex_count=3,
            face_count=1,
            bounds_min_xyz=(0.0, 0.0, 0.0),
            bounds_max_xyz=(0.0, 0.0, 0.0),
            slabs_processed=1,
            seam_vertices_reused=0,
        )
        check.raises(
            "face index outside vertex payload is rejected", TIFFMeshError,
            write_binary_ply, base / "invalid.ply", invalid_mesh,
        )

        tiff_path = base / "fixture.tiff"
        fixture = np.zeros((12, 15, 18), dtype=np.uint16)
        fixture[3:9, 5:10, 6:12] = 1000
        tifffile.imwrite(tiff_path, fixture, imagej=True, metadata={"axes": "ZYX"})
        converted = base / "converted.ply"
        manifest = convert_tiff_to_ply(
            tiff_path, converted, threshold_spec=500,
            histogram_chunk_depth=2, slab_depth=2,
        )
        check.check("end-to-end TIFF conversion creates PLY", converted.is_file())
        check.check("end-to-end conversion creates preflight", converted.with_suffix(".preflight.json").is_file())
        check.check("end-to-end conversion creates manifest", converted.with_suffix(".manifest.json").is_file())
        check.check("end-to-end conversion creates threshold preview", converted.with_suffix(".threshold_preview.png").is_file())
        saved_manifest = json.loads(converted.with_suffix(".manifest.json").read_text())
        check.equal("manifest records explicit threshold", saved_manifest["threshold"]["value"], 500.0)
        check.equal("end-to-end result passes payload validation", manifest["validation"]["header_and_payload_re_read"], "passed")

        preflight_only = base / "preflight_only.ply"
        convert_tiff_to_ply(tiff_path, preflight_only, threshold_spec=500, preflight_only=True)
        check.check("preflight-only does not create a mesh", not preflight_only.exists())
        check.check("preflight-only still saves evidence", preflight_only.with_suffix(".preflight.json").is_file())
        check.check("preflight-only saves threshold overlay", preflight_only.with_suffix(".threshold_preview.png").is_file())

    impossible = ResourceEstimate(10, 10, 10, 10, 10_000)
    check.raises(
        "synthetic low-disk estimate fails before allocation", TIFFMeshError,
        validate_resources, impossible, free_disk_bytes=9_999,
    )
    return check.done()


if __name__ == "__main__":
    finish(run())
