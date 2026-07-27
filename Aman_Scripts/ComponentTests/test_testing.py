#!/usr/bin/env python3
"""Adversarial checks for the shared executable-test harness."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from _harness import Checker
from Components.testing import CheckResult, finish, load_module_from_path


def main() -> int:
    outer = Checker("testing", minimum_checks=10)
    stream = io.StringIO()
    inner = Checker("inner", minimum_checks=3, stream=stream)
    outer.equal("new checker starts with zero passes", inner.passed, 0)
    outer.equal("new checker starts with zero failures", inner.failed, 0)
    outer.check("truthy check returns true", inner.check("yes", 1))
    outer.check("falsey check returns false", not inner.check("no", 0))
    outer.check("equal helper passes equal values", inner.equal("equal", [1], [1]))
    outer.check("close helper accepts tolerance", inner.close("close", 1.0, 1.0001, relative_tolerance=1e-3))
    outer.check("raises helper recognizes expected type", inner.raises("raises", ValueError, int, "x"))
    outer.equal("pass count is accurate", inner.passed, 4)
    outer.equal("failure count is accurate", inner.failed, 1)
    summary = inner.summary()
    outer.equal("summary total is accurate", summary["total"], 5)
    outer.check("minimum count is satisfied", summary["minimum_satisfied"])
    outer.equal("failed checker exits nonzero", inner.done(), 1)
    outer.check("human output contains title", "ADVERSARIAL SUITE: inner" in stream.getvalue())
    outer.check("human output contains PASS and FAIL", "[PASS]" in stream.getvalue() and "[FAIL]" in stream.getvalue())

    too_short = Checker("short", minimum_checks=2, stream=io.StringIO())
    too_short.check("only", True)
    outer.equal("minimum check count is enforced", too_short.done(), 1)

    with tempfile.TemporaryDirectory(prefix="dssi_testing_") as temporary:
        root = Path(temporary)
        summary_path = root / "nested" / "summary.json"
        written = inner.write_summary(summary_path)
        parsed = json.loads(written.read_text())
        outer.equal("summary writer creates parents", written, summary_path.resolve(strict=False))
        outer.equal("written summary round-trips", parsed["failed"], 1)

        module_path = root / "fixture.py"
        module_path.write_text("VALUE = 42\n", encoding="utf-8")
        module = load_module_from_path(module_path, "dssi_fixture_module")
        outer.equal("module loader executes source", module.VALUE, 42)
        outer.raises("module loader rejects missing path", FileNotFoundError, load_module_from_path, root / "missing.py", "missing_module")
        outer.raises("module loader rejects invalid name", ValueError, load_module_from_path, module_path, "not-valid")

    result = CheckResult("x", True, "detail")
    outer.equal("CheckResult stores name", result.name, "x")
    outer.check("CheckResult stores pass state", result.passed)
    try:
        finish(7)
    except SystemExit as exc:
        outer.equal("finish exits with requested code", exc.code, 7)
    else:
        outer.check("finish exits with requested code", False)

    runner_path = Path(__file__).with_name("run_all.py")
    runner = load_module_from_path(runner_path, "dssi_component_runner_test")
    outer.equal("runner parses plain check count", runner._counts("10/10 checks passed\n"), (10, 10))
    outer.equal(
        "runner parses JSON check count",
        runner._counts('{"passed": 12, "total": 12}\n'),
        (12, 12),
    )
    outer.equal("runner rejects output without summary", runner._counts("looks fine\n"), (None, None))
    stable = runner._stable_summary({
        "suite": "x", "passed": 1, "failed": 0, "total": 1,
        "results": [{"name": "fixture", "passed": True, "detail": "/tmp/random"}],
    })
    outer.equal("runner normalization removes volatile detail paths",
                stable["results"], [{"name": "fixture", "passed": True}])

    with tempfile.TemporaryDirectory(prefix="dssi_runner_") as temporary:
        root = Path(temporary)
        old_file, old_root, old_tests = runner.__file__, runner.ROOT, runner.TESTS
        runner.__file__, runner.ROOT = str(root / "run_all.py"), root
        try:
            (root / "pass.py").write_text(
                "print('{\"suite\":\"pass\",\"passed\":10,\"failed\":0,"
                "\"total\":10,\"minimum_satisfied\":true}')\n",
                encoding="utf-8",
            )
            runner.TESTS = ("pass.py",)
            pass_output = root / "pass_output"
            outer.equal("runner accepts valid successful test", runner.run(pass_output), 0)
            pass_summary = json.loads((pass_output / "component_test_summary.json").read_text())
            outer.check("runner persists successful status", pass_summary["success"])
            outer.equal("runner persists parsed totals", pass_summary["checks_total"], 10)

            (root / "no_summary.py").write_text("print('no count here')\n", encoding="utf-8")
            marker = root / "should_not_exist"
            (root / "marker.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
                "print('{\"suite\":\"marker\",\"passed\":10,\"failed\":0,"
                "\"total\":10,\"minimum_satisfied\":true}')\n",
                encoding="utf-8",
            )
            runner.TESTS = ("no_summary.py", "marker.py")
            invalid_output = root / "invalid_output"
            outer.equal("exit-zero test without summary fails", runner.run(invalid_output), 1)
            invalid_summary = json.loads((invalid_output / "component_test_summary.json").read_text())
            outer.equal("invalid summary status is failed", invalid_summary["tests"][0]["status"], "failed")
            outer.check("runner stops before later test after invalid summary", not marker.exists())

            runner.TESTS = ("absent.py",)
            missing_output = root / "missing_output"
            outer.equal("allow-missing permits only missing build-stage test", runner.run(missing_output, allow_missing=True), 0)
            missing_summary = json.loads((missing_output / "component_test_summary.json").read_text())
            outer.equal("missing test is represented explicitly", missing_summary["tests"][0]["status"], "missing")

            (root / "partial.py").write_text(
                "print('{\"suite\":\"partial\",\"passed\":9,\"failed\":1,"
                "\"total\":10,\"minimum_satisfied\":true}')\n",
                encoding="utf-8",
            )
            runner.TESTS = ("partial.py",)
            partial_output = root / "partial_output"
            outer.equal("partial check count fails despite exit zero", runner.run(partial_output), 1)
            partial_summary = json.loads((partial_output / "component_test_summary.json").read_text())
            outer.equal("partial check status is failed", partial_summary["tests"][0]["status"], "failed")
        finally:
            runner.__file__, runner.ROOT, runner.TESTS = old_file, old_root, old_tests
    return outer.done()


if __name__ == "__main__":
    raise SystemExit(main())
