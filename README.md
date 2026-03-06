# Agent Forge

Independent agents that can operate on any task, no matter how complex.

Agent Forge gives AI agents the ability to think through problems (forge) and interact with the real world (computer use). Each module works on its own or together with the others.

## Modules

### [forge/](forge/) - Workflow Generation Engine

Designs and generates complete agentic workflow projects through a 7-step conversational process. Agent-agnostic: works with any AI coding agent that can read files and follow instructions.

```
Read forge/agentic.md and start
```

### [computer_use/](computer_use/) - Desktop Automation Engine

Captures screenshots, locates UI elements, and executes mouse/keyboard actions. Works as a Python library, MCP server, or CLI tool.

```python
from computer_use import ComputerUseEngine
engine = ComputerUseEngine()
engine.click(500, 300)
```

### paper/ - Research Paper

Academic paper documenting the framework.

## Quick Start

Point your AI coding agent at the orchestrator:

```
Read forge/agentic.md and start
```

For agents with slash commands (e.g., Claude Code), wrappers are available in `.claude/commands/`:

```
/create-workflow           # Full workflow from scratch
```

## Structure

```
Agent-Forge/
├── forge/                 # Workflow generation engine (standalone)
│   ├── agentic.md         # 7-step orchestrator
│   ├── Prompts/           # Specialized agent prompts
│   ├── patterns/          # 10 reusable workflow patterns
│   ├── examples/          # 3 example workflows
│   └── utils/scaffold/    # Templates for generated projects
├── computer_use/          # Desktop automation engine (standalone)
│   ├── core/              # Engine facade, types, actions
│   ├── platform/          # OS backends (Linux, Windows, macOS, WSL2)
│   └── mcp_server.py      # MCP server
├── paper/                 # Research paper
├── .claude/commands/      # Claude Code wrappers (thin, no logic)
└── output/                # Generated workflow projects
```

## Contributing

1. Create a branch from `master`:
   ```bash
   git checkout master && git checkout -b feature/your-change
   ```
2. Make your changes and commit:
   ```bash
   git add . && git commit -m "your message"
   ```
3. Push and open a PR into `master`:
   ```bash
   git push -u origin feature/your-change
   ```
