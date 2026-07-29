# Adversarial audit — direct STL-to-TIFF strut comparison

Independent falsification attempt against the implementation tracked in
`STRUT_ERROR_DETECTION_PLAN.md`, run against the real assets in the `DSC`
environment. Reproduction scripts: `Aman_Scripts/audit/strut_detector/`.

## Headline

**The CT comparator is sound. The STL-to-graph rotation is wrong.**

`Components/strut_pipeline.py` fixes `REQUIRED_STL_ROTATION = "+z+x+y"` as a
module constant and never tests the other 23 proper cube rotations. The octet
lattice is invariant under the full cube group, so **all 24 rotations fit the
graph identically** and each one names a *different, disjoint* set of ~93 strut
IDs as "intentionally absent from `0.5.stl`".

The CT resolves the ambiguity unambiguously, and it does not choose `+z+x+y`.
The correct rotation is **`-x-z-y`**.

## What was confirmed, not refuted

These claims in the plan reproduce exactly and survive attack.

| Claim | Status |
| --- | --- |
| Registration scale `2.28 mm/design unit`, X/Z surface residuals `0.0288`/`0.0316 mm` | reproduced exactly |
| Design→CT fit: scale `39.4888` vox/unit, rotation `0.3351°`, RMS `<1e-6` vox | reproduced exactly |
| `3,498,656` specimen triangles, no decimation | reproduced exactly |
| CAD-omission cluster: `94` IDs, split `0.4667`, gap `0.7111` | reproduced exactly |
| Strut length `55.85` vox = `39.49 × √2` | correct octet geometry |

The corridor criterion is also **not** vacuous, contrary to my first hypothesis.
The specimen's interior foreground fraction at Otsu is 6.87%, so a radius-5.67
disk contains ~6.9 material voxels by chance against a `>= 9` requirement — close
enough to be worth testing. I tested it: **213 of 214 random non-strut corridors
placed inside the lattice were correctly flagged** (0 false "healthy"). Median
`realized_axial_fraction` for random geometry is 0.16 versus 1.0 for real struts.
Specificity is good.

## The falsification

### 1. The rotation is not identifiable by the method used

For each of the 24 proper cube rotations, recompute which graph IDs `0.5.stl`
omits (`audit/strut_detector/stage5_rotation_scan.py`):

| rotation | median coverage | struts covered ≥0.8 | omitted (cov <0.8) |
| --- | --- | --- | --- |
| all 24, identically | 1.000 | 18,375 / 18,468 | 93 |

Every rotation produces the same clean bimodal split. Pairwise overlap between
the omitted sets of different rotations is **0**. The "clean, unforced cluster"
in the completion log is therefore *zero evidence* for `+z+x+y` — it is an
artifact of lattice symmetry that every wrong answer also produces.

This is a concrete instance of the plan's own warning that a passing test count
is not evidence of scientific validity: 139 tests passed with the wrong constant.

### 2. The CT arbitrates, and rejects `+z+x+y`

The complete lattice is cube-symmetric, so all 24 placements superimpose it on
itself — but the *omitted* struts are not symmetric, so their locations differ
per rotation. Mean raw CT intensity in a radius-2 cylinder around each omitted
centerline (`stage6_arbiter.py`); baseline over 200 random struts is 39,553 with
p10 = 34,073:

| rotation | median core CT | fraction darker than baseline p10 |
| --- | --- | --- |
| **`-x-z-y`** | **32,181** | **0.91** |
| `+z+x+y` (pipeline) | 40,103 | 0.05 |
| other 22 | 38,591 – 41,795 | 0.02 – 0.15 |

One rotation stands far outside the rest. Under `-x-z-y` the omitted corridors
are genuinely empty; under `+z+x+y` they are indistinguishable from ordinary
present struts.

### 3. End-to-end confirmation with the pipeline's own comparator

Running `compare_strut_local` (pure CT side, `expected_present_override=True`,
`expected_radius_voxels=3.6718`) on each candidate omitted set:

| rotation | omitted | flagged error | called healthy | undecided | sensitivity |
| --- | --- | --- | --- | --- | --- |
| **`-x-z-y`** | 93 | **91** | 2 | 0 | **97.8%** |
| `+z+x+y` (pipeline) | 93 | 6 | 73 | 14 | 6.5% |

Both sets are scattered across the whole specimen (X 59–753, Y 52–762, Z 46–738),
so this is not a boundary or field-of-view artifact.

97.8% sensitivity on true removals plus 99.5% specificity on random corridors
means **the detector logic, thresholds, corridor radius, and gap rules are
working**. The single wrong constant is what breaks the result.

## Consequences for the current output

1. The 94 IDs marked `cad_intentionally_absent` / `comparison_applicable: false`
   are **healthy present struts**, silently excluded from inspection.
2. The ~93 genuinely missing struts — the actual answer for this dataset — are
   fed to the comparator as struts that *should* be present. A full run would
   flag most of them, but as manufacturing defects rather than CAD-intentional
   omissions, and the two populations are swapped.
3. `stl_tiff_strut_errors_smoke_500.json` carries one `intentionally_absent`
   record that is wrong, and its `_comparison.registration.stl_rotation` field
   records the wrong frame. The 425/34/40 split is otherwise unaffected, because
   the CT comparator does not depend on the rotation.
4. Phase A (skin observability) derives skin planes from the *design graph*, not
   the STL, so it is unaffected by this bug.

## Recommended fix

Do not hardcode the rotation. Select it, and record the evidence:

- Enumerate all 24 proper cube rotations.
- For each, compute the omitted-ID set from `0.stl` → `0.5.stl` coverage.
- Score each candidate set by median CT core intensity (or the existing
  comparator's flag rate) and require the winner to separate from the runner-up
  by a wide, recorded margin — here 32,181 versus 38,591, and 0.91 versus 0.15
  dark-fraction.
- Fail fast if no rotation separates, rather than defaulting to a constant.

Add a regression test asserting that the selected rotation reproduces
`-x-z-y` for this specimen and that ≥90% of its omitted set is flagged by the CT
comparator. Coverage-based tests alone cannot catch this — all 24 rotations pass
them.

## Reproduction

The audited modules (`Components/strut_pipeline.py`, `strut_comparison.py`,
`cad_strut_mapping.py`, `stl_surface_index.py`) are not yet committed to `main`,
so point `DSC_SCRIPTS_DIR` at the working checkout that has them:

```bash
export DSC_SCRIPTS_DIR=/path/to/repo/Aman_Scripts
cd Aman_Scripts/audit/strut_detector
conda run -n DSC python stage1_cad_map.py           # registration + 94-ID cluster
conda run -n DSC python stage4_random_corridors.py  # specificity floor
conda run -n DSC python stage5_rotation_scan.py     # 24-rotation degeneracy
conda run -n DSC python stage6_arbiter.py           # CT arbitration
conda run -n DSC python stage7_verify.py            # sensitivity both ways
```

Stages 2–7 depend on stage 1's cache, written to `_cache/` (gitignored).
Every number in this document was regenerated from these committed scripts. Peak RSS stayed under 2 GiB; the TIFF is
memory-mapped throughout and no file under `data/` or `Aman_Scripts/outputs/`
was modified.
