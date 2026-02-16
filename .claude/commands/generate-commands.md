---
description: Generate .claude/commands/ slash commands for the new workflow (Step 5).
argument-hint: [workflow-name]
---

Read `agent/agentic.md` for context.
Read `agent/utils/scaffold/command.md.template` for the command template.

Execute **Step 5: Generate CLI Commands** for workflow "$ARGUMENTS".

Create one command per workflow step plus a master start command.
Additionally, include the standard fix command from `agent/utils/scaffold/fix.md.template` in the generated workflow's `.claude/commands/fix.md`, and copy `agent/utils/scaffold/00_Workflow_Fixer.md.template` to the generated workflow's `agent/Prompts/00_Workflow_Fixer.md`.
