<!-- DSC_PART2_RULES_START -->
# DSC Part 2 Rules to Merge into Repository AGENTS.md

## Scope

These rules apply to all work under `src/part2/`, `tests/part2/`, `outputs/part2/`, Part 2 skills, Part 2 subagents, and Part 2 reports.

## Repository safety

- Never stage, commit, push, reset, checkout, merge, rebase, clean, or delete files unless the user explicitly requests that exact Git action.
- Treat `.tif`, `.tiff`, `.stl`, and source `.json` files as immutable raw inputs.
- Never overwrite a generated run directory. Use a new `run_id` unless the user explicitly authorizes replacement.
- Preserve all existing Part 1 code and notes. Add separate Part 2 modules rather than silently rewriting beginner-oriented Part 1 tools.
- Before editing, record `git status --short --branch` in the run log.

## Scientific traceability

- Every equation, numerical model, physical property, threshold-selection method, and fitted parameter must have a `method_id` and `reference_ids`.
- Every physical quantity must have units in names, schemas, or metadata.
- Every assumption must be registered as `VERIFIED`, `CALIBRATED`, `UNVERIFIED`, or `REJECTED`.
- Distinguish published methods from project-defined metrics. Never make a project threshold sound like a universal physical law.
- Every run must write input hashes, Git state, configuration, package versions, random seeds, transforms, method IDs, and artifact paths.
- Do not claim causation from one CT specimen. Separate observation, association, mechanism hypothesis, and validated cause.
- Do not call a CT TIFF page a print layer. Report CT page, build height, and unit-cell row separately. Only report true LPBF layer numbers when layer thickness and origin are verified.
- Do not compare a DFT bulk modulus directly with the effective modulus of the porous lattice.

## Graph semantics

- Raw JSON junction IDs are not assumed to be unique physical nodes.
- Canonicalize nodes by verified physical position tolerance while preserving all source aliases and unit-cell provenance.
- Keep source strut IDs stable whenever possible.
- Do not run graph connectivity, mechanics, or a GNN on the raw alias graph.
- Distinguish complete-reference graph, specimen design intent, registered expected graph, and CT observation attributes.

## CT defect analysis

- Use the registered JSON as the expected-strut atlas for the available TIFF.
- Use STL comparison to recover intentionally removed edge IDs before calling an absent edge an unintended defect.
- Primary production evidence comes from local 3D CT ROIs around expected struts, not only whole-volume skeleton graph adjacency.
- A physical strut may contain multiple skeleton branches; direct observed-edge equality is not sufficient evidence of intactness.
- Every final label must include evidence, perturbation stability, and review status.
- Unstable or ambiguous cases must be labeled `uncertain`.
- Aggregate agreement with the paper is a sanity check, not the only tuning objective.

## Mechanics

- Implement and test an axial truss baseline before a 3D frame model.
- Frame calculations must state element theory, section properties, material properties, boundary conditions, skin treatment, and limitations.
- Use canonical physical nodes, consistent SI units internally, and sparse assembly.
- Absolute RUS comparison is blocked until skin mass/stiffness and free-boundary conditions are represented adequately.
- Defect criticality must name the response metric and reference state.

## Agent behavior

- Deterministic code performs numerical calculations. Agents plan, invoke tools, inspect artifacts, challenge assumptions, and write reports.
- Subagents must be narrow, bounded, and have explicit stop/failure limits.
- A reference/provenance auditor can block report generation.
- Agents may not silently install dependencies, download large files, or enable internet access.
- Agents must stop when units, coordinate frames, data identity, or model assumptions are unresolved.

## Required documentation after meaningful changes

Update the project task log with:

- what changed;
- why;
- files created/modified;
- commands/tests run;
- results;
- failures/limitations;
- assumptions changed;
- next gated task.

<!-- DSC_PART2_RULES_END -->
