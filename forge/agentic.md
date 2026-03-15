<!-- Copyright 2026 Victor Santiago Montano Diaz
     Licensed under the Apache License, Version 2.0 -->

# Agent Forge, Meta-Workflow Orchestrator

## Trigger Commands

- `create new workflow`
- `new agentic project`
- `build workflow for [domain]`
- `/create-workflow`

---

## Workflow Overview

```
Step 1         Step 2          Step 3          Step 4          Step 5       Step 6       Step 7
Gather    -->  Design     -->  Generate   -->  Generate   -->  Generate --> Generate --> Review
Requirements   Architecture    Scaffold        Orchestrator    Agents       Scripts      & Deliver
               ⏸               ⏸               ⏸                                        ⏸
```

---

## Step 1: Gather Requirements

**Step file:** `forge/steps/interactive/step_01_gather-requirements.md`

Read the step file and execute it. This step interviews the user to understand what they want to automate.

**Save:** Hold requirements summary in context for subsequent steps.

---

## Step 2: Design Architecture ⏸

**Step file:** `forge/steps/interactive/step_02_design-architecture.md`

Read the step file and execute it. This step designs the workflow structure, identifies agents, patterns, and scripts.

**Wait for user approval. If changes requested, iterate.**

---

## Step 3: Generate Project Scaffold ⏸

**Step file:** `forge/steps/interactive/step_03_generate-scaffold.md`

Read the step file and execute it. This step creates the full project skeleton deterministically: directories, README, CLAUDE.md, commands, standard prompts, and venv.

**Present the complete file listing to the user.**
**Wait for approval.**

---

## Step 4: Generate Orchestrator ⏸

**Step file:** `forge/steps/interactive/step_04_generate-orchestrator.md`

Read the step file and execute it. This step generates the workflow's `agentic.md` using the template and approved architecture. Saves into the scaffold from Step 3.

**Present the complete agentic.md to the user for review.**
**Wait for approval. If changes requested, iterate.**

**Save:** `output/{workflow-name}/agentic.md`

---

## Step 5: Generate Specialized Agents

**Step file:** `forge/steps/interactive/step_05_generate-agents.md`

Read the step file and execute it. This step generates agent prompt files and step definition files. Agents emit `## Script Requirements` sections in step files for scripts needed at runtime.

**Save:** `output/{workflow-name}/agent/Prompts/` and `output/{workflow-name}/agent/steps/`

---

## Step 6: Generate Scripts

**Step file:** `forge/steps/interactive/step_06_generate-scripts.md`

Read the step file and execute it. This step generates workflow-specific scripts identified in architecture (Step 2) and emitted from step files (Step 5). Skip if no scripts are needed.

**Save:** `output/{workflow-name}/agent/scripts/`

---

## Step 7: Review and Deliver ⏸

**Step file:** `forge/steps/interactive/step_07_review-deliver.md`

Read the step file and execute it. This step runs the quality reviewer's checklist and delivers the final summary.

**Fix any issues found before delivering.**

---

## After Each Step

**ALWAYS ask for user approval before saving/marking complete:**

1. Show output to the user
2. Ask: "Does this look good? Any changes needed?"
3. **Wait for user approval**
   - If changes requested → Modify and show again
   - If approved → Continue
4. Save files
5. Confirm: "Saved"

**NEVER proceed to the next step without user confirmation.**

---

## Clarifications

### Self-Similar Architecture
Agent Forge generates workflows that follow the **same architecture** as Agent Forge itself. If you're unsure how to structure something in the generated workflow, look at how Agent Forge does it. The `forge/` directory IS the reference implementation.

### Step File Architecture
Generated workflows use a thin orchestrator + step files pattern:
- `agentic.md` contains step order, pause/approval gates, and references to step files
- `agent/steps/step_{NN}_{step-name}.md` contains the full execution spec for each step
- Each step file defines: prompt reference, inputs, workflow actions, and required outputs
- Step outputs go to `output/{run_id}/agent_outputs/` (inter-step context) and `output/{run_id}/user_outputs/` (user deliverables); the `{run_id}` is provided by the API executor at runtime to isolate concurrent runs, and output directories are created automatically before execution starts

### Templates vs From Scratch
**ALWAYS** start from the scaffold templates in `forge/utils/scaffold/`. Never write an `agentic.md`, `README.md`, `CLAUDE.md`, agent prompt, or command file from scratch. The templates exist to enforce consistency. Fill in the placeholders, adapt the structure, but keep the skeleton.

### When to Add Approval Gates
Not every step needs a gate. Add `⏸` only at **decision points** where:
- The user needs to review a design before generation starts (e.g., architecture review)
- Generated content must be approved before building on top of it (e.g., orchestrator review)
- The final deliverable is ready for sign-off

Steps that are purely mechanical (e.g., "generate commands from an already-approved architecture") do NOT need gates.

### When to Add Quality Loops
Only add evaluate-iterate loops when:
- There is a **measurable quality bar** (e.g., "90% of rubric criteria met")
- The output can be objectively improved through iteration
- The user expects iterative refinement as part of the workflow

Do NOT add quality loops to steps where the output is either correct or not (binary).

### Step Count
5-9 steps is the sweet spot. Fewer than 5 usually means steps are too broad and the agent won't know what to focus on. More than 9 usually means steps are too granular and the workflow becomes tedious. If you find yourself designing more than 9, combine related steps.

### Agent Count
Not every step needs a dedicated agent. Agents are for steps that require **specialized expertise** (e.g., "Software Architect" for design, "Code Generator" for implementation). Mechanical steps like "copy a template" or "create folders" don't need agents. The orchestrator handles them directly.

### Generated Workflows Must Be Self-Contained
Every workflow in `output/` must work **without Agent Forge installed**. This means:
- No references to `forge/`, `forge/patterns/`, or `forge/examples/`
- All prompts, commands, and templates are included in the generated project
- A user can copy the output folder anywhere and it works

### The Orchestrator is the Source of Truth
The `agentic.md` file is the **single source of truth** for any workflow. Slash commands are shortcuts that point INTO it, not replacements for it. Step files are read BY it, not independently. Agent prompts are read by step files. Everything flows through the orchestrator.

### Naming Generated Workflows
- Workflow folder: `kebab-case` (e.g., `content-pipeline`)
- Slash commands: `kebab-case` matching step names (e.g., `generate-content.md`)
- Step names: Title Case, human-readable. Describe WHAT the step does ("Generate PDF Report"), never HOW ("Generate PDF report using gen_document.py"). Script filenames belong in the step's workflow details, not in the step title or description.
- Agent prompts: zero-padded with underscores (e.g., `01_Content_Strategist.md`)
- Step files: `step_{NN}_{step-name}.md` (e.g., `step_01_gather-requirements.md`)
- Master command: always named `start-{workflow-name}.md` or `create-{workflow-name}.md`

### What Agent Forge Does NOT Do
- It does **not** generate application code (apps, APIs). It generates **workflow definitions** (orchestrators, prompts, commands) and **utility scripts** that support those workflows (format generators, data processors, API clients, etc.).
- It does **not** execute the workflows it generates. It only creates the files.
- Dependencies and venvs are set up automatically by `generate_scaffold()`. No manual environment setup is needed.

---

## Quality Checks

| Step | Check |
|------|-------|
| 01 | Description provided? Steps inferred or clarified? Requirements summary confirmed? |
| 02 | Architecture reviewed? Patterns identified? Agents listed? Scripts identified (or "none")? |
| 03 | generate_scaffold() called? Directories, commands, standard prompts, venv created? README, CLAUDE.md present? |
| 04 | Orchestrator follows template? All steps present with step file references? Gates correct? |
| 05 | All agents generated? Each has all required sections? Step files have inputs/outputs? Script Requirements emitted where needed? |
| 06 | All scripts generated via add_script()? Tests pass? Dependencies installed? Skip if none needed. |
| 07 | Self-review passes all checks? Workflow is self-contained? Step files properly structured? |
| 08 | If computer use: agent prompt, execution commands, and config present? |
