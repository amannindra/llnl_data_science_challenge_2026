#!/usr/bin/env python3
"""Adversarial checks for repository and output path handling."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Callable


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from Scripts.Components.paths import (  # noqa: E402
    RepositoryNotFoundError,
    UnsafePathError,
    data_path,
    ensure_within,
    find_repository_root,
    output_path,
    relative_repository_path,
    repository_path,
    scripts_path,
)


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.results: list[dict[str, object]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}: {detail}")
        self.results.append({"name": name, "passed": bool(condition), "detail": detail})

    def raises(self, name: str, error: type[BaseException], operation: Callable[[], object]) -> None:
        try:
            operation()
        except error:
            self.check(name, True)
        except Exception as exc:  # pragma: no cover - diagnostic branch
            self.check(name, False, f"raised {type(exc).__name__}, expected {error.__name__}")
        else:
            self.check(name, False, f"did not raise {error.__name__}")


def main() -> int:
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="dssi_paths_") as temporary:
        sandbox = Path(temporary).resolve()
        root = (sandbox / "project").resolve()
        (root / "Scripts").mkdir(parents=True)
        (root / "data" / "nested").mkdir(parents=True)
        source = root / "Scripts" / "tool.py"
        source.write_text("# fixture\n", encoding="utf-8")

        checks.check(
            "discovers root from nested directory",
            find_repository_root(root / "data" / "nested") == root,
        )
        checks.check("discovers root from file", find_repository_root(source) == root)

        inner = root / "data" / "nested" / "inner_project"
        (inner / "Scripts").mkdir(parents=True)
        (inner / "data").mkdir()
        checks.check("nearest marked ancestor wins", find_repository_root(inner) == inner)
        checks.check("default discovery finds real repository", find_repository_root() == REPOSITORY)

        checks.raises("empty marker list rejected", ValueError, lambda: find_repository_root(root, markers=()))
        checks.raises(
            "absolute marker rejected",
            ValueError,
            lambda: find_repository_root(root, markers=(root / "data",)),
        )
        checks.raises(
            "parent-traversal marker rejected",
            ValueError,
            lambda: find_repository_root(root, markers=("../data",)),
        )
        unmarked = sandbox / "unmarked" / "child"
        unmarked.mkdir(parents=True)
        checks.raises(
            "missing repository rejected",
            RepositoryNotFoundError,
            lambda: find_repository_root(unmarked),
        )

        checks.check(
            "relative path remains in base",
            ensure_within(root, "data/example.npy") == root / "data" / "example.npy",
        )
        checks.check(
            "absolute in-base path accepted",
            ensure_within(root, root / "Scripts") == root / "Scripts",
        )
        checks.raises(
            "dot-dot escape rejected",
            UnsafePathError,
            lambda: ensure_within(root, "../outside"),
        )
        checks.raises(
            "absolute escape rejected",
            UnsafePathError,
            lambda: ensure_within(root, sandbox / "outside"),
        )

        outside = sandbox / "outside"
        outside.mkdir()
        link = root / "data" / "escape_link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            checks.check("symlink escape rejected", True, "symlinks unavailable; platform-safe skip")
        else:
            checks.raises(
                "symlink escape rejected",
                UnsafePathError,
                lambda: ensure_within(root, "data/escape_link/payload"),
            )

        checks.check(
            "repository_path joins safely",
            repository_path("data", "nested", root=root) == root / "data" / "nested",
        )
        checks.check("data_path uses data base", data_path("nested", root=root) == root / "data" / "nested")
        checks.check("scripts_path uses Scripts base", scripts_path("tool.py", root=root) == source)
        checks.raises(
            "must_exist rejects absent path",
            FileNotFoundError,
            lambda: data_path("absent.bin", root=root, must_exist=True),
        )

        generated = output_path("component", root=root)
        checks.check("output lookup has no write side effect", not generated.exists())
        created = output_path("component", root=root, create=True)
        checks.check("explicit output creation creates directory", created.is_dir())
        checks.raises(
            "output helper rejects escape",
            UnsafePathError,
            lambda: output_path("..", "..", "outside", root=root),
        )
        checks.check(
            "repository-relative conversion is stable",
            relative_repository_path(source, root=root) == Path("Scripts/tool.py"),
        )
        checks.raises(
            "repository-relative conversion rejects outside path",
            UnsafePathError,
            lambda: relative_repository_path(outside, root=root),
        )

    total = checks.passed + checks.failed
    print(f"{checks.passed}/{total} path checks passed")
    print(json.dumps({"suite": "paths", "passed": checks.passed, "failed": checks.failed,
                      "total": total, "minimum_satisfied": total >= 10,
                      "results": checks.results}, sort_keys=True))
    return 0 if checks.failed == 0 and total >= 10 else 1


if __name__ == "__main__":
    raise SystemExit(main())
