"""Create a bounded CT-derived surface for browser visualization."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

from .config import DEFAULT_CONFIG, DefectConfig
from .io import open_ct_memmap
from .io import read_json


def build_xray_context(
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    downsample: int = 8,
    maximum_faces: int = 50_000,
) -> dict[str, np.ndarray | float | int]:
    """Extract a deterministic, decimated material surface from the registered CT."""

    if downsample < 4:
        raise ValueError("X-ray context downsample must be at least 4")
    if maximum_faces < 1_000:
        raise ValueError("maximum_faces must be at least 1000")
    threshold = float(read_json(config.alignment_path)["threshold_otsu"])
    volume = open_ct_memmap(config.ct_path)
    sampled = np.asarray(
        volume[::downsample, ::downsample, ::downsample], dtype=np.float32
    )
    smoothed = gaussian_filter(sampled, sigma=0.7)
    vertices, faces, _, _ = marching_cubes(
        smoothed,
        level=threshold,
        spacing=(float(downsample),) * 3,
        step_size=2,
        allow_degenerate=False,
    )
    if len(faces) > maximum_faces:
        indices = np.linspace(0, len(faces) - 1, maximum_faces, dtype=int)
        faces = faces[indices]
    used = np.unique(faces)
    reindex = np.full(int(used.max()) + 1, -1, dtype=np.int32)
    reindex[used] = np.arange(len(used), dtype=np.int32)
    return {
        "vertices_zyx": vertices[used].astype(np.float32),
        "faces": reindex[faces].astype(np.int32),
        "threshold": threshold,
        "downsample": int(downsample),
    }


def save_xray_context(
    output_path: Path | str,
    config: DefectConfig = DEFAULT_CONFIG,
    *,
    downsample: int = 8,
    maximum_faces: int = 50_000,
) -> Path:
    """Write the compact surface artifact without modifying the source TIFF."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    context = build_xray_context(
        config, downsample=downsample, maximum_faces=maximum_faces
    )
    np.savez_compressed(path, **context)
    return path


def load_xray_context(path: Path | str) -> dict[str, np.ndarray | float | int]:
    """Load and validate the compact surface artifact."""

    with np.load(Path(path), allow_pickle=False) as payload:
        required = {"vertices_zyx", "faces", "threshold", "downsample"}
        missing = required.difference(payload.files)
        if missing:
            raise ValueError(f"X-ray context is missing fields: {sorted(missing)}")
        vertices = np.asarray(payload["vertices_zyx"], dtype=np.float32)
        faces = np.asarray(payload["faces"], dtype=np.int32)
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            raise ValueError("vertices_zyx must have shape (n, 3)")
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError("faces must have shape (n, 3)")
        return {
            "vertices_zyx": vertices,
            "faces": faces,
            "threshold": float(payload["threshold"]),
            "downsample": int(payload["downsample"]),
        }
