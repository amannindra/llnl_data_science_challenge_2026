#!/usr/bin/env python3
"""Convert a lattice JSON into MeshLab-viewable 3D geometry and open it.

MeshLab has no JSON importer, so the design lattice is rebuilt as surface
geometry: one capped polygonal tube per welded strut, plus an optional point
layer marking the welded physical junctions.  Both are written next to a
``.mlp`` project so MeshLab opens them together as one scene.

Registered lattice JSONs are already expressed in CT native XYZ voxel units,
so every length below is a voxel count.  The default strut radius is derived
from the JSON's own ``thickness`` field times the measured unit-cell pitch;
pass ``--radius-voxels`` to override it with an independent number.

Example
-------
    conda run -n DSC python Aman_Scripts/view_lattice_in_meshlab.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Aman_Scripts.Components.lattice_graph import (  # noqa: E402
    LatticeGraph,
    WeldedGraph,
    load_lattice_graph,
    summarize_components,
    weld_coincident_nodes,
)
from Aman_Scripts.Components.lattice_mesh import (  # noqa: E402
    ProjectLayer,
    colored_vertices,
    strut_tube_mesh,
    write_mesh_ply,
    write_meshlab_project,
    write_points_ply,
)
from Aman_Scripts.Components.paths import data_path, output_path  # noqa: E402
from Aman_Scripts.Components.reporting import build_manifest, write_json  # noqa: E402


DEFAULT_LATTICE = ("missing_struts", "registered_jsons",
                   "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
# "Aman_Scripts/outputs/meshlab/" is already gitignored, so generated geometry
# stays out of version control without a new ignore rule.
DEFAULT_OUTPUT_DIRECTORY = "meshlab/lattice_view"
STRUT_COLOR = (176, 182, 192)
NODE_COLOR = (232, 106, 70)
VOXEL_PITCH_MICRONS = 58.1


def unit_cell_pitch(graph: LatticeGraph) -> float | None:
    """Estimate the unit-cell pitch from the junction extent and cell indices.

    Returns ``None`` when the payload carries no indexed unit cells, which is
    the only case where the cell count along each axis is unknown.
    """

    indexed = [cell.indices for cell in graph.unit_cells if cell.indices is not None]
    if not indexed or not graph.junctions:
        return None
    cell_indices = np.asarray(indexed, dtype=np.int64)
    cells_per_axis = cell_indices.max(axis=0) - cell_indices.min(axis=0) + 1
    positions = np.asarray([junction.position for junction in graph.junctions], dtype=np.float64)
    span = positions.max(axis=0) - positions.min(axis=0)
    usable = cells_per_axis > 0
    if not usable.any():
        return None
    return float(np.mean(span[usable] / cells_per_axis[usable]))


def default_radius(graph: LatticeGraph) -> tuple[float | None, str]:
    """Derive a strut radius in position units from the payload's own fields."""

    thicknesses = [
        strut.thickness for strut in graph.struts
        if strut.thickness is not None and strut.thickness > 0
    ]
    pitch = unit_cell_pitch(graph)
    if not thicknesses or pitch is None:
        return None, "unavailable: payload lacks positive thickness or indexed unit cells"
    thickness = float(np.median(thicknesses))
    radius = 0.5 * thickness * pitch
    return radius, (
        f"0.5 * median JSON thickness {thickness:g} * unit-cell pitch {pitch:.4f} voxels"
    )


def node_arrays(welded: WeldedGraph) -> tuple[np.ndarray, np.ndarray]:
    """Return welded node XYZ positions and the integer endpoint-index edge list."""

    positions = np.asarray([node.position for node in welded.nodes], dtype=np.float64)
    edges = np.asarray(
        [(strut.node0, strut.node1) for strut in welded.struts], dtype=np.int64
    ).reshape(-1, 2)
    return positions, edges


def find_meshlab() -> str | None:
    """Locate a MeshLab launcher without assuming a version-pinned app name."""

    for executable in ("meshlab", "meshlabserver"):
        found = shutil.which(executable)
        if found:
            return found
    if platform.system() == "Darwin":
        bundles = sorted(Path("/Applications").glob("[Mm]esh[Ll]ab*.app"))
        if bundles:
            return str(bundles[-1])
    return None


def open_in_meshlab(mesh_file: Path) -> tuple[bool, str]:
    """Launch MeshLab on a mesh file; never fail the export if it cannot.

    This deliberately opens the ``.ply`` rather than the ``.mlp``.  MeshLab
    reaches a command-line or double-clicked path through its mesh importer,
    which rejects a project file as an unsupported format; projects load only
    from *File -> Open Project*.
    """

    if mesh_file.suffix.lower() == ".mlp":
        raise ValueError("open the mesh file, not the project; MeshLab imports .mlp only via its menu")
    launcher = find_meshlab()
    if launcher is None:
        return False, "MeshLab was not found on this machine"
    try:
        if launcher.endswith(".app"):
            subprocess.run(["open", "-a", launcher, str(mesh_file)], check=True)
        else:
            subprocess.Popen(
                [launcher, str(mesh_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (OSError, subprocess.CalledProcessError) as error:
        return False, f"launching {launcher} failed: {error}"
    return True, launcher


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lattice", type=Path, default=None,
                        help="lattice JSON to view (default: registered missing-struts JSON)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help=f"output directory (default: Aman_Scripts/outputs/{DEFAULT_OUTPUT_DIRECTORY})")
    parser.add_argument("--radius-voxels", type=float, default=None,
                        help="strut radius in position units (default: from JSON thickness x cell pitch)")
    parser.add_argument("--radial-segments", type=int, default=8,
                        help="cross-section polygon sides per strut (default: 8)")
    parser.add_argument("--weld-tolerance", type=float, default=1e-6,
                        help="XYZ tolerance for welding coincident junctions (default: 1e-6)")
    parser.add_argument("--tolerant", action="store_true",
                        help="recover records from a damaged JSON and skip reference checks")
    parser.add_argument("--no-nodes", action="store_true",
                        help="skip the welded-junction point layer")
    parser.add_argument("--no-open", action="store_true",
                        help="write the files without launching MeshLab")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    lattice = args.lattice if args.lattice is not None else data_path(*DEFAULT_LATTICE)
    lattice = Path(lattice).expanduser().resolve()
    directory = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir is not None
        else output_path(DEFAULT_OUTPUT_DIRECTORY, create=True)
    )
    directory.mkdir(parents=True, exist_ok=True)

    print(f"reading  {lattice}")
    graph = load_lattice_graph(
        lattice, strict_references=not args.tolerant, tolerant=args.tolerant
    )
    welded = weld_coincident_nodes(graph, tolerance=args.weld_tolerance)
    components = summarize_components(welded)
    print(
        f"parsed   {len(graph.junctions)} junctions, {len(graph.struts)} struts"
        f" -> {len(welded.nodes)} welded nodes, {len(welded.struts)} welded struts"
    )
    print(
        f"connect  {components.component_count} component(s),"
        f" largest holds {components.largest_component_fraction:.4%} of nodes"
    )

    derived_radius, radius_note = default_radius(graph)
    if args.radius_voxels is not None:
        radius = float(args.radius_voxels)
        radius_note = "supplied via --radius-voxels"
    elif derived_radius is not None:
        radius = derived_radius
    else:
        raise SystemExit(f"cannot derive a strut radius ({radius_note}); pass --radius-voxels")
    print(
        f"radius   {radius:.4f} position units"
        f" (~{2 * radius * VOXEL_PITCH_MICRONS:.1f} um diameter at {VOXEL_PITCH_MICRONS} um/voxel)"
        f"  [{radius_note}]"
    )

    positions, edges = node_arrays(welded)
    mesh = strut_tube_mesh(
        positions,
        edges,
        radius=radius,
        radial_segments=args.radial_segments,
        color_rgb=STRUT_COLOR,
    )
    print(f"meshed   {mesh.strut_count} tubes -> {mesh.vertex_count} vertices, {mesh.face_count} triangles")

    stem = "lattice_struts"
    strut_ply = write_mesh_ply(
        directory / f"{stem}.ply",
        mesh,
        comments=(
            f"source {lattice.name}",
            f"welded struts {len(welded.struts)} from {len(graph.struts)} source records",
            f"strut radius {radius:.6f} position units ({radius_note})",
            "coordinates are the lattice JSON XYZ frame (CT native voxels when registered)",
        ),
    )
    layers = [ProjectLayer(strut_ply, f"struts ({mesh.strut_count})")]

    node_ply: Path | None = None
    if not args.no_nodes:
        node_ply = write_points_ply(
            directory / "lattice_nodes.ply",
            colored_vertices(positions, color_rgb=NODE_COLOR),
            comments=(
                f"source {lattice.name}",
                f"welded physical junctions {len(welded.nodes)}"
                f" from {len(graph.junctions)} source records",
            ),
        )
        layers.append(ProjectLayer(node_ply, f"welded nodes ({len(welded.nodes)})"))

    project = write_meshlab_project(directory / "lattice.mlp", layers)
    written = [strut_ply, project] + ([node_ply] if node_ply is not None else [])
    manifest = {
        "source_lattice": str(lattice),
        "source_junctions": len(graph.junctions),
        "source_struts": len(graph.struts),
        "welded_nodes": len(welded.nodes),
        "welded_struts": len(welded.struts),
        "weld_tolerance": args.weld_tolerance,
        "self_loop_strut_ids": list(welded.self_loop_strut_ids),
        "dangling_strut_ids": list(welded.dangling_strut_ids),
        "component_count": components.component_count,
        "largest_component_fraction": components.largest_component_fraction,
        "unit_cell_pitch_voxels": unit_cell_pitch(graph),
        "strut_radius_voxels": radius,
        "strut_radius_provenance": radius_note,
        "strut_diameter_microns": 2 * radius * VOXEL_PITCH_MICRONS,
        "radial_segments": mesh.radial_segments,
        "mesh_vertices": mesh.vertex_count,
        "mesh_triangles": mesh.face_count,
        "files": build_manifest(written, root=directory),
    }
    write_json(directory / "manifest.json", manifest)

    print(f"wrote    {directory}")
    for path in sorted(written):
        print(f"         {path.name}  ({path.stat().st_size:,} bytes)")
    if node_ply is not None:
        print(f"note     load both layers together with MeshLab File > Open Project on {project.name}")

    if args.no_open:
        print("skipped  MeshLab launch (--no-open)")
        return 0
    launched, detail = open_in_meshlab(strut_ply)
    print(f"opened   {strut_ply.name} in {detail}" if launched
          else f"warning  {detail}; open {strut_ply} manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
