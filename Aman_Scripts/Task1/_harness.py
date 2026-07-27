"""Shared Task 1 helpers backed by the reusable Scripts components."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.paths import find_repository_root, repository_path  # noqa: E402
from Components.testing import Checker, finish, load_module_from_path  # noqa: E402,F401


ROOT = str(find_repository_root(__file__))


def load_segment():
    """Import ``segment_ct_dataset`` from the production MCP module."""

    path = repository_path("src", "mcp_server.py", root=ROOT, must_exist=True)
    module = load_module_from_path(path, "mcp_server_under_test")
    return module.segment_ct_dataset, module
