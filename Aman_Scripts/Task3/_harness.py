"""Shared Task 3 helpers backed by the reusable Scripts components."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.paths import find_repository_root, repository_path  # noqa: E402
from Components.testing import Checker, finish, load_module_from_path  # noqa: E402,F401


ROOT = str(find_repository_root(__file__))


def load_module():
    """Import and return the production MCP module."""

    path = repository_path("src", "mcp_server.py", root=ROOT, must_exist=True)
    return load_module_from_path(path, "mcp_server_under_test")


def load_skeletonize():
    """Return ``(skeletonize, module)``."""

    module = load_module()
    return module.skeletonize, module


def cross_mask(n=24, dtype=np.uint8):
    """Build three orthogonal bars through a cubic mask's center."""

    mask = np.zeros((n, n, n), dtype=dtype)
    center = n // 2
    mask[:, center, center] = 1
    mask[center, :, center] = 1
    mask[center, center, :] = 1
    return mask
