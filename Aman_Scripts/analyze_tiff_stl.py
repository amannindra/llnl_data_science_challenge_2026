#!/usr/bin/env python3
"""Inspect every TIFF and STL below ``data`` without modifying source assets.

Git-LFS pointer files are identified before any parser is called.  With real
assets present, TIFF stacks are traversed page-by-page for exact global
intensity statistics and representative slice previews; binary STL meshes are
streamed in chunks for triangle count and spatial bounds.  Outputs are placed
only in ``Scripts/outputs``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import tifffile

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:  # Package import.
    from .Components.asset_io import detect_lfs_pointer, inspect_stl
    from .Components.paths import data_path, find_repository_root, output_path
    from .Components.reporting import file_sha256, write_json
except ImportError:  # Direct execution.
    from Components.asset_io import detect_lfs_pointer, inspect_stl
    from Components.paths import data_path, find_repository_root, output_path
    from Components.reporting import file_sha256, write_json


ROOT = find_repository_root(__file__)
DATA = data_path(root=ROOT)
OUT = output_path(root=ROOT)


def lfs_pointer(path: Path) -> dict[str, Any] | None:
    """Return LFS object metadata, or ``None`` for an actual data file."""
    pointer = detect_lfs_pointer(path)
    if pointer is None:
        return None
    return {
        "object_id": pointer.object_id or "unknown",
        "expected_bytes": pointer.expected_bytes or 0,
    }


def file_digest(path: Path) -> str:
    """Backward-compatible alias for the shared streaming SHA-256 helper."""

    return file_sha256(path)


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
    metadata = inspect_stl(path)
    return {
        "kind": f"{metadata.encoding}_stl_mesh",
        "triangles": metadata.triangles,
        "vertex_records": metadata.vertex_records,
        "bounding_box_min": metadata.bounding_box_min,
        "bounding_box_max": metadata.bounding_box_max,
        "bounding_box_size": metadata.bounding_box_size,
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
    write_json(destination, records)
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
