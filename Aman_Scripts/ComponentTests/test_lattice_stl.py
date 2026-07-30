#!/usr/bin/env python3
"""Deterministic adversarial checks for ``Components.lattice_stl``."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Aman_Scripts.Components.asset_io import inspect_stl  # noqa: E402
from Aman_Scripts.Components.lattice_graph import (  # noqa: E402
    load_lattice_graph,
    parse_lattice_graph,
)
from Aman_Scripts.Components.lattice_stl import (  # noqa: E402
    STL_HEADER_BYTES,
    STL_TRIANGLE_DTYPE,
    LatticeSTLError,
    binary_stl_bytes,
    cylinder_triangles,
    lattice_to_stl,
    strut_endpoints,
    triangle_normals,
    write_binary_stl,
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
        summary = {"suite": "lattice_stl", "passed": passed,
                   "failed": len(self.results) - passed,
                   "total": len(self.results), "results": self.results}
        print(json.dumps(summary, sort_keys=True))
        return 0 if passed == len(self.results) and len(self.results) >= 12 else 1


def fixture() -> dict[str, object]:
    """Three junctions forming two struts, one of them zero length."""

    return {
        "format": "synthetic-test",
        "junctions": [
            {"id": 0, "position": [0.0, 0.0, 0.0]},
            {"id": 1, "position": [10.0, 0.0, 0.0]},
            {"id": 2, "position": [10.0, 0.0, 0.0]},
        ],
        "struts": [
            {"id": 0, "junction0": 0, "junction1": 1},
            {"id": 1, "junction0": 1, "junction1": 2},
        ],
        "unit_cells": [],
    }


def main() -> int:
    checks = Checker()

    # --- Packing: a mis-sized record silently corrupts every STL written. ---
    checks.check("binary STL triangle record packs to exactly 50 bytes",
                 STL_TRIANGLE_DTYPE.itemsize == 50,
                 f"itemsize={STL_TRIANGLE_DTYPE.itemsize}")

    starts = np.array([[0.0, 0.0, 0.0]])
    ends = np.array([[0.0, 0.0, 10.0]])

    triangles = cylinder_triangles(starts, ends, 2.0, segments=8)
    checks.check("one strut at 8 segments yields 4*segments triangles",
                 triangles.shape == (32, 3, 3), f"shape={triangles.shape}")

    two = cylinder_triangles(
        np.vstack((starts, starts)), np.vstack((ends, ends + 5.0)), 2.0, segments=6
    )
    checks.check("triangle count scales linearly with strut count",
                 two.shape == (48, 3, 3), f"shape={two.shape}")

    checks.check("empty input returns an empty (0, 3, 3) array",
                 cylinder_triangles(np.empty((0, 3)), np.empty((0, 3)), 1.0).shape
                 == (0, 3, 3))

    checks.raises("segments below six is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, ends, 1.0, segments=5))
    checks.raises("non-integer segments is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, ends, 1.0, segments=8.5))
    checks.raises("zero radius is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, ends, 0.0))
    checks.raises("negative radius is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, ends, -1.0))
    checks.raises("non-finite radius is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, ends, float("nan")))
    checks.raises("coincident endpoints are rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, starts.copy(), 1.0))
    checks.raises("non-finite endpoint is rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, np.array([[np.inf, 0.0, 0.0]]), 1.0))
    checks.raises("mismatched start/end shapes are rejected", LatticeSTLError,
                  lambda: cylinder_triangles(starts, np.vstack((ends, ends)), 1.0))

    # --- Normals must be unit length and face away from the strut axis. ---
    normals = triangle_normals(triangles)
    lengths = np.linalg.norm(normals, axis=1)
    checks.check("every face normal is unit length",
                 bool(np.allclose(lengths, 1.0, atol=1e-6)),
                 f"min={lengths.min():.6f}, max={lengths.max():.6f}")

    # The first 2*segments triangles are the side wall; their normals should
    # have no axial component and point radially outward from the Z axis.
    side = triangles[: 2 * 8]
    side_normals = triangle_normals(side)
    centroids = side.mean(axis=1)
    radial = centroids.copy()
    radial[:, 2] = 0.0
    radial /= np.linalg.norm(radial, axis=1, keepdims=True)
    outward = np.einsum("ij,ij->i", side_normals, radial)
    checks.check("side-wall normals point outward from the strut axis",
                 bool(np.all(outward > 0.0)), f"min dot={outward.min():.4f}")

    checks.raises("triangle_normals rejects wrong shape", LatticeSTLError,
                  lambda: triangle_normals(np.zeros((4, 3))))
    checks.check("degenerate triangle yields a zero normal, not NaN",
                 bool(np.allclose(triangle_normals(np.zeros((1, 3, 3))), 0.0)))

    # --- Serialized layout must match the binary STL specification. ---
    payload = binary_stl_bytes(triangles, header="unit test")
    checks.check("serialized size is 84 + 50 * triangle_count",
                 len(payload) == 84 + 50 * len(triangles),
                 f"bytes={len(payload)}")
    checks.check("header occupies exactly 80 bytes and is zero padded",
                 payload[:STL_HEADER_BYTES].rstrip(b"\0") == b"unit test")
    checks.check("triangle count field matches the payload",
                 int(np.frombuffer(payload[80:84], dtype="<u4")[0]) == len(triangles))
    checks.check("over-long header is truncated to 80 bytes",
                 len(binary_stl_bytes(triangles, header="x" * 200)) == len(payload))
    checks.raises("binary_stl_bytes rejects wrong shape", LatticeSTLError,
                  lambda: binary_stl_bytes(np.zeros((2, 4, 3))))
    checks.raises("binary_stl_bytes rejects non-finite triangles", LatticeSTLError,
                  lambda: binary_stl_bytes(np.full((1, 3, 3), np.nan)))

    graph = parse_lattice_graph(fixture())
    resolved_starts, resolved_ends, skipped = strut_endpoints(graph)
    checks.check("zero-length strut is skipped and reported",
                 len(resolved_starts) == 1 and skipped == [1],
                 f"drawn={len(resolved_starts)}, skipped={skipped}")

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "nested" / "fixture.stl"
        result = lattice_to_stl(graph, target, radius=1.0, segments=8)
        checks.check("lattice_to_stl creates missing parent directories",
                     target.is_file())
        checks.check("lattice_to_stl reports the skipped degenerate strut",
                     result["drawn_strut_count"] == 1
                     and result["skipped_strut_count"] == 1)

        # Independent cross-check: the project's own STL reader must agree.
        metadata = inspect_stl(target)
        checks.check("project inspect_stl reads the file back as binary STL",
                     metadata.encoding == "binary", f"encoding={metadata.encoding}")
        checks.check("inspect_stl triangle count matches what we wrote",
                     metadata.triangles == result["triangle_count"],
                     f"{metadata.triangles} vs {result['triangle_count']}")
        lower = metadata.bounding_box_min
        upper = metadata.bounding_box_max
        checks.check("STL bounds span the strut length along X",
                     lower is not None and upper is not None
                     and abs(lower[0] - 0.0) < 1e-5 and abs(upper[0] - 10.0) < 1e-5,
                     f"x range {lower[0]:.4f}..{upper[0]:.4f}")
        checks.check("STL radial bounds match the requested radius",
                     abs(upper[1] - 1.0) < 1e-5 and abs(lower[1] + 1.0) < 1e-5,
                     f"y range {lower[1]:.4f}..{upper[1]:.4f}")

        thicker = Path(directory) / "thick.stl"
        thick_result = lattice_to_stl(graph, thicker, radius=4.0, segments=8)
        checks.check("larger radius widens the mesh bounds",
                     thick_result["bounds_max_xyz"][1] > result["bounds_max_xyz"][1],
                     f"{thick_result['bounds_max_xyz'][1]} > {result['bounds_max_xyz'][1]}")

        written = write_binary_stl(Path(directory) / "raw.stl", triangles)
        checks.check("write_binary_stl output is world readable (0644)",
                     (written.stat().st_mode & 0o777) == 0o644,
                     oct(written.stat().st_mode & 0o777))

    empty = parse_lattice_graph(
        {"junctions": [{"id": 0, "position": [0.0, 0.0, 0.0]}], "struts": [],
         "unit_cells": []}
    )
    checks.raises("a lattice with no drawable struts is rejected", LatticeSTLError,
                  lambda: lattice_to_stl(empty, Path(tempfile.gettempdir()) / "x.stl"))

    # --- Real registered asset: counts must match the documented lattice. ---
    registered_path = (ROOT / "data" / "missing_struts" / "registered_jsons"
                       / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
    if registered_path.is_file():
        registered = load_lattice_graph(registered_path)
        with tempfile.TemporaryDirectory() as directory:
            real = lattice_to_stl(
                registered, Path(directory) / "real.stl", radius=3.0, segments=12
            )
            checks.check("real lattice draws all 18,468 struts with none skipped",
                         real["drawn_strut_count"] == 18468
                         and real["skipped_strut_count"] == 0,
                         f"drawn={real['drawn_strut_count']}, "
                         f"skipped={real['skipped_strut_count']}")
            checks.check("real lattice triangle count is struts * 4 * segments",
                         real["triangle_count"] == 18468 * 4 * 12,
                         f"triangles={real['triangle_count']}")
            real_metadata = inspect_stl(real["stl"])
            checks.check("inspect_stl agrees on the real lattice triangle count",
                         real_metadata.triangles == real["triangle_count"],
                         f"{real_metadata.triangles}")
    else:
        checks.check("real registered lattice JSON is available", False,
                     f"missing {registered_path}")

    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
