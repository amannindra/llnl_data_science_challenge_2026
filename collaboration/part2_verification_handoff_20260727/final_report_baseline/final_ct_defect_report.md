# Final CT Defect Report Package

## Status

```text
SPOTCHECK_SUPPORTED_AUTOMATED_ESTIMATE_NOT_FULL_GROUND_TRUTH
```

This package is the current best automatic result, with a small human
spot-check. It is not claiming that every one of the
`18468` struts was manually labeled by a human.

## One-Sentence Result

Using the human-anchored design-intent map and the registered CT strut atlas,
the strict automated review found `214`
possible unintended missing or disconnected strut candidates out of
`18468` expected struts. That is `1.16%`.

## What Data Was Used

- STL/design files tell what the printer was supposed to intentionally remove.
- The registered JSON tells where each expected strut should lie inside the CT scan.
- The TIFF/CT stack tells what material actually appears bright or dark in the scan.
- Phase 2B.4 combines those earlier outputs into automated review labels.
- The user's top-40 spot-check labels test whether the strongest automated calls look physically reasonable.

## Main Numbers

```text
total expected struts = 18468
auto-supported possible unintended missing = 202
auto-supported possible unintended disconnected = 12
auto-supported possible unintended combined = 214
draft possible-unintended fraction = 214 / 18468 = 1.16%
auto-supported designed-removed absent/disconnected = 89
auto-supported present-like = 14820
blocked manual-review rows = 920
low-priority uncertain not counted as defects = 2425
```

## Human Spot-Check

The user reviewed the first `40` top-ranked
Phase 2B.4 spot-check panels.

```text
defect-like labels = 36 / 40
ambiguous labels = 4 / 40
present-like contradictions = 0 / 40
defect-like support fraction = 0.900
```

Simple meaning: the first reviewed cases mostly looked missing or broken, and
none looked clearly present. That supports the automated direction, but it does
not replace full manual review of all candidates.

## Physics Meaning In Simple Words

Think of the lattice as a building made from many tiny bars. The registered
JSON is the map saying where every bar should be in the CT image. The TIFF is
the X-ray scan. Bright voxels usually mean solid titanium alloy is present;
dark voxels usually mean air or missing material.

The automatic system checks each expected bar. If the center of that bar is
mostly dark, has a long dark gap, and the result stays stable when thresholds
or registration are perturbed, the system marks it as possible missing or
disconnected. If the design STL says that bar was intentionally removed, it is
kept in the designed-removal category. If the design says it should be present
but CT evidence looks absent or broken, it becomes a possible unintended defect.

## Suggested Report Wording

```text
Using the human-anchored design-intent map and registered CT strut atlas, the
strict automated review identified 214 possible unintended missing or
disconnected strut candidates among 18468 expected struts. A human spot-check
of the top 40 auto-supported candidates found 36 defect-like cases, 4 ambiguous
cases, and 0 clearly present-like contradictions. The resulting automated
possible-unintended-defect fraction is 214/18468 = 1.16%, reported as a
spot-check-supported estimate rather than a fully human-labeled ground truth.
```

## Caveats

- Do not call this a fully human-labeled ground truth.
- Do not count the `920` blocked manual-review rows as defects.
- Do not merge intentionally designed removals with possible unintended defects.
- Boundary and skin-adjacent struts are physically important but harder to judge.
- CT page number is not the same thing as LPBF print layer number.

## Files In This Package

```text
final_ct_defect_report.md
final_ct_defect_summary.json
agentic_workflow.md
tables/
figures/
run_manifest.json
```
