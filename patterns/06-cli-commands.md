# Pattern 06: CLI Commands

## What

One `.claude/commands/` file per workflow step, plus a master start command. This enables both full sequential execution and targeted step re-runs.

## When to Use

Every workflow should have commands for each step. This is a baseline pattern.

## Structure

```
.claude/
└── commands/
    ├── start-{workflow}.md     # Master command (runs all steps)
    ├── step-1-name.md          # Individual step
    ├── step-2-name.md
    └── step-N-name.md
```

## Command Template

```markdown
---
description: {Short description of what this command does}
argument-hint: {Expected arguments, e.g., [task-id]}
---

Read `agent/agentic.md` to understand the full workflow context and rules.
Read `agent/Prompts/{NN}_{Agent_Name}.md` for guidance. <!-- if applicable -->

Execute **Step {N}: {Step Name}**{for task "$ARGUMENTS"}.

{Brief summary of what the step does, 3-5 lines}
```

## Key Conventions

1. **Filenames** use `kebab-case`: `generate-rubric.md`, `first-turn.md`
2. **YAML frontmatter** includes `description` and `argument-hint`
3. Every command **reads `agentic.md` first** for context
4. Commands reference the **specific step number and name**
5. The master command runs all steps sequentially with gate pauses
6. `$ARGUMENTS` captures user-provided arguments (task ID, workflow name, etc.)

## Benefits

- Users can re-run a single step without restarting the entire workflow
- Slash commands appear in Claude Code's autocomplete
- Each command is a focused entry point with clear scope
