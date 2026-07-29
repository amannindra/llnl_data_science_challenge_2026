"""Lazy CT loading, graph validation, and serialization helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import tifffile


REQUIRED_GRAPH_KEYS = {"junctions", "struts", "unit_cells"}


def load_graph(path: Path) -> dict[str, Any]:
    """Load and minimally validate the registered lattice graph."""

    if not path.is_file():
        raise FileNotFoundError(f"Registered JSON does not exist: {path}")
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load registered JSON {path}: {exc}") from exc
    missing = REQUIRED_GRAPH_KEYS.difference(graph)
    if missing:
        raise ValueError(f"Registered JSON is missing keys: {sorted(missing)}")
    if not graph["junctions"] or not graph["struts"]:
        raise ValueError("Registered JSON contains no junctions or struts")

    junction_ids = {int(item["id"]) for item in graph["junctions"]}
    for strut in graph["struts"]:
        endpoints = {int(strut["junction0"]), int(strut["junction1"])}
        if not endpoints.issubset(junction_ids):
            raise ValueError(f"Strut {strut.get('id')} references an unknown junction")
    return graph


def open_ct_memmap(path: Path) -> np.ndarray:
    """Open the TIFF as an operating-system-backed array without copying it."""

    if not path.is_file():
        raise FileNotFoundError(f"Registered TIFF does not exist: {path}")
    try:
        volume = tifffile.memmap(path, mode="r")
    except (OSError, ValueError, tifffile.TiffFileError) as exc:
        raise ValueError(f"Could not memory-map TIFF {path}: {exc}") from exc
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D TIFF, found shape {volume.shape}")
    return volume


def sampled_voxels(
    path: Path,
    page_count: int = 64,
    in_plane_stride: int = 8,
) -> np.ndarray:
    """Read an evenly spaced, reproducible subset for intensity estimation."""

    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError(f"TIFF has no pages: {path}")
        page_indices = np.linspace(0, len(tif.pages) - 1, page_count, dtype=int)
        chunks = [
            tif.pages[int(index)].asarray()[::in_plane_stride, ::in_plane_stride].ravel()
            for index in page_indices
        ]
    return np.concatenate(chunks)


def write_json(path: Path, value: Any) -> None:
    """Write JSON atomically enough for a local single-process experiment."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object with a clear missing-file error."""

    if not path.is_file():
        raise FileNotFoundError(f"Required output does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value
