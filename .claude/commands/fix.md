---
description: Diagnose and fix issues in Agent Forge or any generated workflow.
argument-hint: [project-path-or-problem-description]
---

Read `agent/agentic.md` to understand Agent Forge's structure.
Read `agent/Prompts/00_Workflow_Fixer.md` for diagnostic and repair methodology.

Determine the target:

- If "$ARGUMENTS" is a path to a workflow (e.g., `output/my-workflow`), fix that workflow. Read that workflow's `agentic.md` as the source of truth.
- If "$ARGUMENTS" is a complaint or instruction (not a path), fix Agent Forge itself. You are already reading Agent Forge's own agentic.md.
- If "$ARGUMENTS" is empty, ask the user what needs fixing.

For prompt quality issues, also read `agent/Prompts/02_Prompt_Writer.md` for prompt writing guidelines.
For architecture issues, also read `agent/Prompts/01_Workflow_Architect.md` for design guidelines.
For structural issues, also read `agent/Prompts/03_Quality_Reviewer.md` for the full structural checklist.

Follow the Workflow Fixer's Expected Workflow: diagnose, plan, get approval, fix, verify.
