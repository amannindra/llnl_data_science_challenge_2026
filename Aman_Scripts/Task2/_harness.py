"""Shared Task 2 helpers backed by the reusable Aman components."""

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

    path = repository_path("Aman_src", "mcp_server.py", root=ROOT, must_exist=True)
    return load_module_from_path(path, "mcp_server_under_test")


def load_visualize():
    """Return ``(visualize_slice, module)``."""

    module = load_module()
    return module.visualize_slice, module


def read_luminance(path):
    """Read a saved image as normalized float luminance with shape ``(H, W)``."""

    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.float64) / 255.0
