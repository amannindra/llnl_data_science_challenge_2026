"""Analyze lattice-graph JSON files and explain registered CT graphs.

For each input, report the junction/strut/unit-cell schema, geometry, topology,
and integrity, then render a 3-D wireframe.  When ``--design`` is supplied,
also compare the input with the unregistered design graph and recover the
similarity transform that maps design coordinates into CT voxel coordinates.
An optional ``--ct`` argument writes a graph-on-CT registration overlay.

Examples
--------
python Scripts2/analyze_json.py path/to/registered.json \
    --design data/missing_struts/octet_truss_9x9x9.json \
    --ct path/to/corresponding.tif

With no input paths, the two small example graphs used by the original script
are analyzed. Outputs go to ``Scripts2/outputs/``.
"""
import argparse
import os
import json
import numpy as np
from collections import Counter

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

DEFAULT_FILES = [
    ("polyhedron_1x1x1", os.path.join(ROOT, "data", "unitcell", "polyhedron_1x1x1.json")),
    ("octet_truss_8x8x8", os.path.join(ROOT, "data", "octet_truss_8x8x8", "octet_truss_8x8x8.json")),
]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("paths", nargs="*", help="lattice JSON file(s) to analyze")
parser.add_argument(
    "--design",
    help="unregistered design JSON to compare with a single registered input",
)
parser.add_argument(
    "--ct",
    help="CT TIFF corresponding to the registered JSON; requires --design",
)
parser.add_argument(
    "--voxel-um",
    type=float,
    default=58.1,
    help="CT voxel pitch in micrometres (default: 58.1)",
)
parser.add_argument(
    "--no-render",
    action="store_true",
    help="skip 3-D wireframe rendering",
)
args = parser.parse_args()

if args.paths:
    FILES = [
        (os.path.splitext(os.path.basename(path))[0], os.path.abspath(path))
        for path in args.paths
    ]
else:
    FILES = DEFAULT_FILES

if args.design and len(FILES) != 1:
    parser.error("--design requires exactly one input JSON")
if args.ct and not args.design:
    parser.error("--ct requires --design")

for name, path in FILES:
    if not os.path.exists(path):
        print(f"[skip] {name}: not found")
        continue
    # Skip Git LFS pointer stubs
    if os.path.getsize(path) < 500:
        with open(path) as f:
            head = f.read(50)
        if head.startswith("version https://git-lfs"):
            print(f"[skip] {name}: Git LFS pointer (not pulled)")
            continue
    with open(path) as f:
        g = json.load(f)

    junctions = g.get("junctions", [])
    struts = g.get("struts", [])
    unit_cells = g.get("unit_cells", [])
    pos = {j["id"]: np.array(j["position"], float) for j in junctions}
    P = np.array([j["position"] for j in junctions], float)

    print("=" * 60)
    print(name)
    print("=" * 60)
    print(f"junctions  : {len(junctions)}")
    print(f"struts     : {len(struts)}")
    print(f"unit_cells : {len(unit_cells)}")
    print(f"bbox min   : {np.round(P.min(0), 3)}")
    print(f"bbox max   : {np.round(P.max(0), 3)}")
    print(f"bbox size  : {np.round(P.max(0) - P.min(0), 3)}")

    # Degree distribution
    deg = Counter()
    lengths, thick = [], []
    adjacency = {j["id"]: set() for j in junctions}
    invalid_references = []
    for s in struts:
        a, b = s["junction0"], s["junction1"]
        deg[a] += 1; deg[b] += 1
        if a in pos and b in pos:
            lengths.append(float(np.linalg.norm(pos[a] - pos[b])))
            adjacency[a].add(b)
            adjacency[b].add(a)
        else:
            invalid_references.append(s["id"])
        thick.append(s.get("thickness", np.nan))
    degvals = [deg.get(j["id"], 0) for j in junctions]
    print(f"degree     : min {min(degvals)}, max {max(degvals)}, "
          f"mean {np.mean(degvals):.2f}, dist {dict(sorted(Counter(degvals).items()))}")
    if lengths:
        L = np.array(lengths)
        print(f"strut len  : min {L.min():.3f}, max {L.max():.3f}, "
              f"mean {L.mean():.3f}, unique~ {len(np.unique(np.round(L,3)))}")
    tt = np.array(thick, float)
    print(f"thickness  : min {np.nanmin(tt):.3f}, max {np.nanmax(tt):.3f}, "
          f"unique {sorted(set(np.round(tt[~np.isnan(tt)],4)))[:8]}")

    # Topological integrity: reported components exclude intentionally unused
    # junction records, which occur at cube corners in this graph format.
    active = {node for node, neighbors in adjacency.items() if neighbors}
    seen, component_sizes = set(), []
    for start in active:
        if start in seen:
            continue
        stack, size = [start], 0
        seen.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for neighbor in adjacency[node]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        component_sizes.append(size)
    print(f"active graph: {len(active)} junctions; {len(component_sizes)} component(s); "
          f"largest={max(component_sizes, default=0)}")
    print(f"references : invalid strut endpoints={len(invalid_references)}; "
          f"unique positions={len({tuple(point) for point in P})}")

    # The repeated-lattice JSON may retain a local node ID for each unit cell.
    # Recompute connectivity after welding records that have identical positions;
    # this distinguishes file representation from physical lattice topology.
    coordinate_to_id = {
        tuple(np.round(point, 9)): index for index, point in enumerate(P)
    }
    welded_adjacency = {index: set() for index in coordinate_to_id.values()}
    for strut in struts:
        a, b = strut["junction0"], strut["junction1"]
        if a not in pos or b not in pos:
            continue
        left = coordinate_to_id[tuple(np.round(pos[a], 9))]
        right = coordinate_to_id[tuple(np.round(pos[b], 9))]
        if left != right:
            welded_adjacency[left].add(right)
            welded_adjacency[right].add(left)
    welded_active = {node for node, neighbors in welded_adjacency.items() if neighbors}
    welded_seen, welded_sizes = set(), []
    for start in welded_active:
        if start in welded_seen:
            continue
        stack, size = [start], 0
        welded_seen.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for neighbor in welded_adjacency[node]:
                if neighbor not in welded_seen:
                    welded_seen.add(neighbor)
                    stack.append(neighbor)
        welded_sizes.append(size)
    welded_degrees = [len(neighbors) for neighbors in welded_adjacency.values()]
    print(f"welded graph: {len(welded_active)} active unique positions; "
          f"{len(welded_sizes)} component(s); largest={max(welded_sizes, default=0)}; "
          f"degree dist={dict(sorted(Counter(welded_degrees).items()))}")

    if unit_cells:
        cell_strut_counts = np.array([len(cell.get("struts", [])) for cell in unit_cells])
        cell_indices = np.array([cell.get("indices", [np.nan] * 3) for cell in unit_cells], float)
        print(f"cell struts : min {cell_strut_counts.min()}, max {cell_strut_counts.max()}, "
              f"mean {cell_strut_counts.mean():.2f}")
        print(f"cell index bbox: {np.round(cell_indices.min(0), 3)} to "
              f"{np.round(cell_indices.max(0), 3)}")
    edge_kind_counts = Counter(s.get("unit_cell_edge_idx", "not_recorded") for s in struts)
    print(f"edge kinds : {dict(sorted(edge_kind_counts.items(), key=lambda pair: str(pair[0])))}")

    # 3D wireframe render
    if not args.no_render and plt is not None:
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="3d")
        for s in struts:
            a, b = s["junction0"], s["junction1"]
            if a in pos and b in pos:
                xs = [pos[a][0], pos[b][0]]
                ys = [pos[a][1], pos[b][1]]
                zs = [pos[a][2], pos[b][2]]
                ax.plot(xs, ys, zs, color="tab:blue", lw=0.6, alpha=0.7)
        ax.scatter(P[:, 0], P[:, 1], P[:, 2], color="red", s=6)
        ax.set_title(f"{name}: {len(junctions)} nodes / {len(struts)} struts")
        ax.view_init(elev=25, azim=45)
        plt.tight_layout()
        output = os.path.join(OUT, f"json_{name}_wireframe.png")
        plt.savefig(output, dpi=120)
        plt.close()
        print(f"wireframe  : {output}")
    elif not args.no_render:
        print("[wireframe skipped] matplotlib is not installed")
    print()


def _load_graph(path):
    """Load a real JSON object, rejecting missing files and Git LFS pointers."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.getsize(path) < 500:
        with open(path) as file:
            head = file.read(50)
        if head.startswith("version https://git-lfs"):
            raise ValueError(f"Git LFS pointer, not JSON data: {path}")
    with open(path) as file:
        return json.load(file)


def _umeyama(source, destination):
    """Return the least-squares similarity transform destination ~= s*R*x+t."""
    source_mean = source.mean(axis=0)
    destination_mean = destination.mean(axis=0)
    source_centered = source - source_mean
    destination_centered = destination - destination_mean
    covariance = destination_centered.T @ source_centered / len(source)
    left, singular_values, right_t = np.linalg.svd(covariance)
    reflection_fix = np.ones(3)
    reflection_fix[-1] = np.sign(np.linalg.det(left @ right_t))
    rotation = left @ np.diag(reflection_fix) @ right_t
    source_variance = np.mean(np.sum(source_centered ** 2, axis=1))
    scale = np.dot(singular_values, reflection_fix) / source_variance
    translation = destination_mean - scale * rotation @ source_mean
    return scale, rotation, translation


def analyze_registration(design_path, registered_path, ct_path=None, voxel_um=58.1):
    """Explain exactly what changed between a design and registered graph."""
    design = _load_graph(design_path)
    registered = _load_graph(registered_path)

    design_by_id = {item["id"]: item for item in design.get("junctions", [])}
    registered_by_id = {item["id"]: item for item in registered.get("junctions", [])}
    same_junction_ids = design_by_id.keys() == registered_by_id.keys()
    if not same_junction_ids:
        raise ValueError("design and registered JSONs do not have the same junction IDs")

    ids = sorted(design_by_id)
    design_positions = np.array([design_by_id[node]["position"] for node in ids], float)
    registered_positions = np.array(
        [registered_by_id[node]["position"] for node in ids], float
    )
    design_junction_metadata = [
        {key: value for key, value in design_by_id[node].items() if key != "position"}
        for node in ids
    ]
    registered_junction_metadata = [
        {key: value for key, value in registered_by_id[node].items() if key != "position"}
        for node in ids
    ]
    same_junction_metadata = design_junction_metadata == registered_junction_metadata
    same_struts = design.get("struts", []) == registered.get("struts", [])
    same_unit_cells = design.get("unit_cells", []) == registered.get("unit_cells", [])

    scale, rotation, translation = _umeyama(design_positions, registered_positions)
    predicted = (scale * (rotation @ design_positions.T)).T + translation
    errors = np.linalg.norm(predicted - registered_positions, axis=1)
    rms_error = np.sqrt(np.mean(errors ** 2))
    angle = np.degrees(
        np.arccos(np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0))
    )

    print("=" * 60)
    print("REGISTERED-GRAPH EXPLANATION")
    print("=" * 60)
    print(f"design JSON       : {os.path.abspath(design_path)}")
    print(f"registered JSON   : {os.path.abspath(registered_path)}")
    print(f"same junction IDs : {same_junction_ids}")
    print(f"same node metadata: {same_junction_metadata}  (everything except position)")
    print(f"same strut records: {same_struts}")
    print(f"same unit cells   : {same_unit_cells}")
    print(f"design bbox       : {np.round(design_positions.min(0), 4)} -> "
          f"{np.round(design_positions.max(0), 4)} design units")
    print(f"registered bbox   : {np.round(registered_positions.min(0), 4)} -> "
          f"{np.round(registered_positions.max(0), 4)} CT voxels [x,y,z]")
    print(f"scale             : {scale:.9f} voxels/design-unit")
    print(f"rotation angle    : {angle:.9f} degrees")
    print("rotation matrix   :")
    for row in rotation:
        print(f"                     {np.array2string(row, precision=9)}")
    print(f"translation       : {np.round(translation, 9)} voxels")
    print(f"transform RMS     : {rms_error:.12g} voxels")
    print(f"transform max err : {errors.max():.12g} voxels")
    cell_voxels = 2.0 * scale  # cell indices advance by two design-coordinate units
    print(f"unit-cell pitch   : {cell_voxels:.6f} voxels; "
          f"{cell_voxels * voxel_um / 1000.0:.6f} mm at {voxel_um:g} um/voxel")

    topology_unchanged = same_junction_metadata and same_struts and same_unit_cells
    if topology_unchanged and rms_error < 1e-8:
        print("conclusion        : only junction positions changed, via one similarity transform")
        print("defect labels     : none; this is the expected design graph, not measured strut state")
    else:
        print("conclusion        : registration includes changes beyond one exact similarity transform")

    if not ct_path:
        return

    if plt is None:
        print("[overlay skipped] matplotlib is not installed")
        return

    try:
        import tifffile
    except ImportError:
        tifffile = None
        try:
            from PIL import Image
        except ImportError:
            print("[overlay skipped] install tifffile or Pillow to read the CT")
            return

    if not os.path.exists(ct_path) or os.path.getsize(ct_path) < 1_000_000:
        print(f"[overlay skipped] CT is missing or still a Git LFS pointer: {ct_path}")
        return

    # Read only an 11-slice slab; the complete CT is about 1 GB.
    z_center = int(np.median(registered_positions[:, 2]))
    half_width = 5
    if tifffile is not None:
        with tifffile.TiffFile(ct_path) as tif:
            volume_shape = (len(tif.pages),) + tuple(tif.pages[0].shape)
            z_indices = range(
                max(0, z_center - half_width),
                min(len(tif.pages), z_center + half_width + 1),
            )
            slab = np.maximum.reduce(
                [tif.pages[index].asarray().astype(np.float32) for index in z_indices]
            )
    else:
        # Pillow is slower than tifffile but is a useful dependency-free fallback.
        with Image.open(ct_path) as tif:
            volume_shape = (tif.n_frames, tif.height, tif.width)
            z_indices = range(
                max(0, z_center - half_width),
                min(tif.n_frames, z_center + half_width + 1),
            )
            frames = []
            for index in z_indices:
                tif.seek(index)
                frames.append(np.asarray(tif).astype(np.float32))
            slab = np.maximum.reduce(frames)

    lower, upper = np.percentile(slab, [2, 99.5])
    slab = np.clip((slab - lower) / (upper - lower + 1e-9), 0, 1)
    within_volume = (
        (registered_positions[:, 0] >= 0)
        & (registered_positions[:, 0] < volume_shape[2])
        & (registered_positions[:, 1] >= 0)
        & (registered_positions[:, 1] < volume_shape[1])
        & (registered_positions[:, 2] >= 0)
        & (registered_positions[:, 2] < volume_shape[0])
    )
    print(f"CT shape          : {volume_shape} array order [z,y,x]")
    print(f"junctions in CT   : {within_volume.sum()}/{len(within_volume)}")

    registered_position_by_id = {
        node: registered_positions[index] for index, node in enumerate(ids)
    }
    near = np.abs(registered_positions[:, 2] - z_center) <= half_width
    figure, axes = plt.subplots(1, 2, figsize=(16, 8))
    for axis, show_graph in zip(axes, (False, True)):
        axis.imshow(slab, cmap="gray", origin="upper")
        if show_graph:
            for strut in registered.get("struts", []):
                point = registered_position_by_id[strut["junction0"]]
                other = registered_position_by_id[strut["junction1"]]
                midpoint_z = (point[2] + other[2]) / 2.0
                if abs(midpoint_z - z_center) <= half_width:
                    axis.plot(
                        [point[0], other[0]],
                        [point[1], other[1]],
                        color="cyan",
                        linewidth=0.8,
                        alpha=0.7,
                    )
            axis.scatter(
                registered_positions[near, 0],
                registered_positions[near, 1],
                s=18,
                facecolors="none",
                edgecolors="red",
                linewidths=1.1,
            )
            axis.set_title(f"registered expected graph (z={z_center} +/- {half_width})")
        else:
            axis.set_title(f"raw CT slab maximum projection (z={z_center} +/- {half_width})")
        axis.set_xlim(registered_positions[:, 0].min() - 20,
                      registered_positions[:, 0].max() + 20)
        axis.set_ylim(registered_positions[:, 1].max() + 20,
                      registered_positions[:, 1].min() - 20)
        axis.axis("off")
    figure.suptitle("Registered ideal graph overlaid on the corresponding CT")
    figure.tight_layout()
    overlay_path = os.path.join(OUT, "json_registration_overlay.png")
    figure.savefig(overlay_path, dpi=120, bbox_inches="tight")
    plt.close(figure)
    print(f"CT overlay        : {overlay_path}")


if args.design:
    analyze_registration(
        os.path.abspath(args.design),
        FILES[0][1],
        os.path.abspath(args.ct) if args.ct else None,
        voxel_um=args.voxel_um,
    )
    print()

print(f"Outputs written to {OUT}")
