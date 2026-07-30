#!/usr/bin/env python3
"""Run every isolated strut-comparison test with fail-fast behavior."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    # The DSC environment auto-loads napari's pytest plugin, which attempts to
    # write icon caches outside the project sandbox.  These numerical tests do
    # not use napari, so disabling third-party plugin discovery is intentional.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    directory = Path(__file__).resolve().parent
    return int(pytest.main([
        str(directory),
        "-q",
        "--maxfail=1",
        "--disable-warnings",
    ]))


if __name__ == "__main__":
    raise SystemExit(main())

