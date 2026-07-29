"""Ensure the local Part 2 package is importable without installation."""

from __future__ import annotations

from pathlib import Path
import sys


PART2_DIR = Path(__file__).resolve().parents[1]
if str(PART2_DIR) not in sys.path:
    sys.path.insert(0, str(PART2_DIR))
