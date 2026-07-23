"""Shared helpers for the Task 1 adversarial tests.

Loads `segment_ct_dataset` straight from src/mcp_server.py (FastMCP 3.x leaves the
decorated function directly callable) and provides a tiny check/report harness.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_segment():
    """Import segment_ct_dataset from src/mcp_server.py by absolute path."""
    path = os.path.join(ROOT, "src", "mcp_server.py")
    spec = importlib.util.spec_from_file_location("mcp_server_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.segment_ct_dataset, mod


class Checker:
    """Minimal PASS/FAIL tracker. Each check is an attempt to disprove Task 1."""

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
