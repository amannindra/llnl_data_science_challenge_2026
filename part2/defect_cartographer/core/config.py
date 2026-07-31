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
    design_diameter_um: float = 424.0  # STL/paper nominal (58.1um/vox * r~3.65vox); replaces never-validated 350um placeholder
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

    @property
    def classification_path(self) -> Path:
        return REPO_ROOT / "Aman_Scripts" / "outputs" / "strut_defect_classification" / "strut_defect_classification.csv"

    @property
    def measurements_path(self) -> Path:
        return REPO_ROOT / "Aman_Scripts" / "outputs" / "mcp_tiff_strut_measurements" / "strut_measurements.csv"

    @property
    def metrology_path(self) -> Path:
        return REPO_ROOT / "Aman_Scripts" / "outputs" / "simple_strut_metrology" / "strut_metrology.json"

    @property
    def human_review_path(self) -> Path:
        return REPO_ROOT / "Aman_Scripts" / "outputs" / "strut_defect_classification" / "human_review_labels.csv"

    @property
    def otsu_mask_path(self) -> Path:
        return REPO_ROOT / "Aman_Scripts" / "outputs" / "mcp_tiff_strut_measurements" / "otsu_mask.tif"

    @property
    def ct_evidence_dir(self) -> Path:
        return self.output_dir / "ct_evidence"

    @property
    def dashboard_table_path(self) -> Path:
        return self.output_dir / "full_strut_classification.csv"

    @property
    def dashboard_metrics_path(self) -> Path:
        return self.output_dir / "full_pipeline_metrics.json"

    @property
    def dashboard_alignment_path(self) -> Path:
        return self.output_dir / "full_alignment.json"

    @property
    def dashboard_thickness_reference_path(self) -> Path:
        return self.output_dir / "full_thickness_reference.json"

    @property
    def dashboard_report_path(self) -> Path:
        return self.output_dir / "full_defect_report.md"

    @property
    def dashboard_scene_path(self) -> Path:
        return self.output_dir / "full_lattice_scene.npz"


DEFAULT_CONFIG = DefectConfig()
