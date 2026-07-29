from __future__ import annotations

from pathlib import Path

import pandas as pd

from defect_cartographer.core.analysis import RuleSettings
from defect_cartographer.core.config import DEFAULT_CONFIG
from defect_cartographer.core.pipeline import LEGACY_COLUMNS, _metadata


def test_output_schema_and_metadata_are_traceable() -> None:
    table = pd.DataFrame(
        {
            "strut_id": [8, 3],
            "prediction": ["intact", "missing"],
        }
    )
    metrics = {
        "sample_size": 2,
        "prediction_counts": {"intact": 1, "missing": 1},
    }
    output = _metadata(metrics, table, DEFAULT_CONFIG, RuleSettings())
    assert output["random_seed"] == 20260723
    assert len(output["sample_strut_id_sha256"]) == 64
    assert output["provisional_rules"]["missing_max_occupancy"] == 0.10
    assert output["label_version"] == "rules-v2-missing-0.10"
    assert not LEGACY_COLUMNS.intersection(table.columns)
    assert Path(DEFAULT_CONFIG.output_dir).name == "sample"
