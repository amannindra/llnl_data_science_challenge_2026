# End-to-end: the Part 2 CT defect-analysis handoff

A complete read of `collaboration/part2_verification_handoff_20260727/` — what it
is, how the pipeline behind it works, how to use it, what it is good for, and
where it is wrong or fragile. Written from a full file-by-file pass plus
independent re-derivation of its key numbers against this repository's own
`Aman_Scripts/tif2stl` pipeline.

---

## 1. The one-paragraph version

A collaborator built an agentic pipeline that hunts for **unintended
manufacturing defects** — missing and disconnected struts — in an X-ray CT scan
of a 3D-printed octet-truss lattice. The specimen is the "0.5% #1" coupon, where
roughly 0.5% of struts were *deliberately* removed at design time, so the job is
to separate deliberate removals from genuine print defects. The lattice has
**3,430 nodes and 18,468 struts**. After thirteen pipeline phases the automated
answer is **214 candidate defects (1.16%)**, conservatively gated, of which a
human has eyeballed the top 40. A follow-up pass raises that to **228 (1.23%)**
but has *not* been human-checked. What was handed over is **not the pipeline** —
it is a 176-file read-only evidence packet: documentation, output tables, 120
review images, a self-contained 3D viewer, and the agent/skill configs that
drove the work. There is **zero executable code** in it.

---

## 2. What is actually in the box

176 files, all listed with SHA-256 in `MANIFEST.json`: 121 PNG (120 review
panels + 1 label-count bar chart), 22 Markdown, 15 CSV, 8 JSON, 4 YAML, 4 TOML,
1 TXT, 1 HTML. **Zero `.py`, `.sh`, or `.ipynb` — verified by recursive search.**
`raw_data_policy` records the deliberate omissions — no raw TIFF, no STL, no
source JSON under `data/`.

The packet has three layers, and they are best read in that order.

### Layer 1 — agent assets (`agent_assets/`)

This is the layer to read first, because it encodes *how the collaborator wanted
an AI to behave* on this problem, and it is the most reusable thing in the
packet.

**`.agents/skills/part2-defect-analysis/SKILL.md`** is the master playbook. It
declares the governing rule of the whole project: *deterministic Python does the
calculations, the model does planning, gate-checking and note-keeping.* The
model is never allowed to produce a number. It lists a 12-step workflow from
preflight (repo/Git/LFS state) through canonical-graph rebuild, transform-gate
verification, CT-coverage verification, guarded labelling, strict auto-review,
Phase 2C triage, viewer export, config-driven pipeline run, final report, tests,
and note updates. It hard-codes every headline number so a resuming agent can
detect drift. Most valuable are its **six stop gates**: refuse to proceed on
missing or LFS-pointer raw data, on an unresolved coordinate transform, on
incomplete CT coverage, on missing human spot-check labels, on counting blocked
rows as defects, or on presenting auto-promoted rows as human-reviewed.

**`.agents/skills/threshold-optimizer/SKILL.md`** is a focused segmentation
helper. Its core insight is one this repository learned the hard way too: the
raw-CT threshold and the display threshold are different animals. Raw recon
values sit near `[-0.003, 0.015]`, so sweeping around `0.5` segments nothing.
It prescribes a coarse sweep (`0.001…0.010`), a fine sweep, and for uint16 TIFF
a `0.90×–1.10×` band around a sampled Otsu value, scoring each candidate by
foreground fraction, 26-connected component count, and skeleton topology. It
carries a baseline table showing `0.004` is the first threshold yielding a
single connected component on the unit cell, and records that on the 9×9×9 TIFF
the first pass (`36916`, i.e. `0.90×` Otsu) over-segmented at 3/5, improved to
`38557` with `open_close2d`, Dice `0.8976`.

**`.agents/skills/nde_report_expert/SKILL.md`** is the thinnest of the three and
the least finished: load raw/mask/skeleton `.npy`, compute mean intensity,
voxel volume and skeletal complexity, render two fixed 3D views
(`elev=30/azim=45` and `elev=60/azim=45`), emit a Markdown report. It references
a `3d_visualize` script and MCP tools `segment_ct_dataset()` / `skeletonize()`
that are not shipped, and it has no `openai.yaml`, unlike its two siblings.

**`.codex/agents/*.toml`** are four Codex agent definitions, all
`model="gpt-5.5"`, `model_reasoning_effort="xhigh"`,
`sandbox_mode="workspace-write"`. `part2_defect_analysis_agent` is the
orchestrator and mirrors the master skill. `ct_visual_review_agent` owns panel
generation and is explicitly **forbidden from making the final classification** —
a good separation of concerns. `phase2b_ct_calibration_agent` is the strictest:
it must read `anchor_gate_summary.json` and refuses to run unless
`anchor_gate_status == ANCHOR_GATE_PASSED`, then must use
`best_transform_id == perm021_signmmm`. `segmentation_agent` owns Task 6, caps
itself at 10 optimisation iterations, stops after 3 failures, and refuses to run
on a Git-LFS pointer.

### Layer 2 — method and config (`method_and_config/`)

**`part2.yaml`** (schema 0.2.0) is the single source of pipeline truth: seed
`20260723`, `overwrite_existing=false`, `forbid_git_write_operations=true`,
`raw_data_read_only=true`. It pins the expected TIFF shape `[761, 815, 837]`,
the geometry (`unit_cell_edge_mm=4.56`, `graph_units_per_unit_cell_edge=2.0`,
therefore `mm_per_graph_unit=2.28`), the registration constants
(`39.48880949493` voxels per graph unit, `0.3351084961°` rotation, translation
`[59.3396, 52.1829, 26.4617]` voxels), segmentation candidates
`[38557, 40000, 41018]`, sampling geometry (coarse 48 axial bins / detailed 64,
endpoint exclusion 0.12/0.10, radial radius 5/9 voxels), a `max_memory_gb=6.0`
CT-access cap, and downstream mechanics inputs (Ti-5553: E=85 GPa, ν=0.31,
ρ=4650 kg/m³).

**`scientific_assumptions.yaml`** is the best artefact in the entire packet and
the thing most worth stealing. It is a register of 23 numbered assumptions, each
with an explicit status — `CALIBRATED`, `UNVERIFIED`, or `REJECTED` — and the
evidence that earned it. Two are marked **REJECTED**, and the honesty is the
point: `A-STL-001` (direct STL triangle-set differencing) died on 157,833
baseline-only triangle keys against a count-drop of only 15,986; `A-CT-SAMPLER-001`
(the first CT sampler) died with a group-mean difference of `-0.2956`, a 95% CI
of `[-1.249, 0.610]` straddling zero, and ROC AUC `0.4758` — literally chance.
A pipeline that writes down its own failed hypotheses is doing science.

**`METHODS_AND_PHYSICS_REFERENCE_LEDGER.md`** (35 KB) is the formula book: the
centreline parameterisation `x(t) = (1-t)p₀ + t·p₁`, the design-intent score
`delta(t) = dist(x(t), 0.5.stl) − dist(x(t), 0.stl)` with `base_score` the
median over `t ∈ [0.20, 0.80]`, the voxel-difference operator `D_p = M₀ ∧ ¬M_p`,
the cross-section area `A(s)` and equivalent radius `r_eq(s) = √(A(s)/π)`, the
robust negative-residual definition, the fusion objective
`J(T) = median(anomaly | removed, T) − median(anomaly | present)`, and the exact
Phase 2B.2/2B.3/2B.4/2C rule thresholds. Every claim carries a citation key.

**`requirements.txt`** is six bare package names — `numpy`, `matplotlib`,
`fastmcp`, `scikit-image`, `tifffile`, `scipy` — with **no version pins at all**.

### Layer 3 — results (`final_report_baseline/`, `review_tables/`, panels, viewer)

`final_report_baseline/` freezes the Phase 2B.4 answer: `final_ct_defect_summary.json`
carries the status string `SPOTCHECK_SUPPORTED_AUTOMATED_ESTIMATE_NOT_FULL_GROUND_TRUTH`
(exactly the right label), the counts 202 missing + 12 disconnected = 214, plus
89 designed-removed, 14,820 present-like, 920 blocked, 2,425 low-priority.
`run_manifest.json` records git provenance (branch `haseeb`, HEAD `eceb89c9`)
and input hashes. `tables/headline_numbers.csv` is the one-row summary.
`human_spotcheck_labels_rank001_040.csv` holds the only real human labels in the
packet: 29 `material_absent`, 7 `material_disconnected`, 4 `ambiguous`, **0
contradictions**.

`review_tables/` holds the Phase 2C state. `phase2c_labels.csv` is the big one —
18,468 rows (every strut) × ~90 columns spanning every phase's features, 46 MB.
The rest are work queues: `newly_promoted_14_to_verify.csv`,
`remaining_review_required_677_to_verify.csv`,
`low_priority_uncertain_2654_audit_table.csv`, and
`human_verification_template.csv` (3,345 rows = 14 + 677 + 2,654) with six blank
columns awaiting a reviewer.

`review_panels_phase2c_top120/` is 120 PNG review panels plus a summary CSV/JSON.
The naming convention is `rank_{NNN}_E_N{aaaaaa}_N{bbbbbb}_ct_panel.png` — rank in
the anomaly ordering, then the two canonical node IDs the strut connects.

The panels themselves are the best-engineered artefact in the packet. Each is a
five-panel figure: XY, XZ and YZ maximum projections of the local CT crop with
the expected strut drawn as a cyan line; a *straightened, edge-aligned slab*
projection that unrolls the strut along its own axis so a gap is visible as a
dark band; and an along-edge intensity plot carrying tube max, tube p95, tube
mean, centreline value, and the visual threshold. On `rank_001` the evidence is
immediate — intensity sits flat near 32,500 (below the 40,054 Otsu threshold)
for the first 80% of the edge, then climbs past 45,000 only where the strut
meets its node. The strut body is empty.

Two details show real care. The title carries edge ID, source strut ID, label
and anomaly score, so a panel is self-describing if it gets separated from its
table. And the footer states: *"Review aid only, not final defect label. Cyan
line is a drawn registered-edge marker, not CT material. Yellow contour/line is
visual threshold reference only."* That is precisely the warning a reviewer — or
a model — needs to avoid mistaking an annotation for evidence.

`viewer/index.html` is a 7.6 MB self-contained 3D viewer. All data is inlined in
a `<script id="viewer-data" type="application/json">` block; there are no
`fetch`, `XMLHttpRequest`, or external `<script src>` calls, so it opens
directly from `file://` with no web server and no CORS problem. It renders the
lattice graph on a canvas with rotate/zoom/click-to-inspect and search-by-edge-ID,
coloured by the seven Phase 2C classes.

---

## 3. The pipeline, phase by phase

The pipeline's real story is a sequence of **method failures and recoveries**,
which is why the phase numbering is so irregular.

**Phase 0 — canonical graph.** The raw junction JSON contains duplicate aliases
for the same physical node. Phase 0 welds them by position tolerance
(`1e-8` nominal, `1e-6` registered voxels) and assigns stable edge IDs, yielding
the canonical **3,430 nodes / 18,468 struts** that every later phase counts
against.

**Phase 1 — design intent.** Before you can call anything a defect you must
subtract the struts that were *designed* away. Phase 1 walks each strut's
centreline and scores `dist(x(t), 0.5.stl) − dist(x(t), 0.stl)`. It finds a
natural score gap after rank 91, giving **92 design-removed edges** against an
expectation of `0.005 × 18,468 = 92.34`. That near-exact hit is the single
strongest validation in the project.

**Phase 2A — first CT sampler (FAILED).** An edge-owned 3D sampler with junction
exclusion, calibrated on 468 edges, could not separate design-removed struts
from present ones: mean difference `−0.296`, 95% CI `[−1.25, 0.61]`, ROC AUC
`0.476`. Chance. Recorded as `A-CT-SAMPLER-001: REJECTED`.

**Phase 2A.1 — exact STL distance + symmetry audit (UNRESOLVED).** The 2A
failure was blamed on coordinate ambiguity, so 2A.1 ran exact point-to-triangle
scoring over all 18,468 edges and audited **48 candidate transforms** (6 axis
permutations × 8 sign choices). The audit failed to pick a winner — the top
scores were separated by only ~0.006. An 80-panel gold-review packet was built
(30 clear-removed, 30 clear-present, 20 ambiguous) but the human labels were
left blank.

**Phase 2R — method pivot.** Abandons distance scoring for STL voxel-occupancy
subtraction (`D_p = M₀ ∧ ¬M_p`), a CT-only strut atlas, and late-fusion
transform ranking. `perm021_signmmm` leads. **This phase's status was initially
published as VERIFIED and then corrected to PROVISIONAL** when an audit found
only 7 of 67 mapped components actually had CT coverage. A coverage gate
(≥30 edges and ≥50% coverage) was added as a result.

**Phase 2R.1 — human anchoring.** CT coverage expanded to 1,300 edges to reach
67/67 coverage, and 5 primary + 5 backup human anchor panels were labelled.
All 5 confirmed `perm021_signmmm`, 0 contradictions → `ANCHOR_GATE_PASSED`.
Note what this means: the coordinate transform underpinning the entire project
is **anchored by five human-labelled images, not derived analytically.**

**Phase 2B / 2B.1 — recalibration.** With the transform fixed, CT separation of
94 design-removed against controls now works: **AUC 0.9626**, threshold `2.0135`.
2B.1 resolves the 67-blob vs 92-strut discrepancy by volume ratio
(`n = max(1, round(V/V_ref))`), giving 94 candidates and AUC `0.9635`.

**Phase 2B.2 — full coverage.** Extends CT feature extraction from 1,326 to all
**18,468/18,468** edges. The first attempt crashed from buffered stdout, which
is why checkpointing exists.

**Phase 2B.3 — guarded labels.** A rule system over seven evidence signals
(anomaly score, gap fraction, occupied fraction, area, contrast, connectivity,
stability) produces 14,820 present-like, 420 possible-missing, 58
possible-disconnected, and a **3,573-row review queue** — too big for a human.

**Phase 2B.4 — strict auto-support.** Tightens to `score ≥ 3.3135` plus ≥7
evidence flags for missing / ≥5 for disconnected, plus stability bounds. Yields
the headline **202 + 12 = 214**, leaves **920 blocked**, demotes 2,425 to
low-priority. A human reviewed the top 40 panels: 36 defect-like, 4 ambiguous,
**0 contradictions**.

**Final report.** Packages 214/18,468 = **1.159%** with the explicit
not-ground-truth status string.

**Phase 2C — triage the blocked.** Re-examines the 920 blocked rows using only
already-extracted features (no TIFF re-read) under a bounded promotion rule.
Promotes just **14**, leaving 677 still-review-required (672 + 5 design-intent
conflicts) and demoting 229 to low-priority. New total **215 + 13 = 228 (1.23%)**.
The 14 promoted rows are **the assignment** — they have never been human-reviewed.

---

## 4. How to use it

**Read in this order.** `README_START_HERE.md` → `DEFECT_FINDING_PROCESS.md` →
`LABEL_DEFINITIONS.md` → `VERIFICATION_PROTOCOL.md` → `NEXT_AGENT_PROMPT.md`.
Then `agent_assets/.agents/skills/part2-defect-analysis/SKILL.md` for the
operating rules and `method_and_config/scientific_assumptions.yaml` for what is
actually known versus assumed.

**Open the viewer.** Double-click `viewer/index.html`. No server, no install.
Rotate, zoom, click a strut to inspect it, or search by edge ID. This is the
fastest way to get spatial intuition for where the candidates are.

**Do the review work.** The protocol is a strict priority order:

1. `review_tables/newly_promoted_14_to_verify.csv` — the 14 rows Phase 2C
   promoted. Review these first.
2. `review_tables/remaining_review_required_677_to_verify.csv` — high-priority
   rows first.
3. `review_tables/low_priority_uncertain_2654_audit_table.csv` — sample-audit
   only, do not review exhaustively.

For each row, find the matching panel in `review_panels_phase2c_top120/` by edge
ID and fill **only the blank columns** in
`review_tables/human_verification_template.csv`: `human_ct_label`
(`material_absent` / `material_continuous` / `material_disconnected` /
`unexpected_material` / `ambiguous`), `human_design_label_if_relevant`,
`reviewer_confidence`, `reviewer_initials`, `review_date`, `reviewer_notes`, and
`recommended_action`.

**The rules that matter.** Never edit the source Phase 2C CSVs. Never let a
model invent a human label from an image — the whole design intent is that
`human_ct_label` means a person looked. Do not count the 677 or the 2,654 as
defects. Do not describe 228 as spot-check-supported until the 14 are reviewed.

**The deliverable** is a count of how many of the 14 support absent/disconnected,
how many are ambiguous, how many contradict, and a recommendation on whether the
baseline stays at 214 or moves to 228.

---

## 5. Why it is useful

**It is honest about uncertainty in a way most analysis pipelines are not.**
The status string is `SPOTCHECK_SUPPORTED_AUTOMATED_ESTIMATE_NOT_FULL_GROUND_TRUTH`.
The rejected assumptions stay in the register with their failing statistics. A
premature `VERIFIED` was walked back to `PROVISIONAL` in writing. 920 rows that
could not be resolved were left unresolved rather than quietly binned. That
discipline is rarer and more valuable than the defect count itself.

**The separation of concerns is right.** Deterministic Python computes; the
model plans and gate-checks. The visual-review agent is structurally forbidden
from making the final call. The calibration agent physically cannot start until
a gate file says a human confirmed the transform. This is a template for how to
use agents on scientific data without letting them fabricate results.

**`scientific_assumptions.yaml` is directly reusable.** A 23-entry assumption
register with `CALIBRATED`/`UNVERIFIED`/`REJECTED` states and evidence is a
pattern this repository should adopt wholesale.

**It cross-validates our own work.** See §7 — his registration constants and
mine agree to every recorded digit, which independently confirms both
implementations.

**The review packet is genuinely actionable.** Prioritised queues, a
pre-populated template with exactly the blank fields a reviewer must fill, 120
matching panels, and a zero-install viewer. Someone can start reviewing in under
a minute.

---

## 6. What is wrong, and what needs to improve

Ordered by how much they threaten the conclusions.

### 6.1 The discrepancy against the published paper is never addressed — and it is entirely in one class

His own notes (`notes_snapshot/01-how-to-run-code.md`, line 1087) record:

> The paper reports about `105` missing struts and about `918` disconnected
> struts for this specimen, using our JSON strut count as an approximate
> denominator.

That is **1,023 struts ≈ 5.54%** against the same 18,468 denominator, versus the
pipeline's **214 ≈ 1.16%**. But the aggregate 4.8× gap hides the real story,
which only appears when the two classes are split:

| class | paper | pipeline (2B.4) | ratio |
| --- | --- | --- | --- |
| missing | ~105 | **202** | pipeline finds **1.9× more** |
| disconnected | ~918 | **12** | pipeline finds **76× fewer** |
| combined | ~1,023 (5.54%) | 214 (1.16%) | 4.8× fewer |

So the missing-strut detector is not under-sensitive at all — it is arguably
*over*-sensitive relative to the paper. **The entire discrepancy lives in the
disconnected class**, where the pipeline is effectively blind. That is a precise,
actionable diagnosis, and it is not in the packet.

Worse, the sentence above is the *only* place these figures appear, buried at
line 1087 of a 62 KB how-to-run document. It is never revisited in any phase
note, in the final report, or in `README_START_HERE.md`. A reader who does not
know the paper would take 1.16% as the answer. **This belongs at the top of
`README_START_HERE.md`.**

### 6.2 The transform search space was half-degenerate by construction

Phase 2A.1 searched "6 axis permutations × 8 sign choices = 48 transforms" and
could not separate the top candidates (~0.006 apart), which forced the fallback
to human anchoring in 2R.1. There is a structural reason. I enumerated all 48
matrices: exactly **24 have determinant +1 (real rotations) and 24 have
determinant −1 (mirror reflections)**, and for **every one of the 24 proper
rotations, its mirror twin `−R` is also in the set**. An octet truss is
centrosymmetric, so `R` and `−R` produce nearly identical occupancy scores — the
search was ranking each real candidate against its own indistinguishable mirror
image. Restricting to the 24 proper rotations (`det = +1`) would likely have
resolved the transform analytically and made Phase 2R.1's human anchoring
unnecessary. His final answer `perm021_signmmm` is itself proper (`det = +1`,
a 180° rotation), so the conclusion is sound — but it was reached by a route
that did not have to be that hard. *(This repo's `tif2stl/registration.py`
searches only the 24 proper rotations for exactly this reason.)*

### 6.3 Nothing in the packet is reproducible

There is no source code, no `src/`, no `tests/`, no `configs/`, and no raw data.
Every command in every document — `python3 -m src.part2.phase2c_manual_queue_triage`,
`python3 -m src.part2.final_report`, all 8 named test modules — refers to files
that do not exist here. The packet documents 93 passing tests that cannot be
run. It is an evidence archive, not a deliverable someone can verify from first
principles. Adding the `src/part2/` tree and `tests/part2/` would change this
from "trust me" to "check me."

### 6.4 `requirements.txt` has no version pins

Six bare names. `scikit-image` changed `skeletonize` behaviour across versions
and `scipy.ndimage` has shifted defaults; a pipeline whose thresholds are
calibrated to four decimal places cannot float its dependencies. Pin them.

### 6.5 Thresholds are dataset-calibrated and presented as if physical

`score ≥ 3.3135416666666666`, `gap ≥ 0.5208333333333333`,
`contrast ≤ 0.028496128080248578`. The repeating decimals show these are
quantiles of this one specimen (`n/96`, `n/48`), not physics. The ledger says so,
but the skill files quote them as fixed constants an agent must reproduce. On a
second specimen they will not transfer, and an agent following the skill would
not know that.

### 6.6 The segmentation threshold was tuned on a single slice

`38557` was selected by scoring slice 380 against one ground-truth image
(Dice 0.8976). One slice out of 761, in a volume the collaborator's own notes
say has quality variation. Generalisation to the full volume is asserted, not
demonstrated.

### 6.7 The strict gate destroys the disconnected signal specifically

Only 12 of 214 baseline candidates (13 of 228) are `disconnected`, against the
paper's ~918. Trace the class through the phases and the cause is visible:
Phase 2B.3's guarded labels found **58** possible-disconnected, and Phase 2B.4's
strict gate cut that to **12** — a 79% loss — while the missing class only fell
from 420 to 202 (52%). The strict rule requires ≥5 evidence flags for
disconnected versus ≥7 for missing, but both classes share thresholds calibrated
on *missing* struts (the design-removed set used for calibration in Phase 2B is
made of fully-absent struts, because that is what removing a strut from the STL
produces). There is no disconnected-strut calibration set anywhere in the
pipeline. The detector is being scored against the wrong reference class, and
`longest_low_area_gap_fraction` — the one feature that should carry
disconnection — is thresholded at `≥0.5208`, which demands the gap span more
than half the strut. A real cracked or partially-bonded strut has a short gap.
This class needs its own calibration study before any number from it is quoted.

### 6.8 Smaller items

- `MANIFEST.json` includes itself in its own `files[]` list, so it carries a
  SHA-256 that can never match — the entry describes a pre-finalisation revision
  and is unverifiable by construction. Drop the self-entry or publish the
  manifest hash in a detached sidecar.
- The strut diameter conflict (README 350 µm vs paper 424 µm) is logged as
  `A-DIAM-001: UNVERIFIED` and never resolved, yet diameter feeds the radial
  sampling radius.
- The baseline spot-check panel PNGs are **not shipped** — verified, 0 of the 80
  indexed by `spotcheck_panel_index.csv` are present. The 40 human labels that
  support the headline 214 cannot be re-checked against the images that produced
  them. Only Phase 2C's 120 panels are included. (Of the 80 indexed rows, only
  ranks 1–40 carry labels in the first place.)
- `viewer/` ships three sidecars — `viewer_data.json`, `legend.json`,
  `run_manifest.json` — that `index.html` never references, because it inlines
  its entire payload. `viewer_data.json` alone is **10.5 MiB of duplicated
  data**, making the viewer directory roughly 2.4× larger than it needs to be.
- The viewer draws graph edges, not segmented CT surface, so it shows where the
  algorithm says material is missing, not what the scan looks like.
- `nde_report_expert` is unfinished relative to its siblings (no `openai.yaml`,
  references an unshipped `3d_visualize` script and two MCP tools).
- A human-anchor label CSV was once saved as a Numbers/iWork ZIP with a `.csv`
  extension and had to be repaired by hand — a near-miss worth a format check in
  the loader.

---

## 7. Independent verification and cross-validation

Everything below was re-derived independently rather than taken from the packet's
own claims. The tooling lives in `Aman_Scripts/collaboration/verify_handoff.py`:

```bash
conda run -n DSC python Aman_Scripts/collaboration/verify_handoff.py
```

**81 checks: 78 PASS, 3 FAIL, 0 SKIP.** Report written to
`Aman_Scripts/outputs/collaboration/` as `verify_handoff_report.{json,md}`,
`verify_handoff_checks.csv` and a SHA-256 `manifest.json`. The verifier's own
helpers are covered by 62 adversarial unit tests in
`Aman_Scripts/ComponentTests/test_collaboration_verify.py` (BOM, CRLF, quoted
embedded newlines, unicode filenames, `../` path traversal, off-by-one and
zero-based rank columns, `data:` URIs, HTML entities), registered in `run_all.py`
— full regression **531/531 PASS**.

| category | checks | pass | fail |
| --- | ---: | ---: | ---: |
| integrity (hashes, sizes, orphans, path safety) | 10 | 8 | 2 |
| arithmetic (count reconciliation) | 20 | 20 | 0 |
| row counts (claimed vs actual CSV rows) | 15 | 15 | 0 |
| linkage (panels ↔ tables ↔ label table) | 26 | 25 | 1 |
| cross-check (against this repo's own data) | 6 | 6 | 0 |
| viewer | 4 | 4 | 0 |

### 7.0 Integrity — 175/175 payload files verify

Every one of the 175 payload files matches its manifest SHA-256 and byte size
exactly. No file is missing, no unlisted file is present, and no manifest path
escapes the packet via `..` or an absolute path. **The packet is bit-for-bit
intact.**

The two integrity failures are a single benign artefact: `MANIFEST.json` lists
*itself* among its 176 entries, so it carries a hash of an earlier revision of
itself. It declares `size_bytes: 2057` / sha256 `cb9eb3ae…cd4ddd31`, while the
shipped file is **37,600 bytes** / sha256 `c7624c31…b5845652` — the self-entry
was written when the manifest was ~5% of its final size, not merely a few bytes
short. A manifest cannot contain its own final hash, so the entry is
unsatisfiable by construction. It is a design flaw, not evidence of tampering;
drop the self-entry or move it to a detached sidecar. The companion check
(INT-09) independently confirms **175/175 payload files verify**.

The one linkage failure is real and matters: **`spotcheck_panel_index.csv`
indexes 80 panels, and 0 of those 80 PNGs are shipped.** These are the images
behind the 40 human spot-check labels that support the headline 214. Those
labels therefore cannot be re-checked against the evidence that produced them.

### 7.0b Independent reproduction of the lattice graph — exact

The most valuable check. Starting from this repository's own copy of the raw
registered JSON and this repository's own graph code, with no reference to the
packet's tables:

| step | recomputed here | packet claims |
| --- | --- | --- |
| junction records parsed | 10,206 | 10,206 |
| nodes after coincident-node welding | 3,430 | 3,430 |
| struts enumerated | **18,468** | 18,468 |
| edge **set** comparison | packet-only 0, repo-only 0, unmapped 0 | — |

Not merely the same count — **the same set of edges**, element for element.
Two independently written graph builders, run on the same raw JSON, produce
identical topology. Combined with the registration agreement in §7.2 below, the
geometric foundation under his defect counts is independently confirmed.

### 7.1 Internal consistency — clean

Every count in the packet reconciles exactly. The 920 rows blocked at Phase 2B.4
partition perfectly under Phase 2C as **14 promoted + 677 still-review
(672 + 5 design-conflict) + 229 demoted = 920**, which carries the baseline
214 → 228 and the low-priority 2,425 → 2,654. The human-verification template's
3,345 rows equal 14 + 677 + 2,654 exactly. The spot-check labels
(29 absent + 7 disconnected + 4 ambiguous = 40) tie the headline CSV. The class
counts in `phase2c_summary.json`, `viewer/run_manifest.json`, and the JSON
embedded inside `viewer/index.html` are three-way identical. `18468` is
consistent across every file that states it. **No arithmetic errors found.**

The one trap for a reader: the baseline triple (214 / 920 / 2,425) and the
Phase 2C triple (228 / 677 / 2,654) look contradictory but are sequential
stages, related by the +14 / +229 deltas above.

### 7.2 Registration constants — exact independent agreement

This is the strongest positive result of the cross-check. His `part2.yaml` pins
the design→CT registration as `39.48880949493` voxels per graph unit and
`0.3351084961°` rotation. This repository's `Aman_Scripts/tif2stl` derives, from
the same two JSONs but a completely separate implementation:

| quantity | his `part2.yaml` | our `tif2stl` |
| --- | --- | --- |
| scale (voxels/unit) | `39.48880949493` | `39.48880949493017` |
| rotation (degrees) | `0.3351084961` | `0.33510849611461374` |
| fit RMS | — | `3.33e-12` voxels |

Identical to every digit he recorded. Two independently written Umeyama fits
agreeing to twelve significant figures means neither implementation has a bug in
the step that everything else depends on. **The registration is trustworthy.**

### 7.3 The 48-transform search was half mirror images

Verified by direct enumeration. Of the 48 signed permutation matrices his
Phase 2A.1 searched, exactly **24 have `det = +1`** (physically realisable
rotations) and **24 have `det = −1`** (mirror reflections). All 48 are
orthogonal, so there is no third case. Critically, **for all 24 proper
rotations, the mirror twin `−R` is also present in the set**. An octet truss is
centrosymmetric, so `R` and `−R` score almost identically on any occupancy
metric — the search was ranking every real candidate against its own
indistinguishable mirror. That fully explains the reported ~0.006 separation and
the `UNRESOLVED` verdict that forced human anchoring in Phase 2R.1.

His final answer `perm021_signmmm` is itself proper (`det = +1`, a 180°
rotation), so the conclusion is correct. Restricting the search to the 24 proper
rotations would likely have resolved it analytically.

### 7.4 A scale bug — in *our* pipeline, not his

Cross-checking his `mm_per_graph_unit = 2.28` against our `tif2stl` value of
`2.3052` exposed a defect on our side. `tif2stl` computes
`mm_per_design_unit = STL bbox X-extent / 18`, which divides a **surface**
bounding box by a **centreline** span. For a solid mesh those cannot be equal —
the bbox necessarily overshoots the outermost node centres by one strut
diameter. Measured directly from `data/missing_struts/stls/0.5.stl`:

| quantity | value |
| --- | --- |
| bbox X extent | `41.49278 mm` |
| bbox Z extent | `41.49562 mm` (matches X to 3 µm — both are pure lattice axes) |
| node-centre span at 2.28 mm/unit (18 × 2.28) | `41.04000 mm` |
| overshoot | `0.45278 mm` |
| paper strut diameter | `0.424 mm` → residual **+0.029 mm** (half a voxel) |
| challenge nominal diameter | `0.350 mm` → residual +0.103 mm |

The overshoot matches one paper strut diameter to within half a voxel. **His
2.28 is right and our bbox-derived 2.3052 is biased ~1.1% high.** Solving for
the unit given the paper diameter gives `(41.49278 − 0.424)/18 = 2.2816`, within
0.07% of his 2.28.

### 7.5 Rerunning with the corrected scale — the prediction failed, informatively

I expected correcting the scale to improve agreement. It did not:

| metric | bbox scale (2.3052) | design-spec scale (2.28) |
| --- | --- | --- |
| lattice-window Dice | **0.4483** | 0.4263 |
| full-grid Dice | **0.3815** | 0.3629 |
| CT-in-design (+tol) | 0.7347 | **0.7540** |
| design-in-CT (+tol) | **0.6036** | 0.5669 |
| voxelised STL cells | 8,517,337 | 8,742,279 |
| implied voxel pitch | 58.375 µm (+0.47%) | 57.738 µm (−0.62%) |

Dice fell. But the *direction* of the two containment metrics is diagnostic: with
the correctly-scaled (larger) design, **more of the CT fits inside the design
envelope** (0.7347 → 0.7540) while **more design material has no CT counterpart**
(0.6036 → 0.5669). That is the exact signature of struts printing **thinner than
CAD** — expected LPBF behaviour, and the actual subject of the challenge. The
previously higher Dice was partly an artefact of an undersized STL accidentally
compensating for genuinely under-built struts.

The corrected run also flips the sign of the pitch discrepancy, from a
physically odd "printed part is 0.5% *larger* than CAD" to a plausible "printed
part is 0.6% *smaller* than CAD" — i.e. ordinary thermal shrinkage.

Artifacts: `Aman_Scripts/outputs/tif2stl_scalefix/`. The `tif2stl` default is
**left unchanged** pending a decision, since altering it revises every published
metric in `Aman_Scripts/outputs/tif2stl_plate/`. The flag
`--mm-per-design-unit 2.28` already exists, so no code change is needed to adopt
it.

---

### 7.6 What was built to produce this

| file | purpose |
| --- | --- |
| `Aman_Scripts/collaboration/verify_handoff.py` | 81-check verifier: manifest integrity, count arithmetic, CSV row counts, panel/table linkage, cross-validation against this repo's data, viewer analysis |
| `Aman_Scripts/ComponentTests/test_collaboration_verify.py` | 62 adversarial unit tests over the verifier's helpers |
| `Aman_Scripts/outputs/collaboration/` | generated report (JSON + Markdown + CSV + manifest) |
| `Aman_Scripts/outputs/tif2stl_scalefix/` | the §7.5 corrected-scale validation run |

The verifier exits non-zero only on an **integrity** failure; arithmetic and
linkage findings are reported but do not fail the run, since those are the
collaborator's to resolve rather than ours.

---

## 8. Bottom line

**The foundation checks out.** The packet is bit-for-bit intact (175/175 payload
hashes), every count reconciles across every file, and the two things everything
else rests on — the 18,468-strut lattice graph and the design→CT registration —
reproduce *exactly* against an independently written implementation in this
repository. The graph is not merely the same size, it is the same edge set.

**The methodology is careful and unusually honest.** Failed hypotheses stay in
the assumption register with their failing statistics. A premature `VERIFIED`
was walked back to `PROVISIONAL` in writing. 920 unresolvable rows were left
unresolved rather than quietly binned. The agent configs structurally prevent a
model from inventing a label. That discipline is worth more than the number it
produced.

**The headline weakness is framing, not machinery.** 1.16% is presented as the
answer when the published figure for this specimen class is ~5.5%, and splitting
that gap by class shows the missing-strut detector is actually *over*-sensitive
(202 vs ~105) while the disconnected detector is effectively blind (12 vs ~918).
The disconnected class was never given its own calibration set — it inherits
thresholds tuned on fully-absent struts — and Phase 2B.4's strict gate cut it by
79%. That single diagnosis is the most useful thing in this review, and it is
absent from the packet.

**Three things would fix most of it**: put the paper comparison at the top of
`README_START_HERE.md`, build a disconnected-strut calibration set, and ship the
`src/part2/` tree so the 93 documented tests can actually be run. Pin the
dependencies while you're there.

**And one correction flows the other way.** Cross-checking his geometry against
ours exposed a real defect in *our* `tif2stl`: deriving mm-per-design-unit from
an STL bounding box overstates it by one strut diameter (§7.4). His `2.28` is
right and our `2.3052` is not. That is what a good cross-validation looks like —
it should find something on both sides, and it did.
