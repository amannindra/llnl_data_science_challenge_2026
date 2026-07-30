"""MCP server exposing lattice-JSON to binary-STL conversion for MeshLab.

A registered lattice JSON is a graph of junction positions and strut endpoint
references, so MeshLab cannot open it directly. ``lattice_json_to_stl`` sweeps
every strut into a capped cylinder and writes one binary STL.

Run over stdio::

    conda run -n DSC python Aman_src/lattice_stl_mcp.py
"""

import json
import os
import sys

from fastmcp import FastMCP

# Make the repository root importable so ``Aman_Scripts.Components`` resolves
# whether this file is run as a script or loaded by absolute path.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_REPOSITORY_DIR = os.path.dirname(_SRC_DIR)
if _REPOSITORY_DIR not in sys.path:
    sys.path.insert(0, _REPOSITORY_DIR)

from Aman_Scripts.Components.lattice_graph import load_lattice_graph
from Aman_Scripts.Components.lattice_stl import lattice_to_stl

mcp = FastMCP("Lattice STL")


@mcp.tool()
def lattice_json_to_stl(
    json_filepath: str,
    output_filepath: str,
    radius: float = 3.0,
    segments: int = 12,
    tolerant: bool = False,
) -> str:
    """Convert a registered lattice JSON into a binary STL of strut tubes.

    Each strut becomes a capped cylinder of ``radius`` voxels built from
    ``segments`` sides, so the result is viewable in MeshLab. The nominal
    challenge strut radius is about 3.0 voxels (350 um at 58.1 um pitch);
    smaller values render a thin wireframe-style lattice.

    Coordinates are passed through unchanged in native CT XYZ voxel units.
    Struts whose endpoints are missing, non-finite, or coincident are skipped
    and reported rather than aborting the conversion.

    Set ``tolerant`` only for the deliberately damaged project copy: it
    recovers intact records after a JSON syntax error and disables cross
    reference checks.
    """

    if not os.path.isfile(json_filepath):
        return f"Error: lattice JSON not found: '{json_filepath}'."
    if not output_filepath.lower().endswith(".stl"):
        return f"Error: output_filepath must end in .stl, got '{output_filepath}'."
    try:
        graph = load_lattice_graph(
            json_filepath, strict_references=not tolerant, tolerant=tolerant
        )
    except Exception as exc:  # noqa: BLE001 - report any failure to the agent as text
        return f"Error: could not parse '{json_filepath}': {exc}"
    try:
        result = lattice_to_stl(
            graph, output_filepath, radius=radius, segments=segments
        )
    except Exception as exc:  # noqa: BLE001 - report any failure to the agent as text
        return f"Error: STL export failed: {exc}"

    skipped = result["skipped_strut_count"]
    note = f" Skipped {skipped} unusable strut(s)." if skipped else ""
    return (
        f"Wrote {result['stl']} "
        f"({result['triangle_count']} triangles, {result['bytes']} bytes) from "
        f"{result['drawn_strut_count']} of {result['strut_count']} struts and "
        f"{result['junction_count']} junctions. "
        f"radius={result['radius_voxels']} voxels, segments={result['segments']}. "
        f"Bounds XYZ {result['bounds_min_xyz']} to {result['bounds_max_xyz']} "
        f"(native CT voxels).{note} Open it in MeshLab."
    )


@mcp.tool()
def inspect_lattice_json(json_filepath: str, tolerant: bool = False) -> str:
    """Report junction, strut, and unit-cell counts for a lattice JSON.

    Use before converting to confirm the file parses and to size the output.
    """

    if not os.path.isfile(json_filepath):
        return f"Error: lattice JSON not found: '{json_filepath}'."
    try:
        graph = load_lattice_graph(
            json_filepath, strict_references=not tolerant, tolerant=tolerant
        )
    except Exception as exc:  # noqa: BLE001 - report any failure to the agent as text
        return f"Error: could not parse '{json_filepath}': {exc}"
    summary = {
        "junction_count": len(graph.junctions),
        "strut_count": len(graph.struts),
        "unit_cell_count": len(graph.unit_cells),
        "bytes": os.path.getsize(json_filepath),
    }
    return json.dumps(summary, indent=2)


if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default).
    mcp.run()
