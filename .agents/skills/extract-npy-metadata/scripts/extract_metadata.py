#!/usr/bin/env python3
"""Print read-only metadata and basic statistics for NumPy .npy files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Print metadata for one or more NumPy .npy files without modifying them."
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", help="input .npy file")
    return parser.parse_args()


def validate_path(raw_path: str) -> Path:
    """Return a resolved, valid .npy file path or raise ValueError."""
    path = Path(raw_path).expanduser()
    if path.suffix.lower() != ".npy":
        raise ValueError(f"not a .npy file: {raw_path}")
    if not path.exists():
        raise ValueError(f"file does not exist: {raw_path}")
    if not path.is_file():
        raise ValueError(f"not a regular file: {raw_path}")
    return path.resolve()


def display_value(value: np.generic | object) -> str:
    """Convert a NumPy scalar to a concise printable representation."""
    if isinstance(value, np.generic):
        value = value.item()
    return str(value)


def inspect_file(path: Path) -> None:
    """Load one array read-only and print its required metadata."""
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    array.flags.writeable = False

    print(f"Path: {path}")
    print(f"Shape: {array.shape}")
    print(f"Dimensions: {array.ndim}")
    print(f"Dtype: {array.dtype}")
    print(f"Element count: {array.size}")
    print(f"File size (bytes): {path.stat().st_size}")

    if array.size == 0:
        print("Minimum: N/A (empty array)")
        print("Maximum: N/A (empty array)")
        print("Mean: N/A (empty array)")
        print("Nonzero count: 0")
    else:
        print(f"Minimum: {display_value(np.min(array))}")
        print(f"Maximum: {display_value(np.max(array))}")
        print(f"Mean: {display_value(np.mean(array))}")
        print(f"Nonzero count: {np.count_nonzero(array)}")


def main() -> int:
    """Inspect every requested path and return nonzero if any input fails."""
    args = parse_args()
    exit_status = 0

    for index, raw_path in enumerate(args.paths):
        if index:
            print()
        try:
            path = validate_path(raw_path)
            inspect_file(path)
        except Exception as exc:
            print(f"ERROR: {raw_path}: {exc}", file=sys.stderr)
            exit_status = 1

    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
