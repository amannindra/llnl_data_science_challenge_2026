# MeshLab TIFF vs STL metric viewer

Each percentage below was calculated from all downsampled voxels in the lattice-window region. The PLY files contain deterministic display samples, so MeshLab remains responsive without changing the metric. Within each colored metric partition, every layer uses the same stride, preserving the source-count proportions in the visible clouds.

For the exact comparison, the yellow layer is labelled Dice 44.83%, but yellow's share of the red+yellow+green union is IoU rather than Dice. The union-share is recorded in `metrics.json`; use the yellow layer label for the Dice value.

| Direct MeshLab file | What to view | Exact lattice-window metric |
| --- | --- | ---: |
| `01_exact_dice_44.83%.ply` | yellow exact overlap; red CT-only; green STL-only | Dice = 44.83% |
| `02_ct_within_design_73.47%.ply` | blue CT within tolerance of STL; red CT farther away | CT within STL +1 cell = 73.47% |
| `03_design_realized_60.36%.ply` | yellow STL supported by CT; green STL not supported | STL realized in CT +1 cell = 60.36% |

## How to inspect

1. Open one direct `.ply` file in MeshLab (File → Import Mesh); these are the recommended viewer artifacts.
2. The PLY header comments retain the exact metric and source counts; `metrics.json` is the complete machine-readable record.
3. Set Render → Point Size higher if individual points are hard to see.
4. Interpret red/green as a discrepancy to investigate, not automatically as a defect: segmentation, thickness variation, tolerance, and cropped plates all contribute.

## Display-layer provenance

| PLY layer | Exact source voxels | Display points | Sampling stride |
| --- | ---: | ---: | ---: |
| `exact_overlap_yellow.ply` | 3,019,402 | 107,836 | 28 |
| `exact_ct_only_red.ply` | 1,959,821 | 69,994 | 28 |
| `exact_stl_only_green.ply` | 5,470,740 | 195,384 | 28 |
| `ct_near_design_blue.ply` | 3,658,175 | 192,536 | 19 |
| `ct_far_design_red.ply` | 1,321,048 | 69,529 | 19 |
| `ct_reference_gray.ply` | 4,979,223 | 199,169 | 25 |
| `design_realized_yellow.ply` | 5,124,753 | 197,106 | 26 |
| `design_unrealized_green.ply` | 3,365,389 | 129,439 | 26 |
| `stl_reference_green.ply` | 8,490,142 | 197,446 | 43 |

## Direct-view PLYs

| File | Display points |
| --- | ---: |
| `01_exact_dice_44.83%.ply` | 373,214 |
| `02_ct_within_design_73.47%.ply` | 262,065 |
| `03_design_realized_60.36%.ply` | 326,545 |

Optional MeshLab projects: `01_exact_dice.mlp`, `02_ct_within_design.mlp`, `03_design_realized.mlp`
