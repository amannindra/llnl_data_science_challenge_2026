"""Deterministic spatial analysis for saved octet-lattice defect records.

This module deliberately never opens CT TIFF or STL files.  It operates on a
saved all-edge classification table and registered/nominal JSON graphs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import fisher_exact


MAIN_CLASSES = {"missing", "broken", "thin"}
KNN_SOURCE_CLASSES = ("unintentional_missing", "unintentional_broken")
KNN_TARGET_CATEGORIES = (
    "present",
    "unintentional_missing",
    "unintentional_broken",
    "intentional_missing",
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ALLOWED_INPUT_SUFFIXES = {".csv", ".json"}
FORBIDDEN_RAW_SUFFIXES = {".tif", ".tiff", ".stl", ".npy"}
GROUPS = ("main", "review_required", "low_priority_uncertain", "intentional")
COLORS = {
    "missing": "#d7191c",
    "broken": "#fdae61",
    "thin": "#2c7bb6",
    "review_required": "#7b3294",
    "low_priority_uncertain": "#ffd92f",
    "intentionally_removed": "#3b82f6",
    "present": "#b8bec5",
    "uncertain": "#8b5cf6",
}


@dataclass(frozen=True)
class AnalysisConfig:
    config_path: Path
    anthony_root: Path
    specimen_id: str
    records_path: Path
    human_labels_path: Path | None
    registered_graph_path: Path
    nominal_graph_path: Path
    output_root: Path
    graph_unit_mm: float
    unit_cell_mm: float
    estimated_voxel_size_um: float
    dbscan_eps_mm: tuple[float, ...]
    dbscan_min_samples: int
    knn_k_values: tuple[int, ...]
    permutation_count: int
    random_seed: int
    build_axis: int


def _find_anthony_root(path: Path) -> Path:
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name == "Anthony":
            return candidate
    raise ValueError(f"configuration must be located under an Anthony folder: {path}")


def _resolve_from(base: Path, value: str | os.PathLike[str]) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validate_read_input(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in FORBIDDEN_RAW_SUFFIXES:
        raise ValueError(f"{label} may not be a raw CT/STL/NumPy file: {path}")
    if suffix not in ALLOWED_INPUT_SUFFIXES:
        raise ValueError(f"{label} must be CSV or JSON: {path}")
    head = path.read_bytes()[:80]
    if head.startswith(b"version https://git-lfs"):
        raise ValueError(f"{label} is a Git LFS pointer rather than real data: {path}")


def load_config(config_path: str | os.PathLike[str]) -> AnalysisConfig:
    path = Path(config_path).expanduser().resolve()
    _validate_read_input(path, "config")
    raw = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    anthony_root = _find_anthony_root(path)

    records_path = _resolve_from(base, raw["records_path"])
    registered_graph_path = _resolve_from(base, raw["registered_graph_path"])
    nominal_graph_path = _resolve_from(base, raw["nominal_graph_path"])
    human_raw = raw.get("human_labels_path")
    human_labels_path = _resolve_from(base, human_raw) if human_raw else None
    output_root = _resolve_from(base, raw["output_root"])

    _validate_read_input(records_path, "classification records")
    _validate_read_input(registered_graph_path, "registered graph")
    _validate_read_input(nominal_graph_path, "nominal graph")
    if human_labels_path is not None:
        _validate_read_input(human_labels_path, "human labels")
    if not _within(output_root, anthony_root):
        raise ValueError(f"output_root must stay inside Anthony: {output_root}")

    eps = tuple(float(v) for v in raw.get("dbscan_eps_mm", [2.28, 4.56, 6.84]))
    if not eps or any(v <= 0 for v in eps):
        raise ValueError("dbscan_eps_mm must contain positive values")
    min_samples = int(raw.get("dbscan_min_samples", 2))
    if min_samples != 2:
        raise ValueError("this implementation supports DBSCAN min_samples=2")
    knn_k_values = tuple(int(v) for v in raw.get("knn_k_values", [1, 3, 5, 10]))
    if (
        not knn_k_values
        or any(v <= 0 for v in knn_k_values)
        or len(set(knn_k_values)) != len(knn_k_values)
    ):
        raise ValueError("knn_k_values must contain unique positive integers")

    return AnalysisConfig(
        config_path=path,
        anthony_root=anthony_root,
        specimen_id=str(raw["specimen_id"]),
        records_path=records_path,
        human_labels_path=human_labels_path,
        registered_graph_path=registered_graph_path,
        nominal_graph_path=nominal_graph_path,
        output_root=output_root,
        graph_unit_mm=float(raw.get("graph_unit_mm", 2.28)),
        unit_cell_mm=float(raw.get("unit_cell_mm", 4.56)),
        estimated_voxel_size_um=float(raw.get("estimated_voxel_size_um", 57.7379)),
        dbscan_eps_mm=eps,
        dbscan_min_samples=min_samples,
        knn_k_values=knn_k_values,
        permutation_count=int(raw.get("permutation_count", 10_000)),
        random_seed=int(raw.get("random_seed", 20260723)),
        build_axis=int(raw.get("build_axis_xyz", 1)),
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _phase2c_class(row: dict[str, str]) -> tuple[str, str]:
    label = row.get("phase2c_label", "").strip().lower()
    if "designed_removed" in label:
        return "intentionally_removed", "intentional"
    if "possible_unintended_missing" in label:
        return "missing", "main"
    if "possible_unintended_disconnected" in label:
        return "broken", "main"
    if "thin" in label:
        return "thin", "main"
    if "still_review_required" in label:
        return "uncertain", "review_required"
    if "low_priority_uncertain" in label:
        return "uncertain", "low_priority_uncertain"
    if "present_like" in label:
        return "present", "present"

    # Generic adapters for future classifier records.
    generic = (
        row.get("defect_class")
        or row.get("classification")
        or row.get("integrity_state")
        or ""
    ).strip().lower()
    if generic in {"missing", "material_absent", "unintended_missing"}:
        return "missing", "main"
    if generic in {"broken", "disconnected", "likely_discontinuous", "endpoint_disconnected"}:
        return "broken", "main"
    if generic in {"thin", "thin_continuous"}:
        return "thin", "main"
    if generic in {"uncertain", "ambiguous", "review_required"}:
        return "uncertain", "review_required"
    if generic in {"intentionally_removed", "designed_removed"}:
        return "intentionally_removed", "intentional"
    if generic in {"present", "complete", "continuous", "good", "material_continuous"}:
        return "present", "present"
    raise ValueError(
        f"unsupported classification for edge {row.get('edge_id') or row.get('strut_id')}: "
        f"{label or generic!r}"
    )


def _load_human_labels(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    labels: dict[str, str] = {}
    for row in _load_csv(path):
        edge_id = row.get("edge_id", "").strip()
        value = (
            row.get("normalized_human_ct_label")
            or row.get("human_ct_label")
            or ""
        ).strip().lower()
        if not edge_id or not value:
            continue
        if edge_id in labels and labels[edge_id] != value:
            raise ValueError(f"conflicting human labels for {edge_id}")
        labels[edge_id] = value
    return labels


def _human_class(value: str, fallback_class: str, fallback_group: str) -> tuple[str, str]:
    mapping = {
        "material_absent": ("missing", "main"),
        "missing": ("missing", "main"),
        "material_disconnected": ("broken", "main"),
        "broken": ("broken", "main"),
        "material_continuous": ("present", "present"),
        "continuous": ("present", "present"),
        "ambiguous": ("uncertain", "review_required"),
        "uncertain": ("uncertain", "review_required"),
        "unexpected_material": ("uncertain", "review_required"),
    }
    return mapping.get(value, (fallback_class, fallback_group))


def _orientation(delta_xyz: np.ndarray) -> tuple[str, str]:
    tol = 1e-8
    axes = [i for i, value in enumerate(delta_xyz) if abs(float(value)) > tol]
    axis_names = "XYZ"
    if len(axes) != 2:
        return "other", "other"
    first, second = axes
    family = axis_names[first] + axis_names[second]
    vector = delta_xyz.copy()
    if vector[first] < 0:
        vector *= -1
    signs = ("+" if vector[first] >= 0 else "-") + ("+" if vector[second] >= 0 else "-")
    return family, f"{family}:{signs}"


def _region_for_width(
    midpoint: np.ndarray,
    bounds_min: np.ndarray,
    bounds_max: np.ndarray,
    width_mm: float,
) -> str:
    axis_face_distances = np.minimum(midpoint - bounds_min, bounds_max - midpoint)
    near_axes = int(np.sum(axis_face_distances <= width_mm + 1e-9))
    return {3: "corner", 2: "edge", 1: "face", 0: "interior"}[near_axes]


def _geometry_fields(
    u_nominal: np.ndarray,
    v_nominal: np.ndarray,
    u_ct: np.ndarray,
    v_ct: np.ndarray,
    bounds_min_mm: np.ndarray,
    bounds_max_mm: np.ndarray,
    graph_unit_mm: float,
    unit_cell_mm: float,
    build_axis: int,
) -> dict[str, Any]:
    u_mm = u_nominal * graph_unit_mm
    v_mm = v_nominal * graph_unit_mm
    midpoint_mm = (u_mm + v_mm) / 2.0
    midpoint_ct = (u_ct + v_ct) / 2.0
    family, direction = _orientation(v_nominal - u_nominal)
    axis_face = np.minimum(midpoint_mm - bounds_min_mm, bounds_max_mm - midpoint_mm)
    ordered = np.sort(axis_face)
    nearest_face = float(ordered[0])
    nearest_edge = float(math.hypot(ordered[0], ordered[1]))
    nearest_corner = float(np.linalg.norm(axis_face))
    center = (bounds_min_mm + bounds_max_mm) / 2.0
    center_distance = float(np.linalg.norm(midpoint_mm - center))
    central_half_width = 1.5 * unit_cell_mm
    in_center_core = bool(np.all(np.abs(midpoint_mm - center) <= central_half_width + 1e-9))
    build_index = int(
        np.clip(
            math.floor((midpoint_mm[build_axis] - bounds_min_mm[build_axis]) / unit_cell_mm),
            0,
            8,
        )
    )
    return {
        "u_ct_xyz_voxels": [float(v) for v in u_ct],
        "v_ct_xyz_voxels": [float(v) for v in v_ct],
        "midpoint_ct_xyz_voxels": [float(v) for v in midpoint_ct],
        "u_lattice_xyz_mm": [float(v) for v in u_mm],
        "v_lattice_xyz_mm": [float(v) for v in v_mm],
        "midpoint_lattice_xyz_mm": [float(v) for v in midpoint_mm],
        "orientation_family": family,
        "orientation_direction": direction,
        "nearest_face_distance_mm": nearest_face,
        "nearest_edge_distance_mm": nearest_edge,
        "nearest_corner_distance_mm": nearest_corner,
        "center_distance_mm": center_distance,
        "region_0p5_cell": _region_for_width(
            midpoint_mm, bounds_min_mm, bounds_max_mm, 0.5 * unit_cell_mm
        ),
        "region_1p0_cell": _region_for_width(
            midpoint_mm, bounds_min_mm, bounds_max_mm, unit_cell_mm
        ),
        "region_1p5_cell": _region_for_width(
            midpoint_mm, bounds_min_mm, bounds_max_mm, 1.5 * unit_cell_mm
        ),
        "center_core_3x3x3": in_center_core,
        "build_cell_index": build_index,
    }


def load_records(config: AnalysisConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registered = _load_json(config.registered_graph_path)
    nominal = _load_json(config.nominal_graph_path)
    rows = _load_csv(config.records_path)
    humans = _load_human_labels(config.human_labels_path)

    for graph_name, graph in (("registered", registered), ("nominal", nominal)):
        if not all(key in graph for key in ("junctions", "struts")):
            raise ValueError(f"{graph_name} graph lacks junctions or struts")

    reg_junction = {int(v["id"]): np.asarray(v["position"], dtype=float) for v in registered["junctions"]}
    nom_junction = {int(v["id"]): np.asarray(v["position"], dtype=float) for v in nominal["junctions"]}
    reg_strut = {int(v["id"]): v for v in registered["struts"]}
    nom_strut = {int(v["id"]): v for v in nominal["struts"]}
    if set(reg_strut) != set(nom_strut):
        raise ValueError("registered and nominal graph strut IDs do not match one-to-one")

    all_nominal = np.vstack(list(nom_junction.values())) * config.graph_unit_mm
    bounds_min_mm = np.min(all_nominal, axis=0)
    bounds_max_mm = np.max(all_nominal, axis=0)
    seen_edges: set[str] = set()
    records: list[dict[str, Any]] = []

    for row in rows:
        source_text = row.get("source_strut_id") or row.get("strut_id") or ""
        if not source_text.strip():
            raise ValueError("classification row lacks source_strut_id/strut_id")
        source_id = int(source_text)
        if source_id not in reg_strut:
            raise ValueError(f"source strut {source_id} is absent from registered graph")
        edge_id = row.get("edge_id", "").strip() or f"strut_{source_id}"
        if edge_id in seen_edges:
            raise ValueError(f"duplicate edge_id in classification records: {edge_id}")
        seen_edges.add(edge_id)

        auto_class, auto_group = _phase2c_class(row)
        human_label = humans.get(edge_id, "")
        adjudicated_class, adjudicated_group = _human_class(
            human_label, auto_class, auto_group
        )
        rs = reg_strut[source_id]
        ns = nom_strut[source_id]
        if (int(rs["junction0"]), int(rs["junction1"])) != (
            int(ns["junction0"]),
            int(ns["junction1"]),
        ):
            raise ValueError(f"registered/nominal endpoint IDs differ for strut {source_id}")
        j0, j1 = int(rs["junction0"]), int(rs["junction1"])
        geometry = _geometry_fields(
            nom_junction[j0],
            nom_junction[j1],
            reg_junction[j0],
            reg_junction[j1],
            bounds_min_mm,
            bounds_max_mm,
            config.graph_unit_mm,
            config.unit_cell_mm,
            config.build_axis,
        )
        record = {
            "specimen_id": config.specimen_id,
            "edge_id": edge_id,
            "source_strut_id": source_id,
            "node_u": row.get("node_u", "").strip() or f"J{j0}",
            "node_v": row.get("node_v", "").strip() or f"J{j1}",
            "automated_defect_class": auto_class,
            "automated_group": auto_group,
            "human_ct_label": human_label,
            "adjudicated_defect_class": adjudicated_class,
            "adjudicated_group": adjudicated_group,
            "validation_status": row.get("phase2c_status", "")
            or row.get("validation_status", ""),
            "confidence": row.get("phase2c_confidence_tier", "")
            or row.get("confidence", ""),
            "uncertainty": row.get("phase2c_reason", "")
            or row.get("uncertainty", ""),
            "source_boundary_bin": row.get("boundary_bin", "unknown") or "unknown",
            "source_orientation_key": row.get("orientation_key", "unknown") or "unknown",
            "source_label": row.get("phase2c_label", "")
            or row.get("defect_class", ""),
            "method_ids": row.get("phase2c_method_ids", "")
            or row.get("method_ids", ""),
            "assumption_ids": row.get("phase2c_assumption_ids", "")
            or row.get("assumption_ids", ""),
            "reference_ids": row.get("phase2c_reference_ids", "")
            or row.get("reference_ids", ""),
            **geometry,
        }
        records.append(record)

    metadata = {
        "registered_junction_count": len(reg_junction),
        "registered_strut_count": len(reg_strut),
        "classification_row_count": len(records),
        "human_label_count": len(humans),
        "bounds_lattice_xyz_mm": [
            [float(v) for v in bounds_min_mm],
            [float(v) for v in bounds_max_mm],
        ],
    }
    return records, metadata


def _group_records(records: Sequence[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    return [record for record in records if record["automated_group"] == group]


def _stable_components(
    records: Sequence[dict[str, Any]],
    neighbor_pairs: Iterable[tuple[int, int]],
    prefix: str,
) -> tuple[list[str | int], list[list[int]]]:
    parent = list(range(len(records)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for a, b in neighbor_pairs:
        union(int(a), int(b))
    raw: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        raw[find(index)].append(index)
    components = sorted(
        raw.values(),
        key=lambda members: min(records[index]["edge_id"] for index in members),
    )
    labels: list[str | int] = [-1] * len(records)
    for number, members in enumerate(components, start=1):
        cluster_id: str | int = f"{prefix}{number:04d}"
        for index in members:
            labels[index] = cluster_id
    return labels, components


def graph_components(
    records: Sequence[dict[str, Any]],
) -> tuple[list[str | int], list[list[int]], int]:
    by_node: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        by_node[record["node_u"]].append(index)
        by_node[record["node_v"]].append(index)
    pairs: set[tuple[int, int]] = set()
    for indices in by_node.values():
        for a_pos, a in enumerate(indices):
            for b in indices[a_pos + 1 :]:
                if a != b:
                    pairs.add((min(a, b), max(a, b)))
    labels, components = _stable_components(records, sorted(pairs), "G")
    return labels, components, len(pairs)


def dbscan_components(
    records: Sequence[dict[str, Any]], eps_mm: float
) -> tuple[list[str | int], list[list[int]], int]:
    if not records:
        return [], [], 0
    points = np.asarray([v["midpoint_lattice_xyz_mm"] for v in records], dtype=float)
    pairs = sorted(cKDTree(points).query_pairs(eps_mm, output_type="set"))
    active: set[int] = set()
    for a, b in pairs:
        active.add(a)
        active.add(b)
    if not active:
        return [-1] * len(records), [], 0
    active_records = [records[index] for index in sorted(active)]
    reindex = {old: new for new, old in enumerate(sorted(active))}
    active_pairs = [(reindex[a], reindex[b]) for a, b in pairs]
    active_labels, active_components = _stable_components(active_records, active_pairs, "D")
    labels: list[str | int] = [-1] * len(records)
    active_order = sorted(active)
    for local_index, original_index in enumerate(active_order):
        labels[original_index] = active_labels[local_index]
    components = [[active_order[index] for index in members] for members in active_components]
    return labels, components, len(pairs)


def _component_summary(
    group: str,
    method: str,
    parameter: str,
    components: Sequence[Sequence[int]],
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, members in enumerate(components, start=1):
        prefix = "G" if method == "graph_shared_junction" else "D"
        rows.append(
            {
                "group": group,
                "method": method,
                "parameter": parameter,
                "cluster_id": f"{prefix}{number:04d}",
                "size": len(members),
                "member_edge_ids": "|".join(sorted(records[i]["edge_id"] for i in members)),
            }
        )
    return rows


def analyze_data(
    records: Sequence[dict[str, Any]], config: AnalysisConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    membership: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    group_metrics: dict[str, Any] = {}
    primary_eps = min(config.dbscan_eps_mm, key=lambda value: abs(value - config.unit_cell_mm))

    for group in GROUPS:
        subset = _group_records(records, group)
        graph_labels, graph_comps, adjacent_pairs = graph_components(subset)
        dbscan_by_eps: dict[float, tuple[list[str | int], list[list[int]], int]] = {}
        summaries.extend(
            _component_summary(group, "graph_shared_junction", "shared_node", graph_comps, subset)
        )
        for eps in config.dbscan_eps_mm:
            result = dbscan_components(subset, eps)
            dbscan_by_eps[eps] = result
            summaries.extend(
                _component_summary(group, "dbscan", f"eps_mm={eps:g}", result[1], subset)
            )
        primary_labels, primary_components, primary_pairs = dbscan_by_eps[primary_eps]
        graph_sizes = [len(component) for component in graph_comps]
        dbscan_sizes = [len(component) for component in primary_components]
        group_metrics[group] = {
            "record_count": len(subset),
            "graph_component_count": len(graph_comps),
            "graph_largest_component": max(graph_sizes, default=0),
            "graph_adjacent_pair_count": adjacent_pairs,
            "graph_non_singleton_fraction": (
                sum(size for size in graph_sizes if size > 1) / len(subset) if subset else 0.0
            ),
            "dbscan_primary_eps_mm": primary_eps,
            "dbscan_cluster_count": len(primary_components),
            "dbscan_largest_cluster": max(dbscan_sizes, default=0),
            "dbscan_clustered_fraction": (
                sum(dbscan_sizes) / len(subset) if subset else 0.0
            ),
            "dbscan_neighbor_pair_count": primary_pairs,
        }
        for index, record in enumerate(subset):
            row = dict(record)
            row["analysis_group"] = group
            row["graph_cluster_id"] = graph_labels[index]
            row["dbscan_cluster_id"] = primary_labels[index]
            for eps in config.dbscan_eps_mm:
                key = f"dbscan_cluster_eps_{str(eps).replace('.', 'p')}_mm"
                row[key] = dbscan_by_eps[eps][0][index]
            membership.append(row)

    membership.sort(key=lambda row: (row["analysis_group"], row["edge_id"]))
    summaries.sort(key=lambda row: (row["group"], row["method"], row["parameter"], row["cluster_id"]))
    return membership, summaries, group_metrics


def _run_dir(config: AnalysisConfig, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must use only letters, numbers, dot, underscore, or hyphen")
    path = (config.output_root / run_id).resolve()
    if not _within(path, config.anthony_root):
        raise ValueError("resolved run directory leaves Anthony")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_bytes_idempotent(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(
                f"refusing to overwrite a different existing artifact; use a new run_id: {path}"
            )
        return
    path.write_bytes(content)


def _write_json(path: Path, value: Any) -> None:
    _write_bytes_idempotent(path, _canonical_json_bytes(value))


def _csv_bytes(rows: Sequence[dict[str, Any]], fieldnames: Sequence[str] | None = None) -> bytes:
    import io

    if fieldnames is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fieldnames = ordered
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        encoded = {
            key: json.dumps(value, separators=(",", ":"))
            if isinstance(value, (list, dict))
            else value
            for key, value in row.items()
        }
        writer.writerow(encoded)
    return output.getvalue().encode("utf-8")


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    _write_bytes_idempotent(path, _csv_bytes(rows))


def analyze_spatial_clusters(
    config_path: str | os.PathLike[str], run_id: str
) -> dict[str, Any]:
    config = load_config(config_path)
    records, metadata = load_records(config)
    membership, summaries, group_metrics = analyze_data(records, config)
    run_dir = _run_dir(config, run_id)
    _write_csv(run_dir / "cluster_membership.csv", membership)
    _write_csv(run_dir / "cluster_summary.csv", summaries)
    result = {
        "status": "ok",
        "specimen_id": config.specimen_id,
        "run_id": run_id,
        "record_validation": metadata,
        "group_metrics": group_metrics,
        "thin_status": "available"
        if any(row["automated_defect_class"] == "thin" for row in records)
        else "unavailable_no_explicit_thin_labels",
        "outputs": {
            "cluster_membership_csv": str(run_dir / "cluster_membership.csv"),
            "cluster_summary_csv": str(run_dir / "cluster_summary.csv"),
        },
    }
    _write_json(run_dir / "cluster_analysis_summary.json", result)
    return result


def _numeric_cluster_metrics(
    records: Sequence[dict[str, Any]],
    eps_values: Sequence[float],
    intentional: Sequence[dict[str, Any]] = (),
) -> dict[str, float]:
    if not records:
        return {
            "mean_nearest_neighbor_mm": math.nan,
            "graph_adjacent_pairs": 0.0,
            "graph_largest_component": 0.0,
            "graph_clustered_fraction": 0.0,
            "dbscan_largest_cluster": 0.0,
            "dbscan_clustered_fraction": 0.0,
        }
    points = np.asarray([r["midpoint_lattice_xyz_mm"] for r in records], dtype=float)
    if len(points) > 1:
        nearest = cKDTree(points).query(points, k=2)[0][:, 1]
        mean_nearest = float(np.mean(nearest))
    else:
        mean_nearest = math.inf
    _, graph_comps, graph_pairs = graph_components(records)
    _, db_comps, _ = dbscan_components(records, eps_values[1] if len(eps_values) > 1 else eps_values[0])
    values: dict[str, float] = {
        "mean_nearest_neighbor_mm": mean_nearest,
        "graph_adjacent_pairs": float(graph_pairs),
        "graph_largest_component": float(max(map(len, graph_comps), default=0)),
        "graph_clustered_fraction": float(
            sum(len(v) for v in graph_comps if len(v) > 1) / len(records)
        ),
        "dbscan_largest_cluster": float(max(map(len, db_comps), default=0)),
        "dbscan_clustered_fraction": float(
            sum(map(len, db_comps)) / len(records) if records else 0.0
        ),
    }
    for eps in eps_values:
        pair_count = len(cKDTree(points).query_pairs(float(eps), output_type="set"))
        values[f"pair_count_within_{eps:g}_mm"] = float(pair_count)
    if intentional:
        intentional_points = np.asarray(
            [r["midpoint_lattice_xyz_mm"] for r in intentional], dtype=float
        )
        distances = cKDTree(intentional_points).query(points, k=1)[0]
        intentional_nodes = {
            node for record in intentional for node in (record["node_u"], record["node_v"])
        }
        values["mean_nearest_intentional_mm"] = float(np.mean(distances))
        values["adjacent_to_intentional_count"] = float(
            sum(
                record["node_u"] in intentional_nodes or record["node_v"] in intentional_nodes
                for record in records
            )
        )
    return values


def _uniform_geometric_metrics(
    points: np.ndarray, eps_values: Sequence[float]
) -> dict[str, float]:
    if len(points) < 2:
        return {
            "mean_nearest_neighbor_mm": math.inf,
            "dbscan_largest_cluster": 0.0,
            "dbscan_clustered_fraction": 0.0,
        }
    tree = cKDTree(points)
    nearest = tree.query(points, k=2)[0][:, 1]
    values = {"mean_nearest_neighbor_mm": float(np.mean(nearest))}
    primary = eps_values[1] if len(eps_values) > 1 else eps_values[0]
    pairs = sorted(tree.query_pairs(primary, output_type="set"))
    fake = [
        {"edge_id": f"P{i:06d}", "midpoint_lattice_xyz_mm": list(point)}
        for i, point in enumerate(points)
    ]
    _, components = _stable_components(fake, pairs, "D")
    active = {index for pair in pairs for index in pair}
    active_components = [
        [index for index in component if index in active]
        for component in components
        if any(index in active for index in component)
    ]
    values["dbscan_largest_cluster"] = float(
        max(map(len, active_components), default=0)
    )
    values["dbscan_clustered_fraction"] = float(len(active) / len(points))
    for eps in eps_values:
        values[f"pair_count_within_{eps:g}_mm"] = float(
            len(tree.query_pairs(float(eps), output_type="set"))
        )
    return values


def _sample_stratified(
    eligible: Sequence[dict[str, Any]],
    observed: Sequence[dict[str, Any]],
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    pools: dict[tuple[str, str], list[int]] = defaultdict(list)
    desired: Counter[tuple[str, str]] = Counter()
    for index, record in enumerate(eligible):
        pools[(record["source_boundary_bin"], record["source_orientation_key"])].append(index)
    for record in observed:
        desired[(record["source_boundary_bin"], record["source_orientation_key"])] += 1
    selected: list[dict[str, Any]] = []
    for stratum, count in sorted(desired.items()):
        pool = pools.get(stratum, [])
        if count > len(pool):
            raise ValueError(f"stratified null lacks enough eligible records in {stratum}")
        choices = rng.choice(pool, size=count, replace=False)
        selected.extend(eligible[int(index)] for index in choices)
    return selected


def _summarize_null(
    observed: dict[str, float],
    distributions: dict[str, list[float]],
    model: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    lower_is_clustered = {"mean_nearest_neighbor_mm", "mean_nearest_intentional_mm"}
    for metric, values in distributions.items():
        array = np.asarray(values, dtype=float)
        array = array[np.isfinite(array)]
        if not len(array) or metric not in observed or not math.isfinite(observed[metric]):
            continue
        obs = float(observed[metric])
        if metric in lower_is_clustered:
            p_value = (1 + int(np.sum(array <= obs))) / (len(array) + 1)
        else:
            p_value = (1 + int(np.sum(array >= obs))) / (len(array) + 1)
        std = float(np.std(array))
        output[metric] = {
            "observed": obs,
            "null_mean": float(np.mean(array)),
            "null_95_interval": [
                float(np.quantile(array, 0.025)),
                float(np.quantile(array, 0.975)),
            ],
            "standardized_effect": (obs - float(np.mean(array))) / std if std > 0 else None,
            "one_sided_concentration_p_value": p_value,
            "permutation_count": int(len(array)),
            "model": model,
        }
    return output


def compare_random_baseline_data(
    records: Sequence[dict[str, Any]], config: AnalysisConfig
) -> dict[str, Any]:
    observed = _group_records(records, "main")
    intentional = _group_records(records, "intentional")
    eligible = [
        record
        for record in records
        if record["automated_group"] != "intentional"
    ]
    n = len(observed)
    if n < 2:
        return {
            "status": "descriptive_only_too_few_main_candidates",
            "observed_count": n,
        }
    rng = np.random.default_rng(config.random_seed)
    observed_metrics = _numeric_cluster_metrics(observed, config.dbscan_eps_mm, intentional)
    distributions: dict[str, dict[str, list[float]]] = {
        "graph_opportunity": defaultdict(list),
        "boundary_orientation_stratified": defaultdict(list),
        "uniform_3d": defaultdict(list),
    }
    bounds = np.asarray(
        [
            np.min([r["u_lattice_xyz_mm"] for r in records] + [r["v_lattice_xyz_mm"] for r in records], axis=0),
            np.max([r["u_lattice_xyz_mm"] for r in records] + [r["v_lattice_xyz_mm"] for r in records], axis=0),
        ],
        dtype=float,
    )
    for _ in range(config.permutation_count):
        chosen_indices = rng.choice(len(eligible), size=n, replace=False)
        opportunity = [eligible[int(index)] for index in chosen_indices]
        opp_metrics = _numeric_cluster_metrics(opportunity, config.dbscan_eps_mm, intentional)
        for key, value in opp_metrics.items():
            if math.isfinite(value):
                distributions["graph_opportunity"][key].append(value)

        stratified = _sample_stratified(eligible, observed, rng)
        strat_metrics = _numeric_cluster_metrics(stratified, config.dbscan_eps_mm, intentional)
        for key, value in strat_metrics.items():
            if math.isfinite(value):
                distributions["boundary_orientation_stratified"][key].append(value)

        points = rng.uniform(bounds[0], bounds[1], size=(n, 3))
        uniform_metrics = _uniform_geometric_metrics(points, config.dbscan_eps_mm)
        for key, value in uniform_metrics.items():
            if math.isfinite(value):
                distributions["uniform_3d"][key].append(value)

    return {
        "status": "ok",
        "specimen_id": config.specimen_id,
        "random_seed": config.random_seed,
        "permutation_count": config.permutation_count,
        "main_candidate_count": n,
        "observed_metrics": observed_metrics,
        "models": {
            model: _summarize_null(observed_metrics, values, model)
            for model, values in distributions.items()
        },
        "interpretation_guardrail": (
            "Uniform-3D is a sensitivity baseline, not a physical opportunity model. "
            "Manufacturing conclusions require validated defect labels and persistence "
            "under the boundary-orientation-stratified graph baseline."
        ),
    }


def compare_random_baseline(
    config_path: str | os.PathLike[str], run_id: str
) -> dict[str, Any]:
    config = load_config(config_path)
    records, _ = load_records(config)
    result = compare_random_baseline_data(records, config)
    run_dir = _run_dir(config, run_id)
    _write_json(run_dir / "random_baseline.json", result)
    return {
        "status": result["status"],
        "run_id": run_id,
        "output": str(run_dir / "random_baseline.json"),
        "main_candidate_count": result.get("main_candidate_count", 0),
    }


def _knn_category(record: dict[str, Any]) -> str | None:
    """Return a physical KNN category, or None when integrity is unresolved."""

    group = str(record["automated_group"])
    defect_class = str(record["automated_defect_class"])
    if group == "present":
        return "present"
    if group == "main" and defect_class == "missing":
        return "unintentional_missing"
    if group == "main" and defect_class == "broken":
        return "unintentional_broken"
    if group == "intentional":
        return "intentional_missing"
    if group in {"review_required", "low_priority_uncertain"}:
        return None
    if group == "main" and defect_class == "thin":
        return None
    raise ValueError(
        f"cannot map edge {record.get('edge_id')} to the requested KNN category schema"
    )


def _knn_neighbor_order(
    source_records: Sequence[dict[str, Any]],
    pool_records: Sequence[dict[str, Any]],
    max_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return deterministic all-strut neighbors for selected defect sources.

    Exact distance ties are resolved by canonical edge ID so repeated runs do
    not depend on the internal ordering chosen by a spatial-tree library.
    """

    if not source_records or len(pool_records) < 2 or max_k <= 0:
        return (
            np.empty((len(source_records), 0), dtype=int),
            np.empty((len(source_records), 0), dtype=float),
        )
    source_points = np.asarray(
        [record["midpoint_lattice_xyz_mm"] for record in source_records], dtype=float
    )
    pool_points = np.asarray(
        [record["midpoint_lattice_xyz_mm"] for record in pool_records], dtype=float
    )
    edge_ids = np.asarray([str(record["edge_id"]) for record in pool_records])
    edge_order = np.argsort(edge_ids, kind="stable")
    pool_index = {edge_id: index for index, edge_id in enumerate(edge_ids)}
    order = np.empty((len(source_records), max_k), dtype=int)
    distances = np.empty((len(source_records), max_k), dtype=float)
    for source_index, source in enumerate(source_records):
        values = np.linalg.norm(pool_points - source_points[source_index], axis=1)
        values[pool_index[str(source["edge_id"])]] = math.inf
        ranked = edge_order[np.argsort(values[edge_order], kind="stable")][:max_k]
        order[source_index] = ranked
        distances[source_index] = values[ranked]
    return order, distances


def _knn_metric_values(
    source_labels: np.ndarray,
    target_labels: np.ndarray,
    neighbor_order: np.ndarray,
    k_values: Sequence[int],
    source_classes: Sequence[str],
    target_categories: Sequence[str],
) -> dict[tuple[int, str, str, str], float]:
    values: dict[tuple[int, str, str, str], float] = {}
    for k in k_values:
        neighbor_labels = target_labels[neighbor_order[:, :k]]
        for source_class in source_classes:
            source_indices = np.flatnonzero(source_labels == source_class)
            if not len(source_indices):
                continue
            for target_class in target_categories:
                target_counts = np.sum(
                    neighbor_labels[source_indices] == target_class, axis=1
                )
                values[
                    (k, source_class, target_class, "mean_target_neighbor_fraction")
                ] = float(np.mean(target_counts / k))
                values[
                    (
                        k,
                        source_class,
                        target_class,
                        "source_with_target_neighbor_fraction",
                    )
                ] = float(np.mean(target_counts > 0))
    return values


def _permuted_within_strata(
    labels: np.ndarray,
    strata: Sequence[Sequence[int]],
    rng: np.random.Generator,
) -> np.ndarray:
    permuted = labels.copy()
    for indices in strata:
        index_array = np.asarray(indices, dtype=int)
        permuted[index_array] = rng.permutation(labels[index_array])
    return permuted


def knn_association_data(
    records: Sequence[dict[str, Any]], config: AnalysisConfig
) -> dict[str, Any]:
    """Measure all-strut neighborhoods around unintended defect candidates.

    This is a neighborhood-composition analysis, not another cluster
    assignment. Source locations stay fixed while all-strut neighborhood labels
    are permuted for the null models.
    """

    pool = sorted(records, key=lambda record: str(record["edge_id"]))
    sources = sorted(
        [
            record
            for record in records
            if record["automated_group"] == "main"
            and record["automated_defect_class"] in {"missing", "broken"}
        ],
        key=lambda record: str(record["edge_id"]),
    )
    valid_k = tuple(k for k in config.knn_k_values if k < len(pool))
    skipped_k = tuple(k for k in config.knn_k_values if k >= len(pool))
    source_labels = np.asarray([_knn_category(record) for record in sources], dtype=str)
    target_labels = np.asarray([_knn_category(record) for record in pool], dtype=object)
    source_counts = Counter(source_labels)
    target_counts = Counter(
        label for label in target_labels if label in KNN_TARGET_CATEGORIES
    )
    unresolved_pool_count = int(np.sum(target_labels == None))  # noqa: E711
    if not valid_k or not len(sources):
        return {
            "status": "descriptive_only_insufficient_sources_or_neighbors",
            "specimen_id": config.specimen_id,
            "main_candidate_count": len(sources),
            "source_counts": dict(source_counts),
            "target_category_counts": dict(target_counts),
            "unresolved_pool_count": unresolved_pool_count,
            "requested_k_values": list(config.knn_k_values),
            "analyzed_k_values": list(valid_k),
            "skipped_k_values": list(skipped_k),
            "association_rows": [],
            "neighbor_rows": [],
        }

    neighbor_order, neighbor_distances = _knn_neighbor_order(
        sources, pool, max(valid_k)
    )
    observed = _knn_metric_values(
        source_labels,
        target_labels,
        neighbor_order,
        valid_k,
        KNN_SOURCE_CLASSES,
        KNN_TARGET_CATEGORIES,
    )

    strata_map: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, record in enumerate(pool):
        strata_map[
            (record["source_boundary_bin"], record["source_orientation_key"])
        ].append(index)
    strata = [strata_map[key] for key in sorted(strata_map)]

    distributions: dict[
        str, dict[tuple[int, str, str, str], list[float]]
    ] = {
        "all_strut_label_permutation": defaultdict(list),
        "boundary_orientation_stratified_all_strut_permutation": defaultdict(list),
    }
    rng = np.random.default_rng(config.random_seed)
    for _ in range(config.permutation_count):
        unrestricted = rng.permutation(target_labels)
        stratified = _permuted_within_strata(target_labels, strata, rng)
        for model, permuted in (
            ("all_strut_label_permutation", unrestricted),
            ("boundary_orientation_stratified_all_strut_permutation", stratified),
        ):
            values = _knn_metric_values(
                source_labels,
                permuted,
                neighbor_order,
                valid_k,
                KNN_SOURCE_CLASSES,
                KNN_TARGET_CATEGORIES,
            )
            for key, value in values.items():
                distributions[model][key].append(value)

    association_rows: list[dict[str, Any]] = []
    for model, model_distributions in distributions.items():
        for key in sorted(observed):
            k, source_class, target_class, metric = key
            observed_value = float(observed[key])
            null = np.asarray(model_distributions[key], dtype=float)
            null_mean = float(np.mean(null))
            null_std = float(np.std(null))
            attraction_p = (1 + int(np.sum(null >= observed_value))) / (
                len(null) + 1
            )
            avoidance_p = (1 + int(np.sum(null <= observed_value))) / (
                len(null) + 1
            )
            association_rows.append(
                {
                    "model": model,
                    "k": k,
                    "source_class": source_class,
                    "target_class": target_class,
                    "source_count": source_counts[source_class],
                    "target_count": target_counts[target_class],
                    "metric": metric,
                    "observed": observed_value,
                    "null_mean": null_mean,
                    "null_95_interval": [
                        float(np.quantile(null, 0.025)),
                        float(np.quantile(null, 0.975)),
                    ],
                    "standardized_effect": (
                        (observed_value - null_mean) / null_std
                        if null_std > 0
                        else None
                    ),
                    "one_sided_attraction_p_value": attraction_p,
                    "attraction_q_value_bh": "",
                    "one_sided_avoidance_p_value": avoidance_p,
                    "avoidance_q_value_bh": "",
                    "permutation_count": config.permutation_count,
                }
            )

    for model in distributions:
        model_rows = [row for row in association_rows if row["model"] == model]
        for p_key, q_key in (
            ("one_sided_attraction_p_value", "attraction_q_value_bh"),
            ("one_sided_avoidance_p_value", "avoidance_q_value_bh"),
        ):
            proxy_rows = [
                {"p_value": row[p_key], "q_value_bh": ""}
                for row in model_rows
            ]
            _bh_adjust(proxy_rows)
            for row, adjusted in zip(model_rows, proxy_rows):
                row[q_key] = adjusted["q_value_bh"]

    neighbor_rows: list[dict[str, Any]] = []
    for source_index, record in enumerate(sources):
        for k in valid_k:
            neighbor_indices = neighbor_order[source_index, :k]
            categories = target_labels[neighbor_indices]
            resolved_neighbor_count = int(
                np.sum(np.isin(categories, KNN_TARGET_CATEGORIES))
            )
            neighbor_rows.append(
                {
                    "edge_id": record["edge_id"],
                    "source_strut_id": record["source_strut_id"],
                    "source_class": _knn_category(record),
                    "k": k,
                    "neighbor_edge_ids": [
                        pool[int(index)]["edge_id"] for index in neighbor_indices
                    ],
                    "neighbor_categories": [
                        category if category is not None else ""
                        for category in categories
                    ],
                    "neighbor_distances_mm": [
                        float(value)
                        for value in neighbor_distances[source_index, :k]
                    ],
                    **{
                        f"{category}_neighbor_count": int(
                            np.sum(categories == category)
                        )
                        for category in KNN_TARGET_CATEGORIES
                    },
                    "resolved_neighbor_count": resolved_neighbor_count,
                    "unresolved_neighbor_count": k - resolved_neighbor_count,
                }
            )

    unresolved_neighbor_summary = []
    for k in valid_k:
        for source_class in KNN_SOURCE_CLASSES:
            rows = [
                row
                for row in neighbor_rows
                if row["k"] == k and row["source_class"] == source_class
            ]
            if not rows:
                continue
            total_slots = len(rows) * k
            unresolved_count = sum(
                int(row["unresolved_neighbor_count"]) for row in rows
            )
            unresolved_neighbor_summary.append(
                {
                    "k": k,
                    "source_class": source_class,
                    "source_count": len(rows),
                    "unresolved_neighbor_count": unresolved_count,
                    "total_neighbor_slots": total_slots,
                    "unresolved_neighbor_fraction": (
                        unresolved_count / total_slots if total_slots else 0.0
                    ),
                }
            )

    return {
        "status": "ok",
        "specimen_id": config.specimen_id,
        "main_candidate_count": len(sources),
        "source_counts": dict(source_counts),
        "target_category_counts": dict(target_counts),
        "unresolved_pool_count": unresolved_pool_count,
        "target_category_order": list(KNN_TARGET_CATEGORIES),
        "requested_k_values": list(config.knn_k_values),
        "analyzed_k_values": list(valid_k),
        "skipped_k_values": list(skipped_k),
        "random_seed": config.random_seed,
        "permutation_count": config.permutation_count,
        "distance_space": "lattice-aligned XYZ millimetres",
        "neighbor_tie_breaker": "canonical edge_id",
        "models": {
            "all_strut_label_permutation": (
                "Keep unintended missing/broken source locations fixed and permute the "
                "four physical labels plus unresolved status across all strut locations "
                "while preserving global counts. Unresolved is a coverage status and is "
                "not tested as a target classification."
            ),
            "boundary_orientation_stratified_all_strut_permutation": (
                "Keep source locations fixed and permute all-strut neighborhood labels "
                "only within boundary-bin × orientation strata."
            ),
        },
        "association_rows": association_rows,
        "neighbor_rows": neighbor_rows,
        "unresolved_neighbor_summary": unresolved_neighbor_summary,
        "interpretation_guardrail": (
            "KNN measures the composition of all-strut neighborhoods around saved "
            "unintended missing/broken candidates. It does not classify defects, assign "
            "clusters, or establish manufacturing causation. Review-required and "
            "uncertain neighbors are retained only as unresolved coverage, never as "
            "physical target categories. Present struts dominate the lattice, so "
            "interpret observed percentages relative to the nulls."
        ),
    }


def analyze_knn_association(
    config_path: str | os.PathLike[str], run_id: str
) -> dict[str, Any]:
    config = load_config(config_path)
    records, _ = load_records(config)
    result = knn_association_data(records, config)
    run_dir = _run_dir(config, run_id)
    _write_csv(run_dir / "knn_association.csv", result["association_rows"])
    _write_csv(run_dir / "knn_neighbors.csv", result["neighbor_rows"])
    json_result = {key: value for key, value in result.items() if key != "neighbor_rows"}
    _write_json(run_dir / "knn_random_baseline.json", json_result)
    record_by_edge = {str(record["edge_id"]): record for record in records}
    max_k = max(result["analyzed_k_values"], default=0)
    max_rows = [
        row for row in result["neighbor_rows"] if int(row["k"]) == max_k
    ]
    visible_ids = {
        str(row["edge_id"]) for row in max_rows
    } | {
        str(edge_id)
        for row in max_rows
        for edge_id in row["neighbor_edge_ids"]
    }
    source_class_by_edge = {
        str(row["edge_id"]): str(row["source_class"]) for row in max_rows
    }
    viewer_payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "k_values": result["analyzed_k_values"],
        "target_categories": result["target_category_order"],
        "edges": [
            [
                edge_id,
                _knn_category(record_by_edge[edge_id]),
                record_by_edge[edge_id]["u_lattice_xyz_mm"],
                record_by_edge[edge_id]["v_lattice_xyz_mm"],
                source_class_by_edge.get(edge_id),
            ]
            for edge_id in sorted(visible_ids)
        ],
        "neighbors": {
            str(row["edge_id"]): [
                [str(edge_id), float(distance)]
                for edge_id, distance in zip(
                    row["neighbor_edge_ids"], row["neighbor_distances_mm"]
                )
            ]
            for row in max_rows
        },
        "association": [
            {
                "k": row["k"],
                "source": row["source_class"],
                "target": row["target_class"],
                "observed": row["observed"],
                "null_mean": row["null_mean"],
                "attraction_q": row["attraction_q_value_bh"],
                "avoidance_q": row["avoidance_q_value_bh"],
            }
            for row in result["association_rows"]
            if row["model"]
            == "boundary_orientation_stratified_all_strut_permutation"
            and row["metric"] == "mean_target_neighbor_fraction"
        ],
    }
    viewer_javascript = (
        "window.KNN_ALL_STRUT_DATA="
        + json.dumps(
            viewer_payload,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        + ";\n"
    ).encode("utf-8")
    _write_bytes_idempotent(run_dir / "knn_viewer_data.js", viewer_javascript)
    return {
        "status": result["status"],
        "run_id": run_id,
        "main_candidate_count": result["main_candidate_count"],
        "source_counts": result["source_counts"],
        "target_category_counts": result["target_category_counts"],
        "unresolved_pool_count": result["unresolved_pool_count"],
        "analyzed_k_values": result["analyzed_k_values"],
        "outputs": {
            "knn_association_csv": str(run_dir / "knn_association.csv"),
            "knn_neighbors_csv": str(run_dir / "knn_neighbors.csv"),
            "knn_random_baseline_json": str(
                run_dir / "knn_random_baseline.json"
            ),
            "knn_viewer_data_js": str(run_dir / "knn_viewer_data.js"),
        },
    }


def _bh_adjust(rows: list[dict[str, Any]]) -> None:
    indexed = [
        (index, float(row["p_value"]))
        for index, row in enumerate(rows)
        if row.get("p_value") not in ("", None)
    ]
    if not indexed:
        return
    indexed.sort(key=lambda item: item[1])
    count = len(indexed)
    adjusted = [1.0] * count
    running = 1.0
    for reverse_position in range(count - 1, -1, -1):
        _, p_value = indexed[reverse_position]
        rank = reverse_position + 1
        running = min(running, p_value * count / rank)
        adjusted[reverse_position] = min(1.0, running)
    for position, (row_index, _) in enumerate(indexed):
        rows[row_index]["q_value_bh"] = adjusted[position]


def boundary_distribution_data(
    records: Sequence[dict[str, Any]], config: AnalysisConfig
) -> list[dict[str, Any]]:
    eligible = [record for record in records if record["automated_group"] != "intentional"]
    dimensions = {
        "region": lambda r: r["region_1p0_cell"],
        "orientation_family": lambda r: r["orientation_family"],
        "orientation_direction": lambda r: r["orientation_direction"],
        "build_cell_index": lambda r: str(r["build_cell_index"]),
        "center_core": lambda r: "center_core" if r["center_core_3x3x3"] else "outside_center_core",
    }
    analysis_classes = [
        ("missing", lambda r: r["automated_defect_class"] == "missing"),
        ("broken", lambda r: r["automated_defect_class"] == "broken"),
        ("thin", lambda r: r["automated_defect_class"] == "thin"),
        ("review_required", lambda r: r["automated_group"] == "review_required"),
        (
            "low_priority_uncertain",
            lambda r: r["automated_group"] == "low_priority_uncertain",
        ),
    ]
    output: list[dict[str, Any]] = []
    for dimension, getter in dimensions.items():
        levels = sorted({getter(record) for record in eligible})
        for class_name, predicate in analysis_classes:
            class_total = sum(predicate(record) for record in eligible)
            class_rows: list[dict[str, Any]] = []
            for level in levels:
                in_level = [record for record in eligible if getter(record) == level]
                count = sum(predicate(record) for record in in_level)
                denominator = len(in_level)
                outside_count = class_total - count
                outside_denominator = len(eligible) - denominator
                rate = count / denominator if denominator else 0.0
                global_rate = class_total / len(eligible) if eligible else 0.0
                inferential = class_total >= 5 and denominator > 0 and outside_denominator > 0
                p_value: float | str = ""
                if inferential:
                    table = [
                        [count, denominator - count],
                        [outside_count, outside_denominator - outside_count],
                    ]
                    p_value = float(fisher_exact(table, alternative="two-sided").pvalue)
                row = {
                    "dimension": dimension,
                    "level": level,
                    "analysis_class": class_name,
                    "candidate_count": count,
                    "eligible_strut_count": denominator,
                    "candidate_percentage": 100.0 * rate,
                    "overall_class_percentage": 100.0 * global_rate,
                    "enrichment_ratio": rate / global_rate if global_rate > 0 else "",
                    "p_value": p_value,
                    "q_value_bh": "",
                    "inference_status": "inferential" if inferential else "descriptive_only_n_lt_5",
                }
                class_rows.append(row)
            _bh_adjust(class_rows)
            output.extend(class_rows)
    return output


def summarize_boundary_distribution(
    config_path: str | os.PathLike[str], run_id: str
) -> dict[str, Any]:
    config = load_config(config_path)
    records, _ = load_records(config)
    rows = boundary_distribution_data(records, config)
    run_dir = _run_dir(config, run_id)
    _write_csv(run_dir / "boundary_orientation_summary.csv", rows)
    counts = Counter(record["automated_group"] for record in records)
    classes = Counter(
        record["automated_defect_class"]
        for record in records
        if record["automated_group"] == "main"
    )
    result = {
        "status": "ok",
        "run_id": run_id,
        "output": str(run_dir / "boundary_orientation_summary.csv"),
        "group_counts": dict(counts),
        "main_class_counts": dict(classes),
    }
    _write_json(run_dir / "boundary_orientation_summary.json", result)
    return result


def _membership_lookup(
    records: Sequence[dict[str, Any]], config: AnalysisConfig
) -> dict[str, dict[str, Any]]:
    membership, _, _ = analyze_data(records, config)
    return {row["edge_id"]: row for row in membership}


def prepare_cluster_scene(
    config_path: str | os.PathLike[str],
    run_id: str,
    offset: int = 0,
    limit: int = 1000,
) -> dict[str, Any]:
    if offset < 0 or limit <= 0 or limit > 100_000:
        raise ValueError("offset must be nonnegative and limit must be between 1 and 100000")
    config = load_config(config_path)
    records, metadata = load_records(config)
    lookup = _membership_lookup(records, config)
    visible = [
        record
        for record in records
        if record["automated_group"] in GROUPS
    ]
    visible.sort(key=lambda row: (row["automated_group"], row["edge_id"]))
    page = visible[offset : offset + limit]
    edges = []
    for record in page:
        member = lookup[record["edge_id"]]
        edges.append(
            {
                "edge_id": record["edge_id"],
                "source_strut_id": record["source_strut_id"],
                "node_u": record["node_u"],
                "node_v": record["node_v"],
                "u_ct_xyz_voxels": record["u_ct_xyz_voxels"],
                "v_ct_xyz_voxels": record["v_ct_xyz_voxels"],
                "u_lattice_xyz_mm": record["u_lattice_xyz_mm"],
                "v_lattice_xyz_mm": record["v_lattice_xyz_mm"],
                "defect_class": record["automated_defect_class"],
                "analysis_group": record["automated_group"],
                "human_ct_label": record["human_ct_label"],
                "validation_status": record["validation_status"],
                "confidence": record["confidence"],
                "uncertainty": record["uncertainty"],
                "graph_cluster_id": member["graph_cluster_id"],
                "dbscan_cluster_id": member["dbscan_cluster_id"],
                "region": record["region_1p0_cell"],
                "center_core_3x3x3": record["center_core_3x3x3"],
                "orientation_family": record["orientation_family"],
                "orientation_direction": record["orientation_direction"],
                "color": COLORS.get(record["automated_defect_class"], COLORS["uncertain"]),
            }
        )
    counts = Counter(record["automated_group"] for record in visible)
    main_types = Counter(
        record["automated_defect_class"]
        for record in visible
        if record["automated_group"] == "main"
    )
    scene = {
        "schema_version": "1.0.0",
        "metadata": {
            "specimen_id": config.specimen_id,
            "coordinate_frames": {
                "ct": "XYZ voxels",
                "lattice": "XYZ millimetres",
            },
            "estimated_voxel_size_um": config.estimated_voxel_size_um,
            "voxel_size_status": "design-derived estimate, not independently calibrated",
            "total_visible_edge_count": len(visible),
            "page_offset": offset,
            "page_limit": limit,
            "page_edge_count": len(edges),
            "next_offset": offset + len(edges) if offset + len(edges) < len(visible) else None,
            "group_counts": dict(counts),
            "main_class_counts": dict(main_types),
            "graph_metadata": metadata,
        },
        "edges": edges,
        "chart_data": {
            "group_counts": dict(counts),
            "main_class_counts": dict(main_types),
            "regions": dict(Counter(record["region_1p0_cell"] for record in visible)),
            "orientations": dict(Counter(record["orientation_family"] for record in visible)),
        },
    }
    run_dir = _run_dir(config, run_id)
    page_path = run_dir / f"cluster_scene_page_{offset:06d}_{limit:06d}.json"
    _write_json(page_path, scene)
    if offset == 0 and len(edges) == len(visible):
        _write_json(run_dir / "cluster_scene.json", scene)
    return {
        "status": "ok",
        "run_id": run_id,
        "output": str(page_path),
        "complete_scene_output": (
            str(run_dir / "cluster_scene.json")
            if offset == 0 and len(edges) == len(visible)
            else None
        ),
        "page_edge_count": len(edges),
        "total_visible_edge_count": len(visible),
        "next_offset": scene["metadata"]["next_offset"],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state(start: Path) -> dict[str, Any]:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {"root": root, "head": head, "branch": branch}
    except Exception as error:  # pragma: no cover - environment dependent
        return {"status": "unavailable", "reason": str(error)}


def _build_report(
    config: AnalysisConfig,
    analysis: dict[str, Any],
    baseline: dict[str, Any],
    boundary: dict[str, Any],
    knn: dict[str, Any],
) -> str:
    metrics = analysis["group_metrics"]
    main = metrics.get("main", {})
    review = metrics.get("review_required", {})
    low = metrics.get("low_priority_uncertain", {})
    intentional = metrics.get("intentional", {})
    class_counts = boundary["main_class_counts"]
    graph_models = baseline.get("models", {})
    graph_p = (
        graph_models.get("graph_opportunity", {})
        .get("graph_largest_component", {})
        .get("one_sided_concentration_p_value")
    )
    strat_p = (
        graph_models.get("boundary_orientation_stratified", {})
        .get("graph_largest_component", {})
        .get("one_sided_concentration_p_value")
    )
    if isinstance(strat_p, (int, float)) and strat_p <= 0.05:
        baseline_interpretation = (
            "Candidate-label concentration persists after preserving the observed "
            "boundary and orientation strata. This is spatial evidence about the "
            "saved candidate labels, not proof of a manufacturing mechanism."
        )
    else:
        baseline_interpretation = (
            "Candidate-label concentration does not remain convincing after preserving "
            "the observed boundary and orientation strata."
        )
    knn_rows = [
        row
        for row in knn.get("association_rows", [])
        if row["model"]
        == "boundary_orientation_stratified_all_strut_permutation"
        and row["metric"] == "mean_target_neighbor_fraction"
    ]
    knn_rows.sort(key=lambda row: (int(row["k"]), row["source_class"]))
    knn_lookup = {
        (int(row["k"]), row["source_class"], row["target_class"]): row
        for row in knn_rows
    }
    unresolved_lookup = {
        (int(row["k"]), row["source_class"]): row
        for row in knn.get("unresolved_neighbor_summary", [])
    }
    knn_composition_rows = [
        (k, source_class)
        for k in config.knn_k_values
        for source_class in KNN_SOURCE_CLASSES
        if any(
            (k, source_class, target) in knn_lookup
            for target in KNN_TARGET_CATEGORIES
        )
    ]
    lines = [
        f"# Spatial Defect Clustering Report: {config.specimen_id}",
        "",
        "## Status",
        "",
        "This report describes **candidate-label concentration**. It does not establish",
        "manufacturing causation or convert unresolved records into confirmed defects.",
        "",
        "## Inputs and units",
        "",
        f"- Classification table: `{config.records_path}`",
        f"- Registered graph: `{config.registered_graph_path}`",
        f"- Nominal graph: `{config.nominal_graph_path}`",
        "- Registered coordinates: CT XYZ voxels",
        "- Lattice-aligned coordinates: XYZ millimetres",
        f"- Design-derived voxel estimate: {config.estimated_voxel_size_um:.4f} µm/voxel",
        "",
        "The clustering code did not read the TIFF or STL.",
        "",
        "## Candidate populations",
        "",
        f"- Main candidate count: {main.get('record_count', 0)}",
        f"  - Missing: {class_counts.get('missing', 0)}",
        f"  - Broken/disconnected: {class_counts.get('broken', 0)}",
        f"  - Thin: {class_counts.get('thin', 0)}",
        f"- Review-required records analyzed separately: {review.get('record_count', 0)}",
        f"- Low-priority uncertain records analyzed separately: {low.get('record_count', 0)}",
        f"- Intentionally removed reference struts: {intentional.get('record_count', 0)}",
        "",
        "## Main clustering measurements",
        "",
        f"- Shared-junction components: {main.get('graph_component_count', 0)}",
        f"- Largest shared-junction component: {main.get('graph_largest_component', 0)}",
        f"- Adjacent candidate pairs: {main.get('graph_adjacent_pair_count', 0)}",
        f"- DBSCAN clusters at {main.get('dbscan_primary_eps_mm', config.unit_cell_mm)} mm: "
        f"{main.get('dbscan_cluster_count', 0)}",
        f"- Largest DBSCAN cluster: {main.get('dbscan_largest_cluster', 0)}",
        "",
        "## Random baselines",
        "",
        f"- Permutations: {config.permutation_count}",
        f"- Graph-opportunity largest-component concentration p-value: {graph_p}",
        f"- Boundary×orientation-stratified p-value: {strat_p}",
        "",
        baseline_interpretation,
        "",
        "The uniform-3D model is a sensitivity comparison only because physical defects",
        "can occur on lattice struts rather than arbitrary empty-space points.",
        "",
        "## KNN all-strut neighborhood composition",
        "",
        "For each unintended missing or broken source strut, KNN finds the nearest",
        "struts from the complete 18,468-strut graph and summarizes four physical states.",
        "Review-required and uncertain records remain in the spatial neighborhood but",
        "are reported only as unresolved coverage, not as neighbor classifications.",
        "",
        "| k | Source | Present | Unintentional missing | Unintentional broken | Intentional missing | Unresolved coverage |",
        "|---:|---|---:|---:|---:|---:|---:|",
        *[
            "| {k} | {source} | {values} | {unresolved:.2f}% |".format(
                k=k,
                source=source_class.replace("_", " "),
                values=" | ".join(
                    f"{100.0 * float(knn_lookup[(k, source_class, target)]['observed']):.2f}%"
                    for target in KNN_TARGET_CATEGORIES
                ),
                unresolved=100.0
                * float(
                    unresolved_lookup.get(
                        (k, source_class), {"unresolved_neighbor_fraction": 0.0}
                    )["unresolved_neighbor_fraction"]
                ),
            )
            for k, source_class in knn_composition_rows
        ],
        "",
        "Detailed observed-versus-null comparisons, attraction q-values, and avoidance",
        "q-values for every source/target/k combination are in `knn_association.csv`.",
        "Present struts dominate the lattice, so raw percentages must be interpreted",
        "relative to the all-strut and boundary×orientation-stratified null models.",
        "",
        "## Interpretation guardrails",
        "",
        "- Missing, broken, and thin labels form the main candidate population.",
        "- Review-required and low-priority uncertain labels are never added to that count.",
        "- Intentionally removed struts are a separate design reference.",
        "- Boundary and orientation imbalance can create apparent clustering.",
        "- If concentration weakens under the stratified baseline, it should not be",
        "  presented as independent spatial evidence.",
        "- Thin-strut conclusions are unavailable when no explicit thin labels exist.",
        "",
        "## Output files",
        "",
        "- [Cluster membership](cluster_membership.csv)",
        "- [Cluster summary](cluster_summary.csv)",
        "- [Boundary and orientation summary](boundary_orientation_summary.csv)",
        "- [Random baseline](random_baseline.json)",
        "- [KNN neighbor records](knn_neighbors.csv)",
        "- [KNN association summary](knn_association.csv)",
        "- [KNN random baseline](knn_random_baseline.json)",
        "- [KNN viewer data](knn_viewer_data.js)",
        "- [3D scene handoff](cluster_scene.json)",
        "",
    ]
    return "\n".join(lines)


def run_complete_analysis(
    config_path: str | os.PathLike[str], run_id: str
) -> dict[str, Any]:
    config = load_config(config_path)
    run_dir = _run_dir(config, run_id)
    analysis = analyze_spatial_clusters(config.config_path, run_id)
    baseline_summary = compare_random_baseline(config.config_path, run_id)
    knn_summary = analyze_knn_association(config.config_path, run_id)
    boundary = summarize_boundary_distribution(config.config_path, run_id)
    records, metadata = load_records(config)
    scene = prepare_cluster_scene(
        config.config_path,
        run_id,
        offset=0,
        limit=max(1, len([r for r in records if r["automated_group"] in GROUPS])),
    )
    baseline = json.loads((run_dir / "random_baseline.json").read_text(encoding="utf-8"))
    knn = json.loads((run_dir / "knn_random_baseline.json").read_text(encoding="utf-8"))
    report = _build_report(config, analysis, baseline, boundary, knn)
    _write_bytes_idempotent(run_dir / "REPORT.md", (report + "\n").encode("utf-8"))

    normalized_config = {
        "schema_version": "1.0.0",
        "specimen_id": config.specimen_id,
        "records_path": str(config.records_path),
        "human_labels_path": str(config.human_labels_path) if config.human_labels_path else None,
        "registered_graph_path": str(config.registered_graph_path),
        "nominal_graph_path": str(config.nominal_graph_path),
        "output_root": str(config.output_root),
        "graph_unit_mm": config.graph_unit_mm,
        "unit_cell_mm": config.unit_cell_mm,
        "estimated_voxel_size_um": config.estimated_voxel_size_um,
        "dbscan_eps_mm": list(config.dbscan_eps_mm),
        "dbscan_min_samples": config.dbscan_min_samples,
        "knn_k_values": list(config.knn_k_values),
        "permutation_count": config.permutation_count,
        "random_seed": config.random_seed,
        "build_axis_xyz": config.build_axis,
        "coordinate_conventions": {
            "registered_graph": "XYZ voxels",
            "nominal_graph": "XYZ graph units",
            "lattice_physical": "XYZ millimetres",
            "tiff": "not accessed; source convention ZYX",
        },
    }
    _write_json(run_dir / "run_config.json", normalized_config)
    inputs = [
        config.config_path,
        config.records_path,
        config.registered_graph_path,
        config.nominal_graph_path,
    ]
    if config.human_labels_path:
        inputs.append(config.human_labels_path)
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.exists():
        existing_created_utc = json.loads(
            manifest_path.read_text(encoding="utf-8")
        ).get("created_utc")
    else:
        existing_created_utc = None
    manifest = {
        "schema_version": "1.0.0",
        "created_utc": existing_created_utc or datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "specimen_id": config.specimen_id,
        "input_hashes_sha256": {str(path): _sha256(path) for path in inputs},
        "git": _git_state(config.anthony_root),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "record_validation": metadata,
        "method_ids": [
            "SPATIAL-GRAPH-CC-001",
            "SPATIAL-DBSCAN-001",
            "SPATIAL-PERMUTATION-001",
            "SPATIAL-BOUNDARY-001",
            "SPATIAL-BH-001",
            "SPATIAL-KNN-ASSOC-001",
            "SPATIAL-KNN-PERM-001",
        ],
        "assumptions": [
            "registered and nominal strut IDs correspond one-to-one",
            "2.28 mm per nominal graph unit",
            "57.7379 um/voxel is design-derived, not independently calibrated",
            "uniform-3D is a sensitivity baseline only",
        ],
        "artifacts": sorted(
            {path.name for path in run_dir.iterdir() if path.is_file()}
            | {"run_manifest.json"}
        ),
    }
    _write_json(manifest_path, manifest)
    return {
        "status": "ok",
        "run_id": run_id,
        "output_dir": str(run_dir),
        "analysis": analysis,
        "baseline": baseline_summary,
        "knn": knn_summary,
        "boundary": boundary,
        "scene": scene,
        "report": str(run_dir / "REPORT.md"),
        "manifest": str(run_dir / "run_manifest.json"),
    }
