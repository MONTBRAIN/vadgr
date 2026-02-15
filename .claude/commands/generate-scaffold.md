---
description: Generate README.md, CLAUDE.md, and project skeleton for the new workflow (Step 6).
argument-hint: [workflow-name]
---

Read `agent/agentic.md` for context.
Read `agent/utils/scaffold/README.md.template` and `agent/utils/scaffold/CLAUDE.md.template`.

Execute **Step 6: Generate Project Scaffold** for workflow "$ARGUMENTS".

Generate the complete project skeleton. Every workflow MUST include:
- README.md (entry point)
- CLAUDE.md (project rules, structure, naming conventions)
- agent/ directory containing:
  - agent/Prompts/ (already created in Step 4)
  - agent/scripts/ with src/, tests/, requirements.txt (Python deps, empty if none), and README.md (with venv setup instructions)
  - agent/utils/ with code/ and docs/ (with .gitkeep files)
- Output directories referenced in the architecture (with .gitkeep files)
- Templates (if the workflow uses the template-scaffold pattern)

Present complete file listing and wait for approval.
