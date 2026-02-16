# Agent Forge

A meta-framework that uses agentic workflows to create agentic workflows.

## agent/ - Workflow Engine

Orchestrator for designing and generating complete agentic workflow projects.

### Claude Code (recommended)

Run from the project root:

```bash
claude --dangerously-skip-permissions
```

Then use slash commands:

```
/create-workflow           # Full workflow from scratch
```

Individual steps:

| Command | Step | Description |
|---------|------|-------------|
| `/create-workflow` | All | Full workflow: runs Steps 1-7 sequentially |
| `/gather-requirements` | 01 | Interview the user about their workflow needs |
| `/design-architecture` | 02 | Design the workflow structure and agents |
| `/generate-orchestrator` | 03 | Generate the agentic.md for the new workflow |
| `/generate-agents` | 04 | Generate specialized agent prompts |
| `/generate-commands` | 05 | Generate .claude/commands/ for each step |
| `/generate-scaffold` | 06 | Generate README, CLAUDE.md, and project skeleton |
| `/review-workflow` | 07 | Self-review for completeness and quality |
| `/fix [problem]` | -- | Diagnose and fix workflow issues |

### Other AI tools (Cursor, Windsurf, etc.)

```bash
cd agent

# Point the tool at agentic.md:
# "Read agentic.md and start"
```

## Structure

- `agent/`, core engine (orchestrator, agents, utils)
- `patterns/`, documentation of reusable workflow patterns
- `examples/`, example workflows showing the architecture in action
- `output/`, where generated workflow projects land
