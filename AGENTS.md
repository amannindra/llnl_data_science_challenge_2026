# LLNL Data Science Challenge 2026 — project context

Agentic AI for materials science: an AI-assisted workflow over X-ray CT scans of
additively manufactured strut lattices (segmentation → skeletonization → defect
inspection → NDE report). See `README.md` and `DATA_SCIENCE_CHALLENGE_2026.pdf`.

## Environment

Run all Python via the prepared conda env:

```bash
conda run -n DSC python <script>
```

Deps are pinned in `Aman_Scripts/requirements.txt`. Full regression suite:

```bash
conda run -n DSC python Aman_Scripts/ComponentTests/run_all.py
```

## Layout

| Path | Purpose |
| --- | --- |
| `Aman_Scripts/Components/` | Reusable, side-effect-free implementation (see its `README.md`) |
| `Aman_Scripts/ComponentTests/` | Adversarial checks; ≥10 per public component |
| `Aman_Scripts/tif2stl/` | CT-TIFF-vs-STL validation pipeline (see its `README.md`) |
| `Aman_Scripts/outputs/` | Generated artifacts |
| `Aman_Scripts/Task1..3/` | Challenge task harnesses |
| `Aman_src/` | Starter MCP server (out of scope for refactors) |
| `paraview_mcp/` | ParaView MCP server |
| `data/` | Git-LFS CT volumes, TIFF stacks, STL, lattice JSON |
| `.Codex/agents/` | Codex subagents |
| `.Codex/skills/` | Codex skills |
| `.agents/skills/` | Codex skills (kept for parity) |

`bioimage-agent/` is an unrelated vendored LLNL project — leave it alone unless
asked directly.

## Conventions that bite

- **Coordinates**: NumPy/TIFF volumes are `[z, y, x]`; JSON junctions, STL/PLY
  vertices, and transforms are `(x, y, z)`. Convert via `Components/coordinates.py`.
- **Intensity**: `data/unitcell/unitcell.npy` holds raw recon values ≈`[-0.003,
  0.015]`, not `[0,1]`. Threshold 0.5 segments nothing; Otsu ≈ `0.00581`.
- **Scale**: voxel pitch 58.1 µm; paper strut diameter 424 µm (r ≈ 3.65 vox);
  challenge nominal 350 µm (r ≈ 3.01 vox).
- **Missing-strut dataset**: raw TIFF `(761, 815, 837)` ZYX uint16; corrected
  segmented TIFF same shape, uint8 `{0,255}`; registered JSON has 10,206 junction
  records → 3,430 welded nodes → 18,468 expected struts.
- Segmented TIFFs are supporting evidence, **not** ground truth. Do not tune
  thresholds to reproduce published defect rates.
- `matplotlib.imsave` cannot write `.tif` — save via Pillow by filename.
- Importing any module under `Aman_Scripts/` must not write files, create directories,
  or launch a UI. Large TIFFs open lazily or memory-mapped.
- Write artifacts through `Components/reporting.py` (atomic, deterministic, SHA-256).

## Deferred work

The TIFF strut-defect detector is deferred — see
`Aman_Scripts/TIFF_DEFECT_DETECTION_DEFERRED_PLAN.md`. `Components/legacy_occupancy.py`
is a preserved historical heuristic (flags 3,875/18,468 struts, 20.98%); it is
unvalidated and must never be reported as a defect detector.

## Subagents and skills

- `nde-lattice-analyst` (`.Codex/agents/`) — CT lattice analysis, segmentation,
  strut inspection, mesh export, NDE reporting.
- `tif2stl-validator` (`.Codex/agents/`) — validates the CT TIFF against the STL
  design mesh via `Aman_Scripts/tif2stl/` (registration, voxelization, overlap gates).
- `nde-report` skill (`.Codex/skills/`) — the NDE report generation protocol.
