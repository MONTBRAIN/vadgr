# Forge - Workflow Generation Engine

Designs and generates complete agentic workflow projects from a conversational interview.

This module is **standalone** and works independently without `computer_use/`. It is **agent-agnostic**: works with any AI coding agent that can read files and follow instructions. Current supported agents: **Claude Code**, **OpenCode**.

## What It Does

Takes a user's description of what they want to automate and produces a complete, self-contained workflow project:

- `agentic.md` orchestrator (step-by-step instructions)
- Specialized agent prompts (`agent/Prompts/`)
- CLI commands (one per step)
- Project scaffold (README, rules, scripts, utilities)

## How It Works

A 7-step generation process defined in `agentic.md`:

| Step | Name | Description |
|------|------|-------------|
| 01 | Gather Requirements | Interview the user about their workflow needs |
| 02 | Design Architecture | Design steps, agents, and approval gates |
| 03 | Generate Scaffold | Create project skeleton, README, CLAUDE.md, commands, venv |
| 04 | Generate Orchestrator | Create the workflow's `agentic.md` with step file references |
| 05 | Generate Agents | Create specialized agent prompts and step definition files |
| 06 | Generate Scripts | Create workflow-specific scripts (if needed) |
| 07 | Review & Deliver | Self-review for completeness and quality |

### Three Modes

- **Interactive** (`agentic.md`): Full 7-step flow with user interview and approval gates. Step files in `steps/interactive/`.
- **API Generate** (`api-generate.md`): Non-interactive generation from structured JSON input. Step files in `steps/api-generate/`.
- **API Update** (`api-update.md`): Non-interactive update of existing agents. Step files in `steps/api-update/`.

## Usage

### With any AI coding agent

Point your agent at the orchestrator:

```
Read forge/agentic.md and start
```

This works with **Claude Code**, **OpenCode**, or any AI coding agent that can read files and follow instructions.

### Agent-specific wrappers

For agents that support slash commands (e.g., Claude Code), thin wrappers live in `.claude/commands/` at the repo root. These contain no logic, they just point to `agentic.md` and the relevant prompt.

## Key Files

| File | Purpose |
|------|---------|
| `agentic.md` | Interactive 7-step orchestrator (source of truth) |
| `api-generate.md` | Non-interactive generation orchestrator |
| `api-update.md` | Non-interactive update orchestrator |
| `steps/` | Step files organized by mode (`interactive/`, `api-generate/`, `api-update/`) |
| `Prompts/` | 6 specialized agent prompts |
| `utils/scaffold/` | Templates for generated projects |
| `patterns/` | 10 documented workflow patterns |
| `examples/` | 3 example workflows |
| `scripts/` | Python automation utilities |

## Patterns

The `patterns/` directory documents 10 reusable architectural patterns used across all generated workflows:

01. Orchestrator - central `agentic.md` coordination
02. Specialized Agents - role-based expertise separation
03. Approval Gates - human review checkpoints
04. Quality Loops - iterative refinement
05. Structured Output - predictable artifact organization
06. CLI Commands - step-wise execution
07. Template Scaffold - fresh-start project structures
08. Self-Similar Architecture - generated workflows mirror this framework
09. Fix Command - built-in diagnostic/repair
10. Computer Use - desktop automation

## Examples

Three complete, runnable example workflows in `examples/`:

- **data-analysis/** - data pipeline with profiling and reporting
- **research-paper/** - academic writing with source verification
- **project-scaffold/** - code project generation
