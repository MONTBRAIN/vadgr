# Pattern 09: Fix Command

## What

A built-in diagnostic and repair command that every workflow includes by default. It can triage issues from vague complaints to exact instructions, diagnose root causes, and apply targeted fixes to the workflow's own files.

## When to Use

Every workflow should include a `/fix` command. Workflows without self-repair capability require the user to manually trace and fix issues, which defeats the purpose of orchestration.

## How It Works

The fix command follows a **three-tier input protocol**:

1. **Exact instructions** ("add a gate to Step 3"). Apply the fix directly.
2. **Error logs or conversation output** (pasted failed run). Parse signals, trace to source files, fix.
3. **Vague complaints** ("the prompts are weak"). Run diagnostic checklist, identify root causes, present diagnosis, get approval, then fix.

In all tiers, the fix command reads the entire workflow before acting. It understands the system it is repairing by reading agentic.md, all prompts, all commands, CLAUDE.md, and README.md. This "understand first, fix second" approach prevents fixes that solve one problem while creating another.

## Key Principles

1. **Minimal fix.** Apply the smallest change that resolves the issue. No drive-by improvements.
2. **Cross-reference safety.** After any rename or restructure, verify all references across the project.
3. **Diagnosis before action.** For vague complaints, always present the diagnosis and plan before applying changes.
4. **Verification after action.** After applying fixes, re-check that modified files are internally consistent and cross-references are intact.

## Structure

The fix command is a `.claude/commands/fix.md` file. It is NOT a step in the workflow's main sequence. It is a utility command, always available, invoked on demand.

Both Agent Forge and generated workflows use a dedicated agent prompt (`agent/Prompts/00_Workflow_Fixer.md`) with diagnostic methodology. The command file is thin: it reads `agentic.md` for context and the fixer prompt for methodology.

## Self-Similar Application

| Agent Forge | Generated Workflows |
|---|---|
| `.claude/commands/fix.md` (thin, reads agent prompt) | `.claude/commands/fix.md` (thin, reads agent prompt) |
| `agent/Prompts/00_Workflow_Fixer.md` (dedicated agent) | `agent/Prompts/00_Workflow_Fixer.md` (copied from template) |
| Can invoke Prompt Writer, Architect, Quality Reviewer | Reads own agents for domain context |

## Anti-Patterns

- **Fix everything at once.** The fix command repairs diagnosed issues, not rewrite the entire workflow. If the user wants a redesign, that is a new `/create-workflow` task.
- **Fix without reading.** Never modify a file without reading it first. The fix command must understand the current state before changing it.
- **Add features as fixes.** Adding new steps, new agents, or new commands is a feature, not a fix. The fix command repairs existing structure.
