#!/usr/bin/env python3
"""Analyze lattice JSON topology and its existing CT-frame registration.

The module is side-effect free on import.  Its historical centerline-occupancy
calculation is retained only as an explicitly requested, unvalidated legacy
diagnostic; it is not the deferred TIFF defect detector.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:  # Package import.
    from .Components.asset_io import detect_lfs_pointer, read_tiff
    from .Components.coordinates import homogeneous_matrix
    from .Components.lattice_graph import (
        LatticeGraph,
        load_lattice_graph,
        summarize_components,
        weld_coincident_nodes,
    )
    from .Components.legacy_occupancy import centerline_occupancy
    from .Components.paths import data_path, find_repository_root, output_path
    from .Components.reporting import write_csv
except ImportError:  # Direct execution.
    from Components.asset_io import detect_lfs_pointer, read_tiff
    from Components.coordinates import homogeneous_matrix
    from Components.lattice_graph import (
        LatticeGraph,
        load_lattice_graph,
        summarize_components,
        weld_coincident_nodes,
    )
    from Components.legacy_occupancy import centerline_occupancy
    from Components.paths import data_path, find_repository_root, output_path
    from Components.reporting import write_csv


ROOT = find_repository_root(__file__)
OUT = output_path(root=ROOT)
DESIGN_9X9X9 = data_path("missing_struts", "octet_truss_9x9x9.json", root=ROOT)
REGISTERED = data_path(
    "missing_struts", "registered_jsons",
    "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json", root=ROOT,
)
CT_TIF = data_path("9x9x9_octet_lattice", "9x9x9_octet_lattice.tif", root=ROOT)
GRAPH_FILES = (
    ("polyhedron_1x1x1", data_path("unitcell", "polyhedron_1x1x1.json", root=ROOT)),
    ("octet_truss_8x8x8", data_path("octet_truss_8x8x8", "octet_truss_8x8x8.json", root=ROOT)),
    ("octet_truss_9x9x9_design", DESIGN_9X9X9),
    ("octet_truss_9x9x9_registered", REGISTERED),
)


def _positions(graph: LatticeGraph) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    by_id = {junction.id: np.asarray(junction.position, dtype=float) for junction in graph.junctions}
    return np.asarray([junction.position for junction in graph.junctions], dtype=float), by_id


def _component_sizes(graph: LatticeGraph) -> tuple[int, ...]:
    adjacency = {junction.id: set() for junction in graph.junctions}
    for strut in graph.struts:
        if strut.junction0 in adjacency and strut.junction1 in adjacency:
            adjacency[strut.junction0].add(strut.junction1)
            adjacency[strut.junction1].add(strut.junction0)
    unseen = {node for node, neighbors in adjacency.items() if neighbors}
    sizes: list[int] = []
    while unseen:
        stack, size = [min(unseen)], 0
        unseen.remove(stack[0])
        while stack:
            node = stack.pop()
            size += 1
            for neighbor in adjacency[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        sizes.append(size)
    return tuple(sorted(sizes, reverse=True))


def graph_summary(graph: LatticeGraph) -> dict[str, Any]:
    """Return raw-record and physically welded topology metrics."""

    points, positions = _positions(graph)
    if not len(points):
        raise ValueError("lattice graph has no junctions")
    degree = Counter({junction.id: 0 for junction in graph.junctions})
    lengths, thicknesses = [], []
    for strut in graph.struts:
        degree[strut.junction0] += 1
        degree[strut.junction1] += 1
        lengths.append(float(np.linalg.norm(positions[strut.junction1] - positions[strut.junction0])))
        if strut.thickness is not None:
            thicknesses.append(float(strut.thickness))
    welded = weld_coincident_nodes(graph)
    welded_connectivity = summarize_components(welded)
    welded_degree = Counter({node.id: 0 for node in welded.nodes})
    for strut in welded.struts:
        welded_degree[strut.node0] += 1
        welded_degree[strut.node1] += 1
    return {
        "junction_records": len(graph.junctions),
        "strut_records": len(graph.struts),
        "unit_cells": len(graph.unit_cells),
        "bbox_min": points.min(axis=0),
        "bbox_max": points.max(axis=0),
        "degree_distribution": dict(sorted(Counter(degree.values()).items())),
        "raw_component_sizes": _component_sizes(graph),
        "strut_lengths": np.asarray(lengths),
        "thicknesses": np.asarray(thicknesses),
        "unique_physical_nodes": len(welded.nodes),
        "unique_physical_struts": len(welded.struts),
        "welded_component_count": welded_connectivity.component_count,
        "welded_largest_component": welded_connectivity.largest_component_size,
        "welded_degree_distribution": dict(sorted(Counter(welded_degree.values()).items())),
    }


def save_wireframe(graph: LatticeGraph, name: str, destination: Path) -> None:
    """Render one graph in XYZ order using its source-record connectivity."""

    points, positions = _positions(graph)
    figure = plt.figure(figsize=(8, 8))
    axis = figure.add_subplot(111, projection="3d")
    for strut in graph.struts:
        left, right = positions[strut.junction0], positions[strut.junction1]
        axis.plot(*zip(left, right), color="tab:blue", lw=0.6, alpha=0.7)
    axis.scatter(points[:, 0], points[:, 1], points[:, 2], color="red", s=6)
    axis.set_title(f"{name}: {len(graph.junctions)} nodes / {len(graph.struts)} struts")
    axis.view_init(elev=25, azim=45)
    figure.tight_layout()
    figure.savefig(destination, dpi=120)
    plt.close(figure)


def _umeyama(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Return the least-squares similarity transform ``target ~= s R source+t``."""

    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError("source and target must have equal shape (N, 3)")
    source_mean, target_mean = source.mean(0), target.mean(0)
    source_centered, target_centered = source - source_mean, target - target_mean
    covariance = target_centered.T @ source_centered / len(source)
    left, singular_values, right_t = np.linalg.svd(covariance)
    parity = np.sign(np.linalg.det(left @ right_t))
    rotation = left @ np.diag([1.0, 1.0, parity]) @ right_t
    variance = float(np.square(source_centered).sum() / len(source))
    scale = float(np.dot(singular_values, [1.0, 1.0, parity]) / variance)
    translation = target_mean - scale * rotation @ source_mean
    return scale, rotation, translation


def registration_summary(design: LatticeGraph, registered: LatticeGraph) -> dict[str, Any]:
    """Recover and validate the existing design-to-registered similarity transform."""

    design_positions = {junction.id: junction.position for junction in design.junctions}
    registered_positions = {junction.id: junction.position for junction in registered.junctions}
    common_ids = sorted(set(design_positions) & set(registered_positions))
    if len(common_ids) < 3:
        raise ValueError("registration needs at least three matched junction IDs")
    source = np.asarray([design_positions[node] for node in common_ids], dtype=float)
    target = np.asarray([registered_positions[node] for node in common_ids], dtype=float)
    scale, rotation, translation = _umeyama(source, target)
    predicted = (scale * (rotation @ source.T)).T + translation
    residuals = np.linalg.norm(predicted - target, axis=1)
    angle = float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))))
    design_edges = {(strut.id, strut.endpoints) for strut in design.struts}
    registered_edges = {(strut.id, strut.endpoints) for strut in registered.struts}
    return {
        "matched_junctions": len(common_ids),
        "same_junction_ids": set(design_positions) == set(registered_positions),
        "same_connectivity": design_edges == registered_edges,
        "scale_voxels_per_design_unit": scale,
        "rotation_degrees": angle,
        "translation_xyz_voxels": translation,
        "mean_residual_voxels": float(residuals.mean()),
        "max_residual_voxels": float(residuals.max()),
        "matrix": homogeneous_matrix(rotation=rotation, translation=translation, scale=scale),
    }


def save_registration_overlay(graph: LatticeGraph, tiff_path: Path, destination: Path) -> None:
    """Overlay the already-registered graph on a thin raw-CT maximum projection."""

    volume = read_tiff(tiff_path)
    points, positions = _positions(graph)
    z_index, half_width = int(np.median(points[:, 2])), 5
    slab = np.asarray(volume[max(0, z_index-half_width):z_index+half_width+1], dtype=np.float32).max(0)
    low, high = np.percentile(slab, [2, 99.5])
    slab = np.clip((slab - low) / (high - low + 1e-9), 0, 1)
    near = np.abs(points[:, 2] - z_index) <= half_width
    figure, axes = plt.subplots(1, 2, figsize=(16, 8))
    for axis, with_graph in zip(axes, (False, True)):
        axis.imshow(slab, cmap="gray", origin="upper")
        if with_graph:
            for strut in graph.struts:
                left, right = positions[strut.junction0], positions[strut.junction1]
                if abs((left[2] + right[2]) / 2 - z_index) <= half_width:
                    axis.plot([left[0], right[0]], [left[1], right[1]], color="cyan", lw=0.8, alpha=0.7)
            axis.scatter(points[near, 0], points[near, 1], s=18, facecolors="none", edgecolors="red")
            axis.set_title(f"registered graph overlay (z={z_index})")
        else:
            axis.set_title(f"raw CT slab MIP (z={z_index}±{half_width})")
        axis.set_xlim(points[:, 0].min()-20, points[:, 0].max()+20)
        axis.set_ylim(points[:, 1].max()+20, points[:, 1].min()-20)
        axis.axis("off")
    figure.tight_layout()
    figure.savefig(destination, dpi=120, bbox_inches="tight")
    plt.close(figure)


def node_taxonomy(graph: LatticeGraph) -> dict[str, Any]:
    """Summarize record multiplicity and physical octet node roles."""

    welded = weld_coincident_nodes(graph)
    multiplicity = Counter(len(node.source_junction_ids) for node in welded.nodes)
    degree = Counter({node.id: 0 for node in welded.nodes})
    for strut in welded.struts:
        degree[strut.node0] += 1
        degree[strut.node1] += 1
    degree_distribution = Counter(degree.values())
    roles = {3: "corner", 5: "edge", 8: "face", 12: "interior"}
    return {
        "junction_records": len(graph.junctions),
        "physical_nodes": len(welded.nodes),
        "records_per_node": dict(sorted(multiplicity.items())),
        "degree_distribution": dict(sorted(degree_distribution.items())),
        "role_counts": {roles.get(value, f"degree_{value}"): count for value, count in sorted(degree_distribution.items())},
    }


def strut_geometry(graph: LatticeGraph) -> dict[str, Any]:
    """Summarize lengths and unoriented XYZ directions of source struts."""

    _, positions = _positions(graph)
    vectors = np.asarray([positions[s.junction1] - positions[s.junction0] for s in graph.struts])
    lengths = np.linalg.norm(vectors, axis=1)
    unit = vectors / lengths[:, None]
    flip = (unit[:, 0] < 0) | ((unit[:, 0] == 0) & (unit[:, 1] < 0)) | ((unit[:, 0] == 0) & (unit[:, 1] == 0) & (unit[:, 2] < 0))
    unit[flip] *= -1
    axes, counts = np.unique(np.round(unit, 2), axis=0, return_counts=True)
    return {
        "count": len(graph.struts), "length_mean": float(lengths.mean()),
        "length_std": float(lengths.std()),
        "orientations": [(axis.tolist(), int(count)) for axis, count in zip(axes, counts)],
    }


def print_graph_summary(name: str, summary: dict[str, Any]) -> None:
    lengths, thicknesses = summary["strut_lengths"], summary["thicknesses"]
    print("=" * 60, name, "=" * 60, sep="\n")
    print(f"junctions  : {summary['junction_records']}")
    print(f"struts     : {summary['strut_records']}")
    print(f"unit_cells : {summary['unit_cells']}")
    print(f"bbox       : {np.round(summary['bbox_min'], 3)} -> {np.round(summary['bbox_max'], 3)}")
    print(f"raw graph  : {len(summary['raw_component_sizes'])} active component(s)")
    print(f"welded     : {summary['unique_physical_nodes']} nodes / {summary['unique_physical_struts']} struts; "
          f"{summary['welded_component_count']} component(s)")
    if lengths.size:
        print(f"strut len  : min {lengths.min():.3f}, max {lengths.max():.3f}, mean {lengths.mean():.3f}")
    if thicknesses.size:
        print(f"thickness  : min {thicknesses.min():.3f}, max {thicknesses.max():.3f}")


def run_legacy_occupancy(
    graph: LatticeGraph, tiff_path: Path, destination: Path
) -> dict[str, Path]:
    """Run the preserved heuristic and write its two historical artifacts.

    The output is diagnostic only.  On the real scan this method previously
    labeled 20.98% of struts as missing, far above the paper's specimen rate,
    because it confounds boundary/orientation effects with physical defects.
    """

    print("WARNING: running unvalidated legacy occupancy diagnostic (not defect ground truth)")
    volume = read_tiff(tiff_path)
    result = centerline_occupancy(volume, graph)
    histogram, _ = np.histogram(result.occupancy, bins=10, range=(0, 1))
    print(f"material threshold: {result.material_threshold:.0f}")
    print(f"occupancy histogram: {histogram.tolist()}")
    print(
        f"candidate-missing: {int(result.candidate_missing.sum())}/{len(result.occupancy)} "
        f"({100 * float(result.candidate_missing.mean()):.2f}%)"
    )

    points, positions = _positions(graph)
    z_index, half_width = int(np.median(points[:, 2])), 6
    slab = np.asarray(
        volume[max(0, z_index-half_width):z_index+half_width+1], dtype=np.float32
    ).max(0)
    low, high = np.percentile(slab, [2, 99.5])
    slab = np.clip((slab - low) / (high - low + 1e-9), 0, 1)
    in_slab = np.abs(result.midpoints_xyz[:, 2] - z_index) <= half_width
    figure, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes[0].hist(result.occupancy, bins=40, color="tab:blue")
    axes[0].axvline(result.missing_cutoff, color="red", ls="--", label="legacy cutoff")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("legacy centerline occupancy")
    axes[0].set_ylabel("strut count (log)")
    axes[0].legend()
    axes[1].imshow(slab, cmap="gray", origin="upper")
    for index, strut in enumerate(graph.struts):
        if not in_slab[index]:
            continue
        left, right = positions[strut.junction0], positions[strut.junction1]
        missing = bool(result.candidate_missing[index])
        axes[1].plot(
            [left[0], right[0]], [left[1], right[1]],
            color="red" if missing else "cyan", lw=1.4 if missing else 0.6,
            alpha=0.9 if missing else 0.5,
        )
    axes[1].set_xlim(points[:, 0].min()-20, points[:, 0].max()+20)
    axes[1].set_ylim(points[:, 1].max()+20, points[:, 1].min()-20)
    axes[1].set_title("cyan=occupied; red=legacy candidate")
    axes[1].axis("off")
    figure.suptitle("UNVALIDATED legacy JSON-guided CT occupancy diagnostic")
    figure.tight_layout()
    figure_path = destination / "json_target_missing_struts.png"
    figure.savefig(figure_path, dpi=120, bbox_inches="tight")
    plt.close(figure)

    csv_path = destination / "json_target_strut_occupancy.csv"
    rows = (
        {
            "strut_id": int(result.strut_ids[index]),
            "junction0": int(result.junction0_ids[index]),
            "junction1": int(result.junction1_ids[index]),
            "midx": f"{result.midpoints_xyz[index, 0]:.2f}",
            "midy": f"{result.midpoints_xyz[index, 1]:.2f}",
            "midz": f"{result.midpoints_xyz[index, 2]:.2f}",
            "occupancy": f"{result.occupancy[index]:.4f}",
            "missing": int(result.candidate_missing[index]),
        }
        for index in range(len(result.occupancy))
    )
    write_csv(
        csv_path, rows,
        ("strut_id", "junction0", "junction1", "midx", "midy", "midz", "occupancy", "missing"),
    )
    return {"figure": figure_path, "csv": csv_path}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze lattice graph JSON assets.")
    parser.add_argument("--output-dir", default=str(OUT))
    parser.add_argument("--skip-wireframes", action="store_true")
    parser.add_argument("--skip-overlay", action="store_true")
    parser.add_argument(
        "--run-legacy-occupancy", action="store_true",
        help="run the unvalidated legacy occupancy diagnostic (not defect ground truth)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    destination = Path(args.output_dir).expanduser().resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    loaded: dict[str, LatticeGraph] = {}
    for name, path in GRAPH_FILES:
        if not path.is_file() or detect_lfs_pointer(path) is not None:
            print(f"[skip] {name}: missing or unmaterialized")
            continue
        graph = load_lattice_graph(path)
        loaded[name] = graph
        print_graph_summary(name, graph_summary(graph))
        if not args.skip_wireframes:
            save_wireframe(graph, name, destination / f"json_{name}_wireframe.png")
    if "octet_truss_9x9x9_design" in loaded and "octet_truss_9x9x9_registered" in loaded:
        result = registration_summary(loaded["octet_truss_9x9x9_design"], loaded["octet_truss_9x9x9_registered"])
        print("=" * 60, "registration: design -> CT voxel frame", "=" * 60, sep="\n")
        print(f"scale       : {result['scale_voxels_per_design_unit']:.4f} vox/design-unit")
        print(f"rotation    : {result['rotation_degrees']:.4f} degrees")
        print(f"translation : {np.round(result['translation_xyz_voxels'], 3)} voxels XYZ")
        print(f"mean/max residual: {result['mean_residual_voxels']:.6f}/{result['max_residual_voxels']:.6f} voxels")
        if not args.skip_overlay:
            save_registration_overlay(
                loaded["octet_truss_9x9x9_registered"], CT_TIF,
                destination / "json_registration_overlay.png",
            )
        print("node taxonomy:", node_taxonomy(loaded["octet_truss_9x9x9_registered"]))
        print("strut geometry:", strut_geometry(loaded["octet_truss_9x9x9_registered"]))
    if args.run_legacy_occupancy:
        registered = loaded.get("octet_truss_9x9x9_registered")
        if registered is None:
            raise SystemExit("registered graph is unavailable")
        artifacts = run_legacy_occupancy(registered, CT_TIF, destination)
        print("legacy artifacts:", ", ".join(str(path) for path in artifacts.values()))
    print(f"Outputs written to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
