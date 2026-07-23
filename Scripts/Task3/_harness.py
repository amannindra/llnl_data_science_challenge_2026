"""Shared helpers for the Task 3 adversarial tests.

Loads `skeletonize` straight from src/mcp_server.py (FastMCP 3.x leaves the
decorated function directly callable) and provides a tiny check/report harness.
"""
import importlib.util
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_module():
    """Import src/mcp_server.py by absolute path and hand back the module."""
    path = os.path.join(ROOT, "src", "mcp_server.py")
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_skeletonize():
    """Return (skeletonize, module)."""
    mod = load_module()
    return mod.skeletonize, mod


def cross_mask(n=24, dtype=np.uint8):
    """A simple connected 3D mask: three orthogonal bars through the center."""
    m = np.zeros((n, n, n), dtype=dtype)
    c = n // 2
    m[:, c, c] = 1
    m[c, :, c] = 1
    m[c, c, :] = 1
    return m


class Checker:
    """Minimal PASS/FAIL tracker. Each check is an attempt to disprove Task 3."""

    def __init__(self, title):
        self.title = title
        self.passed = 0
        self.failed = 0
        print("=" * 72)
        print(f"ADVERSARIAL SUITE: {title}")
        print("=" * 72)

    def check(self, name, condition, detail=""):
        tag = "PASS" if condition else "FAIL"
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        line = f"  [{tag}] {name}"
        if detail:
            line += f"  ->  {detail}"
        print(line)
        return bool(condition)

    def done(self):
        print("-" * 72)
        total = self.passed + self.failed
        print(f"  {self.passed}/{total} checks passed"
              + ("" if self.failed == 0 else f"  ({self.failed} FAILED)"))
        print()
        return 0 if self.failed == 0 else 1


def finish(code):
    sys.exit(code)
