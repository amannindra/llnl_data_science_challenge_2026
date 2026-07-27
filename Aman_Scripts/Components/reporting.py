"""Deterministic, inspectable writers for script reports and validation artifacts."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


def json_safe(value: Any) -> Any:
    """Recursively convert common scientific Python values to strict JSON values."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            string_key = str(key)
            if string_key in converted:
                raise ValueError(f"mapping keys collide after JSON string conversion: {string_key!r}")
            converted[string_key] = json_safe(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in sorted(value, key=repr)]
    if isinstance(value, float) and not np.isfinite(value):
        raise ValueError("JSON reports cannot contain NaN or infinity")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported report value type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes suitable for hashing and repeatability tests."""

    text = json.dumps(
        json_safe(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8")


def _destination(path: str | os.PathLike[str], create_parents: bool) -> Path:
    destination = Path(path).expanduser().resolve(strict=False)
    if create_parents:
        destination.parent.mkdir(parents=True, exist_ok=True)
    elif not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    return destination


def atomic_write_bytes(
    path: str | os.PathLike[str], data: bytes, *, create_parents: bool = False
) -> Path:
    """Atomically replace one file with ``data`` and return its absolute path."""

    destination = _destination(path, create_parents)
    destination_mode = (
        stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
    )
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, destination_mode)
        os.replace(temporary_name, destination)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def write_json(
    path: str | os.PathLike[str], value: Any, *, indent: int = 2,
    create_parents: bool = False,
) -> Path:
    """Write strict, key-sorted JSON atomically."""

    if indent < 0:
        raise ValueError("indent must be nonnegative")
    text = json.dumps(
        json_safe(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, indent=indent,
    ) + "\n"
    return atomic_write_bytes(path, text.encode("utf-8"), create_parents=create_parents)


def write_json_lines(
    path: str | os.PathLike[str], rows: Iterable[Any], *, create_parents: bool = False
) -> Path:
    """Write one canonical JSON record per line atomically."""

    payload = b"".join(canonical_json_bytes(row) for row in rows)
    return atomic_write_bytes(path, payload, create_parents=create_parents)


def write_csv(
    path: str | os.PathLike[str], rows: Iterable[Mapping[str, Any]],
    fieldnames: Sequence[str], *, create_parents: bool = False,
) -> Path:
    """Write a deterministic header-first UTF-8 CSV atomically."""

    if not fieldnames or len(set(fieldnames)) != len(fieldnames):
        raise ValueError("fieldnames must be nonempty and unique")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fieldnames), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        missing = set(fieldnames) - set(row)
        extra = set(row) - set(fieldnames)
        if missing or extra:
            raise ValueError(
                f"CSV row schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        writer.writerow({name: json_safe(row[name]) for name in fieldnames})
    return atomic_write_bytes(
        path, stream.getvalue().encode("utf-8"), create_parents=create_parents
    )


def file_sha256(path: str | os.PathLike[str], *, block_size: int = 1 << 20) -> str:
    """Stream a file into SHA-256 without materializing it in memory."""

    if block_size < 1:
        raise ValueError("block_size must be positive")
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise IsADirectoryError(source)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    paths: Iterable[str | os.PathLike[str]], *, root: str | os.PathLike[str] | None = None
) -> list[dict[str, Any]]:
    """Return a path-sorted size/hash manifest for existing files."""

    root_path = None if root is None else Path(root).expanduser().resolve(strict=False)
    records = []
    for item in paths:
        source = Path(item).expanduser().resolve(strict=True)
        if not source.is_file():
            raise IsADirectoryError(source)
        display = str(source if root_path is None else source.relative_to(root_path))
        records.append({
            "path": display, "bytes": source.stat().st_size,
            "sha256": file_sha256(source),
        })
    return sorted(records, key=lambda record: record["path"])
