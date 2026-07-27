"""LFS-aware, memory-conscious readers for project data assets."""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Literal

import numpy as np
import tifffile


LFS_VERSION = "https://git-lfs.github.com/spec/v1"
LFS_PREFIX = f"version {LFS_VERSION}".encode("ascii")


class AssetNotMaterializedError(RuntimeError):
    """Raised when a file is a Git-LFS pointer instead of its data payload."""


@dataclass(frozen=True)
class LFSPointer:
    """Metadata parsed from a Git-LFS pointer file."""

    path: Path
    version: str
    object_id: str | None
    expected_bytes: int | None

    @property
    def valid(self) -> bool:
        return self.object_id is not None and self.expected_bytes is not None


@dataclass(frozen=True)
class NumpyMetadata:
    """Array metadata obtainable without materializing the full array."""

    path: Path
    shape: tuple[int, ...]
    dtype: np.dtype[Any]
    nbytes: int


@dataclass(frozen=True)
class TIFFMetadata:
    """TIFF series metadata read without decoding the image volume."""

    path: Path
    series_index: int
    shape: tuple[int, ...]
    axes: str
    dtype: np.dtype[Any]
    page_count: int
    is_bigtiff: bool
    compression: tuple[str, ...]
    memory_mappable: bool


@dataclass(frozen=True)
class STLMetadata:
    """Triangle count and XYZ bounds for an ASCII or binary STL mesh."""

    path: Path
    encoding: Literal["ascii", "binary"]
    triangles: int
    vertex_records: int
    bounding_box_min: tuple[float, float, float] | None
    bounding_box_max: tuple[float, float, float] | None

    @property
    def bounding_box_size(self) -> tuple[float, float, float] | None:
        if self.bounding_box_min is None or self.bounding_box_max is None:
            return None
        return tuple(
            maximum - minimum
            for minimum, maximum in zip(self.bounding_box_min, self.bounding_box_max)
        )


def _existing_file(path: str | PathLike[str]) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    if not resolved.is_file():
        raise IsADirectoryError(resolved)
    return resolved


def detect_lfs_pointer(
    path: str | PathLike[str],
    *,
    maximum_pointer_bytes: int = 4096,
) -> LFSPointer | None:
    """Return pointer metadata, or ``None`` when ``path`` is a real asset.

    Malformed files beginning with the LFS version header are still reported as
    pointers, with missing fields set to ``None``.  That ensures a corrupt
    pointer is never passed to NumPy, JSON, or TIFF decoders as scientific data.
    """

    asset = _existing_file(path)
    if maximum_pointer_bytes < len(LFS_PREFIX):
        raise ValueError("maximum_pointer_bytes is too small for an LFS header")
    if asset.stat().st_size > maximum_pointer_bytes:
        return None
    raw = asset.read_bytes()
    if not raw.startswith(LFS_PREFIX):
        return None
    text = raw.decode("utf-8", errors="replace")
    version_match = re.search(r"^version\s+(\S+)\s*$", text, re.MULTILINE)
    oid_match = re.search(r"^oid\s+sha256:([0-9a-fA-F]{64})\s*$", text, re.MULTILINE)
    size_match = re.search(r"^size\s+(\d+)\s*$", text, re.MULTILINE)
    return LFSPointer(
        path=asset,
        version=version_match.group(1) if version_match else LFS_VERSION,
        object_id=oid_match.group(1).lower() if oid_match else None,
        expected_bytes=int(size_match.group(1)) if size_match else None,
    )


def _require_materialized(path: str | PathLike[str]) -> Path:
    asset = _existing_file(path)
    pointer = detect_lfs_pointer(asset)
    if pointer is not None:
        details = (
            f" (sha256:{pointer.object_id}, {pointer.expected_bytes} bytes)"
            if pointer.valid
            else " (malformed pointer metadata)"
        )
        raise AssetNotMaterializedError(
            f"Git-LFS asset is not materialized: {asset}{details}"
        )
    return asset


def load_json(path: str | PathLike[str], *, encoding: str = "utf-8") -> Any:
    """Load JSON after rejecting missing and unmaterialized LFS assets."""

    asset = _require_materialized(path)
    with asset.open("r", encoding=encoding) as handle:
        return json.load(handle)


def load_npy(
    path: str | PathLike[str],
    *,
    mmap_mode: Literal["r", "r+", "w+", "c"] | None = "r",
    allow_pickle: bool = False,
) -> np.ndarray:
    """Load a ``.npy`` array, memory-mapped read-only by default."""

    asset = _require_materialized(path)
    return np.load(asset, mmap_mode=mmap_mode, allow_pickle=allow_pickle)


def inspect_npy(path: str | PathLike[str]) -> NumpyMetadata:
    """Return shape, dtype, and logical byte count without loading array data."""

    asset = _require_materialized(path)
    array = np.load(asset, mmap_mode="r", allow_pickle=False)
    return NumpyMetadata(
        path=asset,
        shape=tuple(int(value) for value in array.shape),
        dtype=np.dtype(array.dtype),
        nbytes=int(array.nbytes),
    )


def save_npy(
    path: str | PathLike[str],
    array: np.ndarray,
    *,
    create_parents: bool = False,
    allow_pickle: bool = False,
) -> Path:
    """Explicitly save an array and return the resolved destination path."""

    destination = Path(path).expanduser().resolve(strict=False)
    if create_parents:
        destination.parent.mkdir(parents=True, exist_ok=True)
    elif not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    np.save(destination, np.asarray(array), allow_pickle=allow_pickle)
    # ``np.save`` appends .npy only when the supplied filename lacks it.
    return destination if destination.suffix == ".npy" else Path(f"{destination}.npy")


def inspect_tiff(
    path: str | PathLike[str],
    *,
    series_index: int = 0,
) -> TIFFMetadata:
    """Inspect one TIFF series without decoding its image pages."""

    asset = _require_materialized(path)
    with tifffile.TiffFile(asset) as tif:
        if not 0 <= series_index < len(tif.series):
            raise IndexError(
                f"TIFF series index {series_index} outside [0, {len(tif.series)})"
            )
        series = tif.series[series_index]
        pages = tuple(series.pages)
        # Per-page ``is_memmappable`` is not a reliable series capability test:
        # the project's raw TIFF reports False for every page while its complete
        # contiguous series maps successfully.  Opening a read-only memmap is a
        # metadata-only operation and does not page the volume into RAM.
        try:
            mapped = tifffile.memmap(asset, series=series_index, mode="r")
        except (OSError, TypeError, ValueError):
            memory_mappable = False
        else:
            memory_mappable = isinstance(mapped, np.memmap)
            del mapped
        return TIFFMetadata(
            path=asset,
            series_index=series_index,
            shape=tuple(int(value) for value in series.shape),
            axes=str(series.axes),
            dtype=np.dtype(series.dtype),
            page_count=len(pages),
            is_bigtiff=bool(tif.is_bigtiff),
            compression=tuple(sorted({str(page.compression) for page in pages})),
            memory_mappable=memory_mappable,
        )


def read_tiff(
    path: str | PathLike[str],
    *,
    series_index: int = 0,
    mmap_mode: Literal["r", "r+", "c"] | None = "r",
) -> np.ndarray:
    """Read a TIFF series, returning a memory map by default.

    Set ``mmap_mode=None`` only when deliberately materializing the complete
    series.  Non-contiguous or compressed TIFFs may not be memory-mappable;
    tifffile's ``ValueError`` is preserved instead of silently allocating a
    potentially multi-gigabyte array.
    """

    asset = _require_materialized(path)
    if mmap_mode is None:
        return tifffile.imread(asset, series=series_index)
    return tifffile.memmap(asset, series=series_index, mode=mmap_mode)


def read_tiff_slice(
    path: str | PathLike[str],
    z_index: int,
    *,
    series_index: int = 0,
) -> np.ndarray:
    """Decode one TIFF page corresponding to a Z slice, never the full stack."""

    asset = _require_materialized(path)
    with tifffile.TiffFile(asset) as tif:
        if not 0 <= series_index < len(tif.series):
            raise IndexError(
                f"TIFF series index {series_index} outside [0, {len(tif.series)})"
            )
        series = tif.series[series_index]
        if str(series.axes) != "ZYX":
            raise ValueError(
                f"read_tiff_slice requires a ZYX series, received axes {series.axes!r}; "
                "use read_tiff for multidimensional series"
            )
        pages = series.pages
        if not 0 <= z_index < len(pages):
            raise IndexError(f"Z index {z_index} outside [0, {len(pages)})")
        return np.asarray(pages[z_index].asarray())


def inspect_stl(path: str | PathLike[str]) -> STLMetadata:
    """Inspect ASCII or binary STL geometry without loading all triangles."""

    asset = _require_materialized(path)
    size = asset.stat().st_size
    with asset.open("rb") as handle:
        header = handle.read(84)
    if len(header) >= 84:
        face_count = struct.unpack("<I", header[80:84])[0]
        if 84 + 50 * face_count == size:
            return _inspect_binary_stl(asset, face_count)
    return _inspect_ascii_stl(asset)


def _inspect_binary_stl(path: Path, face_count: int) -> STLMetadata:
    record = np.dtype([
        ("normal", "<f4", (3,)),
        ("vertices", "<f4", (3, 3)),
        ("attributes", "<u2"),
    ])
    if face_count == 0:
        return STLMetadata(path, "binary", 0, 0, None, None)
    faces = np.memmap(path, mode="r", offset=84, dtype=record, shape=(face_count,))
    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    for begin in range(0, face_count, 200_000):
        vertices = faces[begin:begin + 200_000]["vertices"].reshape(-1, 3)
        lower = np.minimum(lower, vertices.min(axis=0))
        upper = np.maximum(upper, vertices.max(axis=0))
    return STLMetadata(
        path, "binary", face_count, face_count * 3,
        tuple(float(value) for value in lower),
        tuple(float(value) for value in upper),
    )


def _inspect_ascii_stl(path: Path) -> STLMetadata:
    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    vertices = triangles = 0
    with path.open("rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 4 and parts[0].lower() == "vertex":
                try:
                    point = np.asarray(parts[1:], dtype=float)
                except ValueError as exc:
                    raise ValueError(f"invalid ASCII STL vertex in {path}: {line.strip()}") from exc
                if not np.isfinite(point).all():
                    raise ValueError(f"nonfinite ASCII STL vertex in {path}: {line.strip()}")
                lower = np.minimum(lower, point)
                upper = np.maximum(upper, point)
                vertices += 1
            elif parts and parts[0].lower() == "endfacet":
                triangles += 1
    if vertices and vertices != triangles * 3:
        raise ValueError(
            f"ASCII STL has {vertices} vertex records but {triangles} facets in {path}"
        )
    return STLMetadata(
        path, "ascii", triangles, vertices,
        tuple(float(value) for value in lower) if vertices else None,
        tuple(float(value) for value in upper) if vertices else None,
    )
