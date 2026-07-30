#!/usr/bin/env python3
"""Run the visual-test contract with third-party pytest plugins disabled."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    repository = Path(__file__).resolve().parents[2]
    if str(repository) not in sys.path:
        sys.path.insert(0, str(repository))
    import pytest

    return int(pytest.main([
        str(Path(__file__).resolve().parent),
        "-q",
        "--maxfail=1",
        "--disable-warnings",
    ]))


if __name__ == "__main__":
    raise SystemExit(main())
