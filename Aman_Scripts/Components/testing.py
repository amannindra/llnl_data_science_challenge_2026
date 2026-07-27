"""Shared fail-fast-friendly check collection for executable script tests."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, TextIO

from .reporting import write_json


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class Checker:
    """Collect named checks, print readable status, and enforce a minimum count."""

    def __init__(
        self, title: str, *, minimum_checks: int = 0, stream: TextIO | None = None
    ) -> None:
        if minimum_checks < 0:
            raise ValueError("minimum_checks must be nonnegative")
        self.title = title
        self.minimum_checks = minimum_checks
        self.stream = stream or sys.stdout
        self.results: list[CheckResult] = []
        print("=" * 72, file=self.stream)
        print(f"ADVERSARIAL SUITE: {title}", file=self.stream)
        print("=" * 72, file=self.stream)

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    def check(self, name: str, condition: Any, detail: str = "") -> bool:
        result = CheckResult(str(name), bool(condition), str(detail))
        self.results.append(result)
        line = f"  [{'PASS' if result.passed else 'FAIL'}] {result.name}"
        if result.detail:
            line += f"  ->  {result.detail}"
        print(line, file=self.stream)
        return result.passed

    def equal(self, name: str, actual: Any, expected: Any) -> bool:
        return self.check(name, actual == expected, f"actual={actual!r}, expected={expected!r}")

    def close(
        self, name: str, actual: float, expected: float, *,
        relative_tolerance: float = 1e-9, absolute_tolerance: float = 0.0,
    ) -> bool:
        passed = math.isclose(
            actual, expected, rel_tol=relative_tolerance, abs_tol=absolute_tolerance
        )
        return self.check(name, passed, f"actual={actual!r}, expected={expected!r}")

    def raises(
        self, name: str, exception_type: type[BaseException], function: Callable[..., Any],
        *args: Any, **kwargs: Any,
    ) -> bool:
        try:
            function(*args, **kwargs)
        except exception_type as exc:
            return self.check(name, True, f"raised {type(exc).__name__}")
        except BaseException as exc:  # noqa: BLE001 - test harness records the mismatch.
            return self.check(name, False, f"raised {type(exc).__name__}, expected {exception_type.__name__}")
        return self.check(name, False, f"did not raise {exception_type.__name__}")

    def summary(self) -> dict[str, Any]:
        count_failure = len(self.results) < self.minimum_checks
        return {
            "suite": self.title,
            "minimum_checks": self.minimum_checks,
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed + int(count_failure),
            "minimum_satisfied": not count_failure,
            "results": [asdict(result) for result in self.results],
        }

    def write_summary(self, path: str | Path) -> Path:
        return write_json(path, self.summary(), create_parents=True)

    def done(self) -> int:
        print("-" * 72, file=self.stream)
        total = len(self.results)
        minimum_failure = total < self.minimum_checks
        suffix = "" if self.failed == 0 else f"  ({self.failed} FAILED)"
        if minimum_failure:
            suffix += f"  (minimum {self.minimum_checks} checks required)"
        print(f"  {self.passed}/{total} checks passed{suffix}", file=self.stream)
        print(file=self.stream)
        print(json.dumps(self.summary(), sort_keys=True), file=self.stream)
        return 0 if self.failed == 0 and not minimum_failure else 1


CheckCollector = Checker


def load_module_from_path(path: str | Path, module_name: str) -> ModuleType:
    """Load a Python file under an explicit module name with clear validation."""

    source = Path(path).expanduser().resolve(strict=False)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not module_name or not module_name.isidentifier():
        raise ValueError("module_name must be a nonempty Python identifier")
    specification = importlib.util.spec_from_file_location(module_name, source)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot create an import specification for {source}")
    module = importlib.util.module_from_spec(specification)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module


def finish(code: int) -> None:
    """Exit an executable test with its accumulated status code."""

    raise SystemExit(int(code))
