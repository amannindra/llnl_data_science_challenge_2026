"""
Analyze the lattice graph JSON files (junctions / struts / unit_cells).
Reports node/edge counts, bounding box, degree distribution, strut length &
thickness stats, and renders a 3D wireframe of the graph.

Also analyzes the *registered* JSON in data/missing_struts/registered_jsons/.
That file is the ideal design graph after it has been aligned into the CT
scan's voxel coordinate frame (a rigid-body + uniform-scale "similarity"
transform).  The registration section recovers that transform (scale, rotation,
translation, fit residual) by matching junction-for-junction against the design
graph, and overlays the graph onto a real CT slice from the tif to prove the
alignment is correct.  This registered graph is what lets you walk each expected
strut through the CT voxels and decide present vs missing/disconnected.

Outputs go to Scripts/outputs/.
"""
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

# Design graph frames (abstract lattice units) ...
DESIGN_9x9x9 = os.path.join(ROOT, "data", "missing_struts", "octet_truss_9x9x9.json")
# ... and the same graph registered into CT voxel space.
REGISTERED = os.path.join(ROOT, "data", "missing_struts", "registered_jsons",
                          "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json")
# The CT volume the registered graph is aligned to (for the overlay proof).
CT_TIF = os.path.join(ROOT, "data", "9x9x9_octet_lattice", "9x9x9_octet_lattice.tif")

FILES = [
    ("polyhedron_1x1x1", os.path.join(ROOT, "data", "unitcell", "polyhedron_1x1x1.json")),
    ("octet_truss_8x8x8", os.path.join(ROOT, "data", "octet_truss_8x8x8", "octet_truss_8x8x8.json")),
    ("octet_truss_9x9x9_design", DESIGN_9x9x9),
    ("octet_truss_9x9x9_registered", REGISTERED),
]

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
    plt.savefig(os.path.join(OUT, f"json_{name}_wireframe.png"), dpi=120)
    plt.close()
    print()


# ---------------------------------------------------------------------------
# Registration analysis: what does the "registered" JSON actually encode?
# ---------------------------------------------------------------------------
def _positions(path):
    with open(path) as f:
        g = json.load(f)
    return g, np.array([j["position"] for j in g["junctions"]], float)


def _umeyama(src, dst):
    """Best similarity transform dst ~= s*Rot@src + t (Umeyama 1991)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    Sc, Dc = src - mu_s, dst - mu_d
    C = Dc.T @ Sc / len(src)
    U, S, Vt = np.linalg.svd(C)
    d = np.sign(np.linalg.det(U @ Vt))
    Rot = U @ np.diag([1, 1, d]) @ Vt
    s = (S * [1, 1, d]).sum() / ((Sc ** 2).sum() / len(src))
    t = mu_d - s * Rot @ mu_s
    return s, Rot, t


def analyze_registration(design_path, registered_path, ct_tif, voxel_um=58.1):
    print("=" * 60)
    print("registration: design 9x9x9  ->  CT voxel frame")
    print("=" * 60)
    for p in (design_path, registered_path):
        if not os.path.exists(p) or os.path.getsize(p) < 500:
            print(f"[skip] missing/pointer: {p}")
            return

    gd, D = _positions(design_path)
    gr, R = _positions(registered_path)

    # 1) Topology is identical -- registration only moves the *positions*.
    same_ids = [j["id"] for j in gd["junctions"]] == [j["id"] for j in gr["junctions"]]
    same_conn = all((sd["junction0"], sd["junction1"]) == (sr["junction0"], sr["junction1"])
                    for sd, sr in zip(gd["struts"], gr["struts"]))
    print(f"same junction ids : {same_ids}")
    print(f"same connectivity : {same_conn}  ({len(gr['struts'])} struts)")
    print(f"design bbox (units): {np.round(D.min(0),2)} -> {np.round(D.max(0),2)}")
    print(f"reg.   bbox (voxels): {np.round(R.min(0),2)} -> {np.round(R.max(0),2)}")

    # 2) Recover the similarity transform design -> registered.
    s, Rot, t = _umeyama(D, R)
    pred = (s * (Rot @ D.T)).T + t
    rms = np.sqrt(((pred - R) ** 2).sum(1)).mean()
    ang = np.degrees(np.arccos(np.clip((np.trace(Rot) - 1) / 2, -1, 1)))
    print(f"scale             : {s:.4f} voxels / design-unit")
    print(f"rotation          : {ang:.3f} deg")
    print(f"translation       : {np.round(t,2)} voxels")
    print(f"fit RMS residual  : {rms:.5f} voxels over {len(D)} junctions "
          f"({'PURE similarity transform' if rms < 1e-2 else 'has deviations'})")
    # 1 unit cell spans 2 design-units in this graph.
    cell_vox = 2 * s
    print(f"=> 1 unit cell = {cell_vox:.1f} voxels = {cell_vox * voxel_um / 1000:.2f} mm "
          f"(paper nominal 4.56 mm)")

    # 3) Prove it: overlay the registered graph on a real CT slice.
    if not os.path.exists(ct_tif) or os.path.getsize(ct_tif) < 1_000_000:
        print("[overlay skipped] CT tif not available (pull it with `git lfs pull`)")
        return
    try:
        import tifffile
    except ImportError:
        print("[overlay skipped] tifffile not installed")
        return

    vol = tifffile.memmap(ct_tif)                 # (nz, ny, nx), lazy
    # JSON position is [x, y, z]; array is indexed [z, y, x].
    z0 = int(np.median(R[:, 2]))
    hw = 5
    slab = vol[max(0, z0 - hw): z0 + hw + 1].astype(np.float32).max(0)   # MIP slab
    lo, hi = np.percentile(slab, [2, 99.5])
    slab = np.clip((slab - lo) / (hi - lo + 1e-9), 0, 1)

    near = np.abs(R[:, 2] - z0) <= hw
    _, ax = plt.subplots(1, 2, figsize=(16, 8))
    for a, show_graph in zip(ax, (False, True)):
        a.imshow(slab, cmap="gray", origin="upper")
        if show_graph:
            # struts whose midpoint sits in this slab
            for st in gr["struts"]:
                p, q = R[st["junction0"]], R[st["junction1"]]
                if abs((p[2] + q[2]) / 2 - z0) <= hw:
                    a.plot([p[0], q[0]], [p[1], q[1]], color="cyan", lw=0.8, alpha=0.7)
            a.scatter(R[near, 0], R[near, 1], s=18, facecolors="none",
                      edgecolors="red", linewidths=1.1)
            a.set_title(f"registered graph overlaid  (junctions near z={z0})")
        else:
            a.set_title(f"raw CT slab MIP  (z={z0}±{hw})")
        a.set_xlim(R[:, 0].min() - 20, R[:, 0].max() + 20)
        a.set_ylim(R[:, 1].max() + 20, R[:, 1].min() - 20)
        a.axis("off")
    plt.suptitle("Registration check: design junctions land on real CT struts", fontsize=14)
    plt.tight_layout()
    overlay = os.path.join(OUT, "json_registration_overlay.png")
    plt.savefig(overlay, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"overlay written   : {overlay}")
    print(f"  ({near.sum()} junctions within z={z0}+/-{hw})")


analyze_registration(DESIGN_9x9x9, REGISTERED, CT_TIF)
print()
print(f"Outputs written to {OUT}")
