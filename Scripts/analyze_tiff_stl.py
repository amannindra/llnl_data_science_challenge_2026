#!/usr/bin/env python3
"""Inspect every TIFF and STL below ``data`` without modifying source assets.

Git-LFS pointer files are identified before any parser is called.  With real
assets present, TIFF stacks are traversed page-by-page for exact global
intensity statistics and representative slice previews; binary STL meshes are
streamed in chunks for triangle count and spatial bounds.  Outputs are placed
only in ``Scripts/outputs``.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import tifffile

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "outputs"
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def lfs_pointer(path: Path) -> dict[str, Any] | None:
    """Return LFS object metadata, or ``None`` for an actual data file."""
    if path.stat().st_size > 512:
        return None
    raw = path.read_bytes()
    if not raw.startswith(LFS_PREFIX):
        return None
    lines = raw.decode("utf-8").splitlines()
    return {
        "object_id": next((line.removeprefix("oid sha256:") for line in lines if line.startswith("oid ")), "unknown"),
        "expected_bytes": int(next((line.removeprefix("size ") for line in lines if line.startswith("size ")), "0")),
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze_tiff(path: Path) -> dict[str, Any]:
    pointer = lfs_pointer(path)
    if pointer:
        return {"kind": "git_lfs_pointer", "lfs": pointer}

    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        pages = list(series.pages)
        info: dict[str, Any] = {
            "kind": "tiff_stack",
            "is_bigtiff": tif.is_bigtiff,
            "series_axes": series.axes,
            "series_shape": list(series.shape),
            "series_dtype": str(series.dtype),
            "page_count": len(pages),
            "page_shapes": sorted({tuple(page.shape) for page in pages}),
            "compression": sorted({str(page.compression) for page in pages}),
        }
        if not pages:
            return info

        first, middle, last = 0, len(pages) // 2, len(pages) - 1
        chosen = {first, middle, last}
        previews: dict[int, np.ndarray] = {}
        count, total, total_sq = 0, 0.0, 0.0
        minimum, maximum = np.inf, -np.inf
        for index, page in enumerate(pages):
            array = page.asarray()
            values = np.asarray(array, dtype=np.float64)
            count += values.size
            total += float(values.sum())
            total_sq += float(np.square(values).sum())
            minimum = min(minimum, float(values.min()))
            maximum = max(maximum, float(values.max()))
            if index in chosen:
                previews[index] = array
        mean = total / count
        info["global_statistics"] = {
            "voxels": count,
            "min": minimum,
            "max": maximum,
            "mean": mean,
            "std": max(total_sq / count - mean * mean, 0.0) ** 0.5,
        }
        _save_tiff_previews(path, previews)
        return info


def _save_tiff_previews(path: Path, previews: dict[int, np.ndarray]) -> None:
    fig, axes = plt.subplots(1, len(previews), figsize=(5 * len(previews), 5))
    if len(previews) == 1:
        axes = [axes]
    for axis, (index, image) in zip(axes, sorted(previews.items())):
        axis.imshow(image, cmap="gray")
        axis.set_title(f"{path.name}: page {index}")
        axis.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / f"{path.stem}_representative_slices.png", dpi=160)
    plt.close(fig)


def analyze_stl(path: Path) -> dict[str, Any]:
    pointer = lfs_pointer(path)
    if pointer:
        return {"kind": "git_lfs_pointer", "lfs": pointer}
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(84)
    if len(header) >= 84:
        face_count = struct.unpack("<I", header[80:84])[0]
        if 84 + 50 * face_count == size:
            return _analyze_binary_stl(path, face_count)
    return _analyze_ascii_stl(path)


def _analyze_binary_stl(path: Path, face_count: int) -> dict[str, Any]:
    record = np.dtype([
        ("normal", "<f4", (3,)),
        ("vertices", "<f4", (3, 3)),
        ("attributes", "<u2"),
    ])
    faces = np.memmap(path, mode="r", offset=84, dtype=record, shape=(face_count,))
    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    for begin in range(0, face_count, 200_000):
        vertices = faces[begin:begin + 200_000]["vertices"].reshape(-1, 3)
        lower = np.minimum(lower, vertices.min(axis=0))
        upper = np.maximum(upper, vertices.max(axis=0))
    return {
        "kind": "binary_stl_mesh",
        "triangles": face_count,
        "vertex_records": face_count * 3,
        "bounding_box_min": lower.tolist(),
        "bounding_box_max": upper.tolist(),
        "bounding_box_size": (upper - lower).tolist(),
    }


def _analyze_ascii_stl(path: Path) -> dict[str, Any]:
    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    vertices = triangles = 0
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 4 and parts[0].lower() == "vertex":
                point = np.asarray(parts[1:], dtype=float)
                lower = np.minimum(lower, point)
                upper = np.maximum(upper, point)
                vertices += 1
            elif parts and parts[0].lower() == "endfacet":
                triangles += 1
    return {
        "kind": "ascii_stl_mesh",
        "triangles": triangles,
        "vertex_records": vertices,
        "bounding_box_min": lower.tolist() if vertices else None,
        "bounding_box_max": upper.tolist() if vertices else None,
        "bounding_box_size": (upper - lower).tolist() if vertices else None,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    records = []
    for path in sorted(DATA.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".tif", ".tiff", ".stl"}:
            continue
        item = {
            "relative_path": str(path.relative_to(ROOT)),
            "present_bytes": path.stat().st_size,
            "sha256_present_bytes": file_digest(path),
        }
        item.update(analyze_tiff(path) if path.suffix.lower() in {".tif", ".tiff"} else analyze_stl(path))
        records.append(item)
        print(f"{item['relative_path']}: {item['kind']}")
    destination = OUT / "tiff_stl_report.json"
    destination.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
