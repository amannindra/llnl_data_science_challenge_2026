#!/usr/bin/env python3
"""Adversarial checks for LFS-aware JSON, NumPy, and TIFF readers."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
import tifffile


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from Scripts.Components.asset_io import (  # noqa: E402
    AssetNotMaterializedError,
    detect_lfs_pointer,
    inspect_npy,
    inspect_stl,
    inspect_tiff,
    load_json,
    load_npy,
    read_tiff,
    read_tiff_slice,
    save_npy,
)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}: {detail}")
        self.results.append({"name": name, "passed": bool(condition), "detail": detail})

    def raises(self, name: str, error: type[BaseException], operation: Callable[[], object]) -> None:
        try:
            operation()
        except error:
            self.check(name, True)
        except Exception as exc:  # pragma: no cover - diagnostic branch
            self.check(name, False, f"raised {type(exc).__name__}, expected {error.__name__}")
        else:
            self.check(name, False, f"did not raise {error.__name__}")


def main() -> int:
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="dssi_assets_") as temporary:
        base = Path(temporary)
        digest = "0123456789abcdef" * 4
        pointer_path = base / "asset.npy"
        pointer_path.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{digest}\n"
            "size 123456\n",
            encoding="utf-8",
        )
        pointer = detect_lfs_pointer(pointer_path)
        checks.check("valid LFS pointer detected", pointer is not None and pointer.valid)
        checks.check("LFS object id parsed", pointer is not None and pointer.object_id == digest)
        checks.check("LFS expected size parsed", pointer is not None and pointer.expected_bytes == 123456)

        ordinary = base / "ordinary.txt"
        ordinary.write_text("not an LFS pointer", encoding="utf-8")
        checks.check("ordinary small file is not pointer", detect_lfs_pointer(ordinary) is None)

        malformed = base / "malformed.tif"
        malformed.write_text(
            "version https://git-lfs.github.com/spec/v1\nsize unknown\n",
            encoding="utf-8",
        )
        malformed_pointer = detect_lfs_pointer(malformed)
        checks.check(
            "malformed LFS header remains classified as pointer",
            malformed_pointer is not None and not malformed_pointer.valid,
        )
        checks.raises(
            "unreasonably small pointer limit rejected",
            ValueError,
            lambda: detect_lfs_pointer(ordinary, maximum_pointer_bytes=5),
        )

        json_path = base / "fixture.json"
        json_path.write_text('{"name": "octet", "count": 9}', encoding="utf-8")
        checks.check("JSON round-trip", load_json(json_path) == {"name": "octet", "count": 9})
        checks.raises(
            "JSON LFS pointer rejected before decoding",
            AssetNotMaterializedError,
            lambda: load_json(pointer_path),
        )
        checks.raises("missing file rejected", FileNotFoundError, lambda: load_json(base / "absent.json"))
        checks.raises("directory rejected as asset", IsADirectoryError, lambda: load_json(base))

        array = np.arange(60, dtype=np.int16).reshape(3, 4, 5)
        npy_path = base / "volume.npy"
        np.save(npy_path, array)
        mapped = load_npy(npy_path)
        checks.check("NPY defaults to memory mapping", isinstance(mapped, np.memmap))
        checks.check("NPY values preserved", np.array_equal(mapped, array))
        loaded = load_npy(npy_path, mmap_mode=None)
        checks.check("explicit materialized NPY read", not isinstance(loaded, np.memmap) and np.array_equal(loaded, array))
        npy_metadata = inspect_npy(npy_path)
        checks.check("NPY shape inspected lazily", npy_metadata.shape == (3, 4, 5))
        checks.check("NPY dtype inspected lazily", npy_metadata.dtype == np.dtype(np.int16))
        checks.check("NPY byte count inspected lazily", npy_metadata.nbytes == array.nbytes)

        saved = save_npy(base / "generated" / "copy", array, create_parents=True)
        checks.check("save_npy appends extension", saved.name == "copy.npy" and saved.is_file())
        checks.check("save_npy preserves values", np.array_equal(np.load(saved), array))
        checks.raises(
            "save_npy requires parent unless opted in",
            FileNotFoundError,
            lambda: save_npy(base / "missing_parent" / "array.npy", array),
        )

        tiff_path = base / "stack.tiff"
        tifffile.imwrite(
            tiff_path,
            array.astype(np.uint16),
            imagej=True,
            metadata={"axes": "ZYX"},
        )
        tiff_metadata = inspect_tiff(tiff_path)
        checks.check("TIFF shape inspected", tiff_metadata.shape == array.shape)
        checks.check("TIFF axes explicit", tiff_metadata.axes == "ZYX")
        checks.check("TIFF dtype inspected", tiff_metadata.dtype == np.dtype(np.uint16))
        checks.check("TIFF page count inspected", tiff_metadata.page_count == array.shape[0])
        checks.check("uncompressed TIFF marked mappable", tiff_metadata.memory_mappable)
        checks.check("TIFF compression metadata populated", len(tiff_metadata.compression) == 1)

        tiff_mapped = read_tiff(tiff_path)
        checks.check("TIFF defaults to memory mapping", isinstance(tiff_mapped, np.memmap))
        checks.check("mapped TIFF values preserved", np.array_equal(tiff_mapped, array))
        tiff_loaded = read_tiff(tiff_path, mmap_mode=None)
        checks.check("explicit full TIFF read preserves values", np.array_equal(tiff_loaded, array))
        checks.check("single TIFF Z page read", np.array_equal(read_tiff_slice(tiff_path, 1), array[1]))
        checks.raises(
            "negative TIFF Z page rejected",
            IndexError,
            lambda: read_tiff_slice(tiff_path, -1),
        )
        checks.raises(
            "past-end TIFF Z page rejected",
            IndexError,
            lambda: read_tiff_slice(tiff_path, array.shape[0]),
        )
        checks.raises(
            "invalid TIFF series rejected",
            IndexError,
            lambda: inspect_tiff(tiff_path, series_index=5),
        )
        checks.raises(
            "TIFF LFS pointer rejected before parser",
            AssetNotMaterializedError,
            lambda: inspect_tiff(malformed),
        )

        temporal_path = base / "temporal.tiff"
        temporal = np.arange(2 * 3 * 4 * 5, dtype=np.uint16).reshape(2, 3, 4, 5)
        tifffile.imwrite(temporal_path, temporal, imagej=True, metadata={"axes": "TZYX"})
        checks.check("multidimensional TIFF axes are reported explicitly",
                     inspect_tiff(temporal_path).axes == "TZYX")
        checks.raises(
            "Z-slice helper rejects ambiguous non-ZYX series",
            ValueError,
            lambda: read_tiff_slice(temporal_path, 1),
        )

        ascii_stl = base / "mesh_ascii.stl"
        ascii_stl.write_text(
            "solid fixture\n"
            "facet normal 0 0 1\nouter loop\n"
            "vertex -1 0 2\nvertex 3 0 2\nvertex -1 4 2\n"
            "endloop\nendfacet\nendsolid fixture\n",
            encoding="utf-8",
        )
        ascii_metadata = inspect_stl(ascii_stl)
        checks.check("ASCII STL encoding detected", ascii_metadata.encoding == "ascii")
        checks.check("ASCII STL triangle count parsed", ascii_metadata.triangles == 1)
        checks.check("ASCII STL vertex count parsed", ascii_metadata.vertex_records == 3)
        checks.check("ASCII STL minimum XYZ bound parsed", ascii_metadata.bounding_box_min == (-1.0, 0.0, 2.0))
        checks.check("ASCII STL maximum XYZ bound parsed", ascii_metadata.bounding_box_max == (3.0, 4.0, 2.0))
        checks.check("ASCII STL bounding-box size derived", ascii_metadata.bounding_box_size == (4.0, 4.0, 0.0))

        binary_stl = base / "mesh_binary.stl"
        triangle_dtype = np.dtype([
            ("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attributes", "<u2")
        ])
        triangle = np.zeros(1, dtype=triangle_dtype)
        triangle["vertices"][0] = [[2, -2, 1], [5, 3, 4], [0, 1, -1]]
        binary_stl.write_bytes(b"binary fixture".ljust(80, b"\0") + struct.pack("<I", 1) + triangle.tobytes())
        binary_metadata = inspect_stl(binary_stl)
        checks.check("binary STL encoding detected", binary_metadata.encoding == "binary")
        checks.check("binary STL triangle and vertex counts parsed",
                     (binary_metadata.triangles, binary_metadata.vertex_records) == (1, 3))
        checks.check("binary STL minimum XYZ bound parsed", binary_metadata.bounding_box_min == (0.0, -2.0, -1.0))
        checks.check("binary STL maximum XYZ bound parsed", binary_metadata.bounding_box_max == (5.0, 3.0, 4.0))
        checks.raises("STL LFS pointer rejected before parsing", AssetNotMaterializedError,
                      lambda: inspect_stl(pointer_path))

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} asset-I/O checks passed")
    print(json.dumps({"suite": "asset_io", "passed": checks.passed, "failed": checks.failed,
                      "total": total, "minimum_satisfied": total >= 12,
                      "results": checks.results}, sort_keys=True))
    return 0 if checks.failed == 0 and total >= 12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
