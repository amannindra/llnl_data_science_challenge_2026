"""Command-line entry point for a complete versioned clustering run."""

from __future__ import annotations

import argparse
import json

from spatial_clustering.core import run_complete_analysis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze saved lattice-defect labels without reading raw CT/STL data."
    )
    parser.add_argument("--config", required=True, help="Path to the specimen JSON configuration")
    parser.add_argument("--run-id", required=True, help="New versioned output run identifier")
    args = parser.parse_args()
    result = run_complete_analysis(args.config, args.run_id)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
