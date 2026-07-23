"""
Analyze the unitcell.npy volume (octet_truss_unit_cell_no_defects_0256_xray_recon).
Reports shape/dtype/value stats, a density histogram, orthogonal slices, and a 3D isosurface.
Outputs go to Scripts/outputs/.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

npy_path = os.path.join(ROOT, "data", "unitcell", "unitcell.npy")
vol = np.load(npy_path)

print("=" * 60)
print("unitcell.npy")
print("=" * 60)
print(f"shape      : {vol.shape}")
print(f"dtype      : {vol.dtype}")
print(f"min/max    : {vol.min():.4f} / {vol.max():.4f}")
print(f"mean/std   : {vol.mean():.4f} / {vol.std():.4f}")
print(f"nbytes     : {vol.nbytes/1e6:.1f} MB")
# Value distribution
pcts = np.percentile(vol, [1, 5, 25, 50, 75, 95, 99])
print(f"percentiles 1/5/25/50/75/95/99: {np.round(pcts,4)}")

# Foreground fractions on the same normalized [0, 1] scale used below for
# marching cubes.  The source CT values are reconstruction intensities (their
# maximum is about 0.015), so using raw thresholds of 0.3--0.7 would always
# return an invalid, empty foreground.
vmin, vmax = float(vol.min()), float(vol.max())
norm = (vol - vmin) / (vmax - vmin) if vmax > vmin else np.zeros_like(vol)
print("foreground fraction by normalized threshold (raw-equivalent shown):")
for t in (0.3, 0.4, 0.5, 0.6, 0.7):
    raw_threshold = vmin + t * (vmax - vmin)
    frac = (norm >= t).mean()
    print(f"  normalized={t:.1f}; raw={raw_threshold:.6f}; fraction={frac:.4f}")

# Histogram
plt.figure(figsize=(7, 4))
plt.hist(vol.ravel(), bins=100, color="steelblue")
plt.yscale("log")
plt.title("unitcell.npy density histogram (log y)")
plt.xlabel("density"); plt.ylabel("voxel count")
plt.tight_layout()
plt.savefig(os.path.join(OUT, "npy_histogram.png"), dpi=120)
plt.close()

# Orthogonal center slices
mid = [s // 2 for s in vol.shape]
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
for ax, axis, m in zip(axes, range(3), mid):
    sl = np.take(vol, m, axis=axis)
    ax.imshow(sl, cmap="gray")
    ax.set_title(f"axis {axis}, slice {m}")
    ax.axis("off")
plt.tight_layout()
plt.savefig(os.path.join(OUT, "npy_center_slices.png"), dpi=120)
plt.close()

# 3D isosurface via marching cubes (downsampled)
try:
    from skimage import measure
    ds = vol[::2, ::2, ::2].astype(np.float32)
    dmin, dmax = ds.min(), ds.max()
    if dmax > dmin:
        ds = (ds - dmin) / (dmax - dmin)
    verts, faces, _, _ = measure.marching_cubes(ds, level=0.5)
    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_trisurf(verts[:, 0], verts[:, 1], faces, verts[:, 2],
                    cmap="viridis", lw=0.1, edgecolor="none")
    ax.view_init(elev=30, azim=45)
    ax.set_axis_off()
    ax.set_title("unitcell 3D isosurface (thr=0.5)")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, "npy_isosurface.png"), dpi=120)
    plt.close()
    print(f"isosurface : {len(verts)} verts, {len(faces)} faces")
except Exception as e:
    print(f"isosurface failed: {e}")

print(f"\nOutputs written to {OUT}")
