# Agent Forge

Agent Forge is an agent-agnostic meta-framework for creating agentic workflows. It IS itself an agentic workflow.

## Project Structure

```
Agent-Forge/
├── README.md                          # Entry point
├── CLAUDE.md                          # This file, project rules
├── .claude/
│   ├── commands/                      # Claude Code wrappers (thin, no logic)
│   └── agents/
│       └── senior-prompt-engineer.md  # Reusable prompt engineering agent
├── forge/                             # Workflow generation engine (standalone)
│   ├── agentic.md                     # Thin orchestrator (step order + gates)
│   ├── api-generate.md                # API non-interactive generation entry point
│   ├── api-update.md                  # API non-interactive update entry point
│   ├── README.md                      # Module docs
│   ├── steps/                         # All step files, organized by mode
│   │   ├── interactive/               # Standalone interactive workflow (7 steps)
│   │   ├── api-generate/              # API-driven generation (7 steps)
│   │   └── api-update/                # API-driven updates (5 steps)
│   ├── Prompts/                       # 5 specialized agents + fixer
│   │   ├── 00_Workflow_Fixer.md
│   │   ├── 01_Senior_Prompt_Engineer.md
│   │   ├── 02_Workflow_Architect.md
│   │   ├── 03_Prompt_Writer.md
│   │   ├── 04_Quality_Reviewer.md
│   │   └── 05_Computer_Use_Agent.md
│   ├── patterns/                      # 10 documented workflow patterns
│   ├── examples/                      # 3 example workflows
│   │   ├── research-paper/
│   │   ├── project-scaffold/
│   │   └── data-analysis/
│   ├── scripts/                       # Automation scripts
│   │   ├── src/
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   └── README.md
│   └── utils/
│       ├── scaffold/                  # Templates for generated projects
│       ├── code/                      # Code utilities
│       └── docs/                      # Documentation utilities
├── computer_use/                      # Desktop automation engine (standalone)
│   ├── README.md                      # Module docs
│   ├── core/                          # Engine facade, types, ABCs, autonomous loop
│   ├── platform/                      # OS backends (WSL2, Linux, Windows, macOS)
│   ├── grounding/                     # UI element location (accessibility + vision)
│   ├── providers/                     # LLM adapters (Anthropic, OpenAI)
│   └── tests/                         # Unit tests
├── registry/                          # Agent package manager (standalone)
│   ├── cli.py                         # Click CLI (pack, pull, push, search, agents)
│   ├── manifest.py                    # .agnt manifest schema + validation
│   ├── packer.py                      # Pack/unpack agent folders to .agnt archives
│   ├── installer.py                   # Install/uninstall agents locally
│   ├── registry_client.py             # High-level registry operations
│   ├── config.py                      # Registry config (~/.forge/registry.yaml)
│   ├── adapters/                      # Registry backend adapters
│   │   ├── github.py                  # GitHub Releases adapter
│   │   ├── http.py                    # Generic HTTP server adapter
│   │   └── local.py                   # Local folder adapter
│   └── tests/                         # Unit tests (96 tests)
├── paper/                             # Research paper
└── output/                            # Generated workflows land here
```

## How to Use

Point your AI coding agent at the orchestrator:
```
Read forge/agentic.md and start
```

For Claude Code, slash commands are available:
```
/create-workflow              # Full workflow: runs Steps 1-7
/gather-requirements          # Step 1: Interview the user
/design-architecture          # Step 2: Design workflow structure
/generate-scaffold            # Step 3: Generate project skeleton
/generate-orchestrator        # Step 4: Generate agentic.md
/generate-agents              # Step 5: Generate agent prompts + step files
/generate-scripts             # Step 6: Generate workflow scripts
/review-workflow              # Step 7: Self-review and deliver
/fix [problem-or-path]        # Diagnose and fix issues in any workflow
/execute-workflow [path]      # Execute a workflow via computer use
/create-and-run [task]        # Generate workflow + execute immediately
/pause-execution              # Pause computer use mid-execution
/resume-execution             # Resume paused execution
```

Registry CLI commands (via `forge` or `python -m registry`):
```
forge pack ./my-agent/        # Package agent folder into .agnt archive
forge pull agent-name         # Download + install agent from registry
forge push my-agent.agnt      # Publish .agnt to a registry
forge search "data analysis"  # Search registries for agents
forge agents                  # List locally installed agents
```

## Key Rules

- Always read `forge/agentic.md` fully before starting any step
- Read the step file referenced by each step before executing it
- Never skip approval gates (marked with ⏸)
- Always use `forge/utils/scaffold/` templates as the base for generated files. Do not create from scratch.
- Generated workflows go into `output/{workflow-name}/`
- Every generated workflow must include: README.md, agentic.md, step files in `agent/steps/`, at least one agent prompt, at least one slash command
- Generated agents use thin orchestrator + step files pattern (see Step File Architecture below)
- Follow the patterns documented in `forge/patterns/` for consistency
- Reference examples in `forge/examples/` when the user needs inspiration
- No emojis in generated content
- No "Co-Authored-By" or AI attribution in generated content
- Generate mode must NEVER depend on `computer_use/`. Delete that directory and generate-only workflows keep working.

## Step File Architecture

Generated workflows use a thin orchestrator + step files pattern:
- `agentic.md` contains step order, pause/approval gates, and references to step files
- `agent/steps/step_{NN}_{step-name}.md` contains the full execution spec for each step
- Each step file defines: prompt reference, inputs, workflow actions, and required outputs
- Agent outputs (inter-step context): `output/agent_outputs/step_{NN}_agent_output.md`
- User outputs (deliverables): `output/user_outputs/step_{NN}/`

This same pattern applies to forge itself:
- `forge/steps/interactive/` -- step files for the standalone interactive workflow
- `forge/steps/api-generate/` -- step files for API-driven generation
- `forge/steps/api-update/` -- step files for API-driven updates

## Naming Conventions

- Slash commands: `kebab-case` (e.g., `create-workflow.md`)
- Agent prompts in `Prompts/`: zero-padded with underscores (e.g., `01_Agent_Name.md`)
- Step files: `step_{NN}_{step-name}.md` (e.g., `step_01_gather-requirements.md`)
- Template placeholders: `{{PLACEHOLDER_NAME}}` (double curly braces, UPPER_SNAKE_CASE)
- Output folders: `kebab-case` for workflow names

## Quality Bar

Every generated workflow must be:
- Self-contained (runnable without Agent Forge)
- Complete (orchestrator + agents + commands + README)
- Consistent (follows the same patterns Agent Forge uses)
