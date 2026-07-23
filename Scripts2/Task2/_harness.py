"""Shared helpers for the Task 2 adversarial tests against src2 only."""

from __future__ import annotations

import importlib.util
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_visualize():
    """Import the Task 2 tool and its FastMCP server from src2 by path."""
    path = os.path.join(ROOT, "src2", "mcp_server.py")
    spec = importlib.util.spec_from_file_location("mcp_server_task2_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.visualize_slice, module


class Checker:
    """Minimal PASS/FAIL tracker for attempts to disprove Task 2."""

    def __init__(self, title: str):
        self.title = title
        self.passed = 0
        self.failed = 0
        print("=" * 72)
        print(f"ADVERSARIAL SUITE: {title}")
        print("=" * 72)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        tag = "PASS" if condition else "FAIL"
        self.passed += int(bool(condition))
        self.failed += int(not bool(condition))
        print(f"  [{tag}] {name}" + (f"  ->  {detail}" if detail else ""))
        return bool(condition)

    def done(self) -> int:
        total = self.passed + self.failed
        print("-" * 72)
        print(f"  {self.passed}/{total} checks passed" + ("" if not self.failed else f"  ({self.failed} FAILED)"))
        print()
        return 0 if self.failed == 0 else 1


def finish(code: int) -> None:
    sys.exit(code)
