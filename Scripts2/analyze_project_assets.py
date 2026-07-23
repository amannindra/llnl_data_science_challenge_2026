#!/usr/bin/env python3
"""Create a repeatable, non-destructive inventory of this DSSI repository.

Run with the prepared environment:
    conda run -n DSC python Scripts/analyze_project_assets.py

Results are written below ``Scripts/analysis_output``.  The program handles
Git-LFS pointer files explicitly, so it never mistakes a pointer for a TIFF,
STL, or other scientific asset.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import filters, measure, morphology

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "analysis_output"
LFS_HEADER = "version https://git-lfs.github.com/spec/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def lfs_pointer(path: Path) -> dict[str, Any] | None:
    if path.stat().st_size > 512:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if not text.startswith(LFS_HEADER):
        return None
    match = re.search(r"oid sha256:([0-9a-f]{64})\nsize (\d+)", text)
    if not match:
        return {"pointer_text": text}
    return {"sha256": match.group(1), "expected_bytes": int(match.group(2))}


def finite_stats(array: np.ndarray) -> dict[str, Any]:
    finite = np.isfinite(array)
    values = array[finite]
    result: dict[str, Any] = {
        "finite_voxels": int(values.size),
        "nonfinite_voxels": int(array.size - values.size),
    }
    if values.size:
        result.update(
            min=float(values.min()),
            max=float(values.max()),
            mean=float(values.mean()),
            std=float(values.std()),
            percentiles={
                str(p): float(np.percentile(values, p))
                for p in (0.1, 1, 5, 25, 50, 75, 95, 99, 99.9)
            },
        )
    return result


def skeleton_metrics(skeleton: np.ndarray) -> dict[str, int]:
    """Estimate centerline complexity from a 26-connected binary skeleton."""
    kernel = np.ones((3, 3, 3), dtype=np.uint8)
    kernel[1, 1, 1] = 0
    degree = ndi.convolve(skeleton.astype(np.uint8), kernel, mode="constant", cval=0)
    return {
        "skeleton_voxels": int(skeleton.sum()),
        "endpoints_degree_1": int(np.count_nonzero(skeleton & (degree == 1))),
        "branch_voxels_degree_ge_3": int(np.count_nonzero(skeleton & (degree >= 3))),
        "maximum_neighbor_degree": int(degree[skeleton].max()) if skeleton.any() else 0,
    }


def save_midslice_gallery(volume: np.ndarray, mask: np.ndarray, skeleton: np.ndarray) -> None:
    mid = tuple(dim // 2 for dim in volume.shape)
    fig, axes = plt.subplots(3, 3, figsize=(10, 10), constrained_layout=True)
    names = ("raw intensity", "Otsu mask", "skeleton")
    arrays = (volume, mask, skeleton)
    for axis in range(3):
        for col, (name, source) in enumerate(zip(names, arrays)):
            image = np.take(source, mid[axis], axis=axis)
            axes[axis, col].imshow(image, cmap="gray")
            axes[axis, col].set_title(f"axis {axis}, index {mid[axis]}: {name}")
            axes[axis, col].axis("off")
    fig.savefig(OUT / "unitcell_orthogonal_slices.png", dpi=180)
    plt.close(fig)


def analyze_npy(path: Path) -> dict[str, Any]:
    array = np.load(path, mmap_mode="r")
    item: dict[str, Any] = {
        "kind": "numpy_volume",
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "nbytes": int(array.nbytes),
        "statistics": finite_stats(array),
    }
    if array.ndim != 3:
        return item

    # The array is loaded once into writable memory for the downstream NDE work.
    volume = np.asarray(array, dtype=np.float32)
    threshold = float(filters.threshold_otsu(volume))
    mask = volume >= threshold
    labels, count = measure.label(mask, connectivity=3, return_num=True)
    component_sizes = np.bincount(labels.ravel())[1:]
    skeleton = morphology.skeletonize(mask)
    np.save(OUT / "unitcell_otsu_mask.npy", mask)
    np.save(OUT / "unitcell_otsu_skeleton.npy", skeleton)
    save_midslice_gallery(volume, mask, skeleton)

    item["segmentation"] = {
        "method": "global Otsu threshold",
        "threshold": threshold,
        "foreground_voxels": int(mask.sum()),
        "foreground_fraction": float(mask.mean()),
        "foreground_mean_intensity": float(volume[mask].mean()),
        "background_mean_intensity": float(volume[~mask].mean()),
        "connected_components_26": int(count),
        "largest_component_voxels": int(component_sizes.max()) if component_sizes.size else 0,
        "largest_component_fraction_of_foreground": (
            float(component_sizes.max() / mask.sum()) if mask.any() else 0.0
        ),
    }
    item["skeleton"] = skeleton_metrics(skeleton)
    return item


def analyze_png(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.load()
        data = np.asarray(image)
        item: dict[str, Any] = {
            "kind": "png_image",
            "mode": image.mode,
            "size_pixels": list(image.size),
            "array_shape": list(data.shape),
            "channels": 1 if data.ndim == 2 else int(data.shape[-1]),
            "per_channel_min": np.atleast_1d(data.min(axis=(0, 1))).tolist(),
            "per_channel_max": np.atleast_1d(data.max(axis=(0, 1))).tolist(),
            "per_channel_mean": [float(v) for v in np.atleast_1d(data.mean(axis=(0, 1)))],
        }
        if data.ndim == 3 and data.shape[-1] == 4:
            alpha = data[..., 3]
            item["transparent_pixels"] = int(np.count_nonzero(alpha == 0))
            item["opaque_pixels"] = int(np.count_nonzero(alpha == 255))
        rgb = data[..., :3] if data.ndim == 3 else data
        if data.ndim == 3:
            item["unique_rgb_colors"] = int(np.unique(rgb.reshape(-1, 3), axis=0).shape[0])
        return item


def json_shape(value: Any, depth: int = 0) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = Counter()
        objects = 1
        lists = scalars = 0
        for key, child in value.items():
            keys[str(key)] += 1
            child_info = json_shape(child, depth + 1)
            objects += child_info["objects"]
            lists += child_info["lists"]
            scalars += child_info["scalars"]
            keys.update(child_info["keys"])
        return {"objects": objects, "lists": lists, "scalars": scalars, "keys": keys}
    if isinstance(value, list):
        keys = Counter()
        objects = lists = 0
        scalars = 0 if value else 1
        for child in value:
            child_info = json_shape(child, depth + 1)
            objects += child_info["objects"]
            lists += 1 + child_info["lists"]
            scalars += child_info["scalars"]
            keys.update(child_info["keys"])
        return {"objects": objects, "lists": lists, "scalars": scalars, "keys": keys}
    return {"objects": 0, "lists": 0, "scalars": 1, "keys": Counter()}


def find_numeric_coordinate_lists(value: Any, label: str = "root") -> list[tuple[str, np.ndarray]]:
    found: list[tuple[str, np.ndarray]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_numeric_coordinate_lists(child, f"{label}.{key}"))
    elif isinstance(value, list):
        if value and all(isinstance(row, (list, tuple)) and len(row) == 3 for row in value):
            try:
                coords = np.asarray(value, dtype=float)
                if np.isfinite(coords).all():
                    found.append((label, coords))
                    return found
            except (TypeError, ValueError):
                pass
        for index, child in enumerate(value):
            found.extend(find_numeric_coordinate_lists(child, f"{label}[{index}]"))
    return found


def analyze_json(path: Path) -> dict[str, Any]:
    pointer = lfs_pointer(path)
    if pointer is not None:
        return {"kind": "git_lfs_pointer", "lfs": pointer}
    value = json.loads(path.read_text(encoding="utf-8"))
    shape = json_shape(value)
    item: dict[str, Any] = {
        "kind": "json",
        "top_level_type": type(value).__name__,
        "top_level_keys": sorted(value) if isinstance(value, dict) else None,
        "objects": shape["objects"],
        "lists": shape["lists"],
        "scalars": shape["scalars"],
        "most_common_keys": shape["keys"].most_common(20),
    }
    coordinate_sets = find_numeric_coordinate_lists(value)
    if coordinate_sets:
        item["coordinate_arrays"] = [
            {
                "location": location,
                "rows": int(coords.shape[0]),
                "min": coords.min(axis=0).tolist(),
                "max": coords.max(axis=0).tolist(),
            }
            for location, coords in coordinate_sets[:10]
        ]
    return item


def analyze_text(path: Path) -> dict[str, Any]:
    pointer = lfs_pointer(path)
    if pointer is not None:
        return {"kind": "git_lfs_pointer", "lfs": pointer}
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"kind": "unrecognized_binary"}
    return {
        "kind": "text_or_source",
        "line_count": len(text.splitlines()),
        "character_count": len(text),
        "first_nonblank_line": next((line for line in text.splitlines() if line.strip()), ""),
    }


def analyze_path(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    item: dict[str, Any] = {
        "relative_path": str(path.relative_to(ROOT)),
        "bytes_present": path.stat().st_size,
        "sha256_present_bytes": sha256(path),
    }
    if suffix == ".npy":
        item.update(analyze_npy(path))
    elif suffix == ".png":
        item.update(analyze_png(path))
    elif suffix == ".json":
        item.update(analyze_json(path))
    elif suffix in {".tif", ".tiff", ".stl"}:
        pointer = lfs_pointer(path)
        item.update({"kind": "git_lfs_pointer", "lfs": pointer} if pointer else {"kind": suffix[1:]})
    elif suffix in {".pdf", ".ipynb", ".md", ".txt", ".py", ".toml", ".json", ""}:
        item.update(analyze_text(path))
    else:
        item.update(analyze_text(path))
    return item


def markdown_report(files: list[dict[str, Any]]) -> str:
    lines = [
        "# Repository asset analysis",
        "",
        "This is a non-destructive inventory produced by `Scripts/analyze_project_assets.py`.",
        "Git-LFS pointers are reported as unavailable source assets; their expected size and object ID are preserved.",
        "",
        "## File inventory",
        "",
        "| Path | Present bytes | Kind | Key result |",
        "| --- | ---: | --- | --- |",
    ]
    for item in files:
        result = ""
        if item["kind"] == "git_lfs_pointer":
            result = f"LFS object expected: {item['lfs'].get('expected_bytes', 'unknown')} bytes"
        elif item["kind"] == "numpy_volume":
            result = f"shape={item['shape']}; Otsu={item.get('segmentation', {}).get('threshold', 'n/a')}"
        elif item["kind"] == "png_image":
            result = f"{item['size_pixels'][0]}×{item['size_pixels'][1]}, {item['mode']}"
        elif item["kind"] == "json":
            result = f"keys={', '.join(item.get('top_level_keys') or [])[:150]}"
        else:
            result = item.get("first_nonblank_line", "")[:150]
        lines.append(f"| `{item['relative_path']}` | {item['bytes_present']:,} | {item['kind']} | {result} |")
    npy = next((item for item in files if item["kind"] == "numpy_volume"), None)
    if npy and "segmentation" in npy:
        seg, skel = npy["segmentation"], npy["skeleton"]
        lines += [
            "",
            "## Unit-cell NDE metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Volume shape | {npy['shape']} |",
            f"| Intensity mean ± SD | {npy['statistics']['mean']:.6f} ± {npy['statistics']['std']:.6f} |",
            f"| Otsu threshold | {seg['threshold']:.6f} |",
            f"| Foreground voxels / fraction | {seg['foreground_voxels']:,} / {seg['foreground_fraction']:.4%} |",
            f"| 26-connected components | {seg['connected_components_26']:,} |",
            f"| Largest-component foreground fraction | {seg['largest_component_fraction_of_foreground']:.4%} |",
            f"| Skeleton voxels | {skel['skeleton_voxels']:,} |",
            f"| Skeleton endpoints (degree 1) | {skel['endpoints_degree_1']:,} |",
            f"| Skeleton branch voxels (degree ≥3) | {skel['branch_voxels_degree_ge_3']:,} |",
            "",
            "![Orthogonal raw/mask/skeleton slices](unitcell_orthogonal_slices.png)",
        ]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    excluded = {".git", "Scripts/analysis_output"}
    paths = sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and str(path.relative_to(ROOT)) not in excluded
        and not any(part == ".git" for part in path.relative_to(ROOT).parts)
        and "Scripts/analysis_output" not in str(path.relative_to(ROOT))
    )
    files = [analyze_path(path) for path in paths]
    document = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "file_count": len(files),
        "files": files,
    }
    (OUT / "asset_inventory.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    (OUT / "asset_inventory.md").write_text(markdown_report(files), encoding="utf-8")
    print(f"Analyzed {len(files)} files.")
    print(f"Inventory: {OUT / 'asset_inventory.md'}")


if __name__ == "__main__":
    main()
