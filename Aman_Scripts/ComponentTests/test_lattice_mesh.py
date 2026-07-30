#!/usr/bin/env python3
"""Deterministic adversarial checks for ``Components.lattice_mesh``."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Aman_Scripts.Components.lattice_mesh import (  # noqa: E402
    MESH_VERTEX_DTYPE,
    ProjectLayer,
    TubeMesh,
    colored_vertices,
    strut_tube_mesh,
    write_mesh_ply,
    write_meshlab_project,
    write_points_ply,
)


class Checker:
    def __init__(self) -> None:
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        passed = bool(condition)
        self.results.append({"name": name, "passed": passed, "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    def raises(self, name: str, exception: type[BaseException], function) -> None:
        try:
            function()
        except exception:
            self.check(name, True)
        except Exception as exc:  # noqa: BLE001 - test must report wrong exception
            self.check(name, False, f"wrong exception {type(exc).__name__}: {exc}")
        else:
            self.check(name, False, "no exception")

    def finish(self) -> int:
        passed = sum(bool(item["passed"]) for item in self.results)
        summary = {"suite": "lattice_mesh", "passed": passed,
                   "failed": len(self.results) - passed,
                   "total": len(self.results), "results": self.results}
        print(json.dumps(summary, sort_keys=True))
        return 0 if passed == len(self.results) and len(self.results) >= 20 else 1


def xyz(mesh: TubeMesh) -> np.ndarray:
    return np.stack(
        [mesh.vertices["x"], mesh.vertices["y"], mesh.vertices["z"]], axis=1
    ).astype(np.float64)


def edge_multiplicity(faces: np.ndarray) -> set[int]:
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.sort(edges, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return set(counts.tolist())


def enclosed_volume(points: np.ndarray, faces: np.ndarray) -> float:
    triangles = points[faces]
    return float(
        (np.cross(triangles[:, 0], triangles[:, 1]) * triangles[:, 2]).sum(1).sum() / 6.0
    )


def read_ply(path: Path) -> tuple[dict[str, int], np.ndarray, np.ndarray | None]:
    """Parse a binary_little_endian PLY from scratch, independent of the writer."""

    raw = path.read_bytes()
    marker = b"end_header\n"
    end = raw.index(marker) + len(marker)
    header = raw[:end].decode("ascii").splitlines()
    if header[0] != "ply" or header[1] != "format binary_little_endian 1.0":
        raise ValueError("unexpected PLY preamble")
    counts: dict[str, int] = {}
    order: list[str] = []
    for line in header:
        if line.startswith("element "):
            _, name, number = line.split()
            counts[name] = int(number)
            order.append(name)
    body = raw[end:]
    offset = 0
    vertices = np.empty(0, dtype=MESH_VERTEX_DTYPE)
    faces: np.ndarray | None = None
    for name in order:
        total = counts[name]
        if name == "vertex":
            vertices = np.frombuffer(
                body, dtype=MESH_VERTEX_DTYPE, count=total, offset=offset
            )
            offset += total * MESH_VERTEX_DTYPE.itemsize
        elif name == "face":
            faces = np.empty((total, 3), dtype=np.int64)
            for index in range(total):
                if body[offset] != 3:
                    raise ValueError(f"face {index} is not a triangle")
                offset += 1
                faces[index] = struct.unpack_from("<3i", body, offset)
                offset += 12
    if offset != len(body):
        raise ValueError(f"{len(body) - offset} trailing bytes")
    return counts, vertices, faces


def main() -> int:
    checks = Checker()
    positions = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]])
    edges = np.array([[0, 1]], dtype=np.int64)

    # ---- input validation -------------------------------------------------
    checks.raises("node_positions with wrong shape is rejected", ValueError,
                  lambda: strut_tube_mesh(np.zeros((4, 2)), edges, radius=1.0))
    checks.raises("non-finite node_positions are rejected", ValueError,
                  lambda: strut_tube_mesh(np.array([[0.0, 0.0, np.nan], [1.0, 0.0, 0.0]]),
                                          edges, radius=1.0))
    checks.raises("edges with wrong shape are rejected", ValueError,
                  lambda: strut_tube_mesh(positions, np.zeros((3, 3), dtype=np.int64),
                                          radius=1.0))
    checks.raises("float edge indices are rejected", ValueError,
                  lambda: strut_tube_mesh(positions, np.array([[0.0, 1.0]]), radius=1.0))
    checks.raises("out-of-range edge index is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, np.array([[0, 7]]), radius=1.0))
    checks.raises("negative edge index is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, np.array([[-1, 1]]), radius=1.0))
    checks.raises("zero radius is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=0.0))
    checks.raises("non-finite radius is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=float("inf")))
    checks.raises("radial_segments below three is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=1.0, radial_segments=2))
    checks.raises("fractional radial_segments is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=1.0, radial_segments=6.5))
    checks.raises("out-of-range color channel is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=1.0, color_rgb=(0, 0, 300)))
    checks.raises("two-channel color is rejected", ValueError,
                  lambda: strut_tube_mesh(positions, edges, radius=1.0, color_rgb=(1, 2)))

    # ---- degenerate and empty inputs --------------------------------------
    empty = strut_tube_mesh(positions, np.empty((0, 2), dtype=np.int64), radius=1.0)
    checks.check("empty edge list yields an empty, correctly typed mesh",
                 empty.vertex_count == 0 and empty.face_count == 0
                 and empty.vertices.dtype == MESH_VERTEX_DTYPE,
                 f"vertices={empty.vertex_count}, faces={empty.face_count}")
    collapsed = strut_tube_mesh(np.array([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]),
                                np.array([[0, 1]]), radius=1.0)
    checks.check("zero-length strut is dropped rather than emitted as degenerate",
                 collapsed.strut_count == 0 and collapsed.face_count == 0,
                 f"strut_count={collapsed.strut_count}")

    # ---- geometry ----------------------------------------------------------
    segments = 6
    mesh = strut_tube_mesh(positions, edges, radius=2.0, radial_segments=segments)
    checks.check("vertex and face counts match the capped closed form",
                 (mesh.vertex_count, mesh.face_count) == (2 * segments + 2, 4 * segments),
                 f"vertices={mesh.vertex_count}, faces={mesh.face_count}")
    points = xyz(mesh)
    checks.check("capped tube is watertight (every edge shared by two faces)",
                 edge_multiplicity(mesh.faces) == {2},
                 f"multiplicities={sorted(edge_multiplicity(mesh.faces))}")
    triangles = points[mesh.faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    centroid = points.mean(axis=0)
    outward = (normals * (triangles.mean(1) - centroid)).sum(1)
    checks.check("every capped-tube face winds outward",
                 bool((outward > 0).all()), f"min dot={outward.min():.6f}")
    checks.check("no degenerate zero-area triangles",
                 bool((np.linalg.norm(normals, axis=1) > 0).all()))
    expected = 0.5 * segments * np.sin(2 * np.pi / segments) * 4.0 * 10.0
    volume = enclosed_volume(points, mesh.faces)
    checks.check("enclosed volume matches the analytic prism volume",
                 abs(volume - expected) < 1e-6 * expected,
                 f"volume={volume:.6f}, expected={expected:.6f}")
    radial = np.linalg.norm(points[:2 * segments, :2], axis=1)
    checks.check("ring vertices sit exactly on the requested radius",
                 bool(np.abs(radial - 2.0).max() < 1e-5),
                 f"max radial error={np.abs(radial - 2.0).max():.3e}")

    open_mesh = strut_tube_mesh(positions, edges, radius=2.0,
                                radial_segments=segments, capped=False)
    checks.check("uncapped tube drops the cap fan and leaves open boundary edges",
                 open_mesh.face_count == 2 * segments
                 and 1 in edge_multiplicity(open_mesh.faces),
                 f"faces={open_mesh.face_count}")

    axis_aligned = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0],
                             [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]])
    triple = strut_tube_mesh(axis_aligned, np.array([[0, 1], [0, 2], [0, 3]]), radius=1.0)
    checks.check("axis-aligned struts on X, Y and Z all get a finite basis",
                 bool(np.isfinite(xyz(triple)).all()) and triple.strut_count == 3)

    scaled = strut_tube_mesh(positions, edges, radius=2.0, radial_segments=64)
    circle = 0.5 * 64 * np.sin(2 * np.pi / 64) * 4.0 * 10.0
    checks.check("refining radial_segments converges toward the true cylinder volume",
                 abs(enclosed_volume(xyz(scaled), scaled.faces) - circle) < 1e-4 * circle
                 and circle > expected,
                 f"64-gon={circle:.4f} > 6-gon={expected:.4f}")

    # ---- serialization -----------------------------------------------------
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        target = directory / "mesh.ply"
        write_mesh_ply(target, mesh, comments=("line one\nline two", "plain"))
        counts, vertices, faces = read_ply(target)
        checks.check("mesh PLY round-trips through an independent reader",
                     counts == {"vertex": mesh.vertex_count, "face": mesh.face_count}
                     and faces is not None and np.array_equal(faces, mesh.faces),
                     f"counts={counts}")
        checks.check("PLY vertex payload preserves float32 coordinates",
                     bool(np.allclose(
                         np.stack([vertices["x"], vertices["y"], vertices["z"]], 1),
                         points, atol=1e-5)))
        text = target.read_bytes().split(b"end_header")[0].decode("ascii")
        checks.check("embedded newlines in comments cannot forge header lines",
                     "comment line one line two" in text
                     and text.count("comment") == 3, text.count("comment"))
        first = target.read_bytes()
        write_mesh_ply(target, mesh, comments=("line one\nline two", "plain"))
        checks.check("repeated writes are byte-identical", target.read_bytes() == first)

        checks.raises("write_mesh_ply rejects a non-TubeMesh", TypeError,
                      lambda: write_mesh_ply(directory / "bad.ply", object()))
        checks.raises("write_points_ply rejects a wrongly typed array", ValueError,
                      lambda: write_points_ply(directory / "bad.ply", np.zeros((4, 3))))
        checks.raises("colored_vertices rejects non-(N,3) input", ValueError,
                      lambda: colored_vertices(np.zeros((4, 2)), color_rgb=(1, 2, 3)))
        checks.raises("colored_vertices rejects non-finite input", ValueError,
                      lambda: colored_vertices(np.array([[0.0, 0.0, np.inf]]),
                                               color_rgb=(1, 2, 3)))

        cloud = colored_vertices(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
                                 color_rgb=(10, 20, 30))
        point_file = write_points_ply(directory / "points.ply", cloud)
        point_counts, point_vertices, point_faces = read_ply(point_file)
        checks.check("point PLY writes a vertex-only element with colors",
                     point_counts == {"vertex": 2} and point_faces is None
                     and int(point_vertices["green"][1]) == 20,
                     f"counts={point_counts}")

        project = write_meshlab_project(
            directory / "scene.mlp",
            [ProjectLayer(target, 'struts "A"'), ProjectLayer(point_file, "nodes")],
        )
        body = project.read_text()
        checks.check("project references siblings by bare filename and stays well formed",
                     'filename="mesh.ply"' in body and 'filename="points.ply"' in body
                     and "<!DOCTYPE MeshLabDocument>" in body
                     and str(directory) not in body)
        checks.check("project label quoting cannot break the XML attribute",
                     "label=\"struts 'A'\"" in body)
        checks.raises("project rejects a layer outside its own directory", ValueError,
                      lambda: write_meshlab_project(
                          directory / "scene.mlp",
                          [ProjectLayer(directory / "nested" / "m.ply", "x")]))
        checks.raises("project rejects an empty layer list", ValueError,
                      lambda: write_meshlab_project(directory / "empty.mlp", []))

    # ---- real registered lattice ------------------------------------------
    registered = (ROOT / "data" / "missing_struts" / "registered_jsons"
                  / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
    if registered.exists():
        from Aman_Scripts.Components.lattice_graph import (
            load_lattice_graph, weld_coincident_nodes,
        )

        welded = weld_coincident_nodes(load_lattice_graph(registered), tolerance=1e-6)
        node_xyz = np.asarray([node.position for node in welded.nodes], dtype=np.float64)
        edge_pairs = np.asarray(
            [(strut.node0, strut.node1) for strut in welded.struts], dtype=np.int64
        )
        real = strut_tube_mesh(node_xyz, edge_pairs, radius=3.9717, radial_segments=8)
        checks.check("real 9x9x9 lattice meshes all 18,468 welded struts",
                     real.strut_count == 18468
                     and (real.vertex_count, real.face_count) == (18468 * 18, 18468 * 32),
                     f"struts={real.strut_count}, vertices={real.vertex_count}, "
                     f"faces={real.face_count}")
        checks.check("real lattice mesh is watertight",
                     edge_multiplicity(real.faces) == {2})
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
