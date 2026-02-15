# Agent, Agent Forge Core Engine

This directory contains the core engine that powers Agent Forge.

## Contents

- `agentic.md`, the 7-step meta-workflow orchestrator. Read this to start.
- `Prompts/`, specialized agent prompts used by the orchestrator:
  - `01_Workflow_Architect.md`, designs workflow structures from requirements
  - `02_Prompt_Writer.md`, creates agent prompts following the canonical template
  - `03_Quality_Reviewer.md`, reviews generated workflows for completeness
- `scripts/`, automation scripts with `src/`, `tests/`, `README.md`, and `requirements.txt`
- `utils/scaffold/`, templates used when generating new workflow projects
- `utils/code/`, code utilities
- `utils/docs/`, documentation utilities

## How It Works

The orchestrator (`agentic.md`) coordinates 7 steps to create a new workflow:

1. Gather requirements from the user
2. Design the workflow architecture (using Prompt 1)
3. Generate the orchestrator file (using Prompt 2)
4. Generate specialized agent prompts (using Prompt 2)
5. Generate CLI commands
6. Generate the project scaffold
7. Review and deliver (using Prompt 3)

Each step is also accessible as a standalone slash command via `.claude/commands/`.
