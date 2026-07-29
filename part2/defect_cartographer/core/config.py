"""Configuration and specimen metadata for the deterministic MVP core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PART2_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PART2_DIR.parent


@dataclass(frozen=True)
class DefectConfig:
    """Paths and reproducibility settings for the 60-strut MVP."""

    ct_path: Path = (
        REPO_ROOT
        / "data"
        / "missing_struts"
        / "tif_stacks"
        / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
    )
    graph_path: Path = (
        REPO_ROOT
        / "data"
        / "missing_struts"
        / "registered_jsons"
        / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
    )
    output_dir: Path = PART2_DIR / "artifacts" / "sample"
    sample_size: int = 60
    random_seed: int = 20_260_723
    voxel_spacing_um: tuple[float, float, float] = (58.09, 58.09, 58.09)
    design_diameter_um: float = 350.0
    axis_permutation: tuple[int, int, int] = (2, 1, 0)
    alignment_struts: int = 600
    alignment_search_radius_vox: int = 4
    analysis_search_radius_vox: int = 4
    threshold_factors: tuple[float, float, float] = (0.97, 1.0, 1.03)

    @property
    def alignment_path(self) -> Path:
        return self.output_dir / "alignment.json"

    @property
    def sample_path(self) -> Path:
        return self.output_dir / "sampled_struts.csv"

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "pipeline_metrics.json"


DEFAULT_CONFIG = DefectConfig()
