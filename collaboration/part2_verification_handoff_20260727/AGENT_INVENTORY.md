# Agent And Skill Inventory

This packet includes the agent and skill files needed for collaborators to
continue the verification workflow.

## Main Agent

```text
agent_assets/.codex/agents/part2_defect_analysis_agent.toml
```

Role:

- main orchestration agent for Part 2;
- reads notes and stop gates;
- runs/audits Phase 2 workflow;
- understands Phase 2C triage and viewer export;
- preserves caveats around the `214` baseline and `228` newer automatic result.

## Specialized Agent Configs

```text
agent_assets/.codex/agents/ct_visual_review_agent.toml
```

Role:

- helper for CT edge-panel review and visual inspection workflows.

```text
agent_assets/.codex/agents/phase2b_ct_calibration_agent.toml
```

Role:

- helper for CT calibration, feature interpretation, and Phase 2B-style checks.

```text
agent_assets/.codex/agents/segmentation_agent.toml
```

Role:

- earlier segmentation subagent for thresholding and segmentation-style work.

## Main Skill

```text
agent_assets/.agents/skills/part2-defect-analysis/SKILL.md
```

Role:

- primary reusable skill for Part 2 defect analysis;
- tells Codex what to read first;
- records current Phase 2B.4 and Phase 2C sources;
- lists stop gates and commands.

## Supporting Skills

```text
agent_assets/.agents/skills/threshold-optimizer/SKILL.md
```

Role:

- threshold sweeps, masks, skeletons, and segmentation evidence.

```text
agent_assets/.agents/skills/nde_report_expert/SKILL.md
```

Role:

- NDE report-style visualization helper used earlier in the project.

## How Collaborators Should Use These

Copy this packet into a checkout of the same repository, or keep it as a
reference folder. A collaborator using Codex should start with
`NEXT_AGENT_PROMPT.md` and point the agent to this handoff folder.

