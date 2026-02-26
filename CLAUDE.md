# Agent Forge

Agent Forge is a meta-framework for creating agentic workflows. It IS itself an agentic workflow.

## Project Structure

```
Agent-Forge/
├── README.md                          # Entry point
├── CLAUDE.md                          # This file, project rules
├── .claude/
│   ├── commands/                      # 13 slash commands (steps + master + fix + execution)
│   └── agents/
│       └── senior-prompt-engineer.md  # Reusable prompt engineering agent
├── agent/                             # The BRAIN (orchestrator, prompts, patterns)
│   ├── agentic.md                     # 7-step meta-orchestrator
│   ├── README.md                      # Usage instructions
│   ├── Prompts/                       # 5 specialized agents + fixer
│   │   ├── 00_Workflow_Fixer.md
│   │   ├── 01_Senior_Prompt_Engineer.md
│   │   ├── 02_Workflow_Architect.md
│   │   ├── 03_Prompt_Writer.md
│   │   ├── 04_Quality_Reviewer.md
│   │   └── 05_Computer_Use_Agent.md
│   ├── scripts/                       # Automation scripts
│   │   ├── src/
│   │   ├── tests/
│   │   ├── requirements.txt           # Python dependencies
│   │   └── README.md
│   └── utils/
│       ├── scaffold/                  # Templates for generated projects
│       ├── code/                      # Code utilities
│       └── docs/                      # Documentation utilities
├── computer_use/                      # The EYES and HANDS (desktop automation engine)
│   ├── core/                          # Engine facade, types, ABCs, autonomous loop
│   ├── platform/                      # OS backends (WSL2, Linux, Windows, macOS)
│   ├── grounding/                     # UI element location (accessibility + vision)
│   ├── providers/                     # LLM adapters (Anthropic, OpenAI)
│   └── tests/                         # Unit tests
├── patterns/                          # 10 documented workflow patterns
├── examples/                          # 3 example workflows
│   ├── research-paper/
│   ├── project-scaffold/
│   └── data-analysis/
└── output/                            # Generated workflows land here
```

## How to Use

Start the full workflow:
```
/create-workflow
```

Or run individual steps:
```
/gather-requirements          # Step 1: Interview the user
/design-architecture          # Step 2: Design workflow structure
/generate-orchestrator        # Step 3: Generate agentic.md
/generate-agents              # Step 4: Generate agent prompts
/generate-commands            # Step 5: Generate slash commands
/generate-scaffold            # Step 6: Generate project skeleton
/review-workflow              # Step 7: Self-review and deliver
/fix [problem-or-path]        # Diagnose and fix issues in any workflow
/execute-workflow [path]      # Execute a workflow via computer use
/create-and-run [task]        # Generate workflow + execute immediately
/pause-execution              # Pause computer use mid-execution
/resume-execution             # Resume paused execution
```

## Key Rules

- Always read `agent/agentic.md` fully before starting any step
- Never skip approval gates (marked with ⏸)
- Always use `agent/utils/scaffold/` templates as the base for generated files. Do not create from scratch.
- Generated workflows go into `output/{workflow-name}/`
- Every generated workflow must include: README.md, agentic.md, at least one agent prompt, at least one slash command
- Follow the patterns documented in `patterns/` for consistency
- Reference examples in `examples/` when the user needs inspiration
- No emojis in generated content
- No "Co-Authored-By" or AI attribution in generated content
- Generate mode must NEVER depend on `computer_use/`. Delete that directory and generate-only workflows keep working.

## Naming Conventions

- Slash commands: `kebab-case` (e.g., `create-workflow.md`)
- Agent prompts in `Prompts/`: zero-padded with underscores (e.g., `01_Agent_Name.md`)
- Template placeholders: `{{PLACEHOLDER_NAME}}` (double curly braces, UPPER_SNAKE_CASE)
- Output folders: `kebab-case` for workflow names

## Quality Bar

Every generated workflow must be:
- Self-contained (runnable without Agent Forge)
- Complete (orchestrator + agents + commands + README)
- Consistent (follows the same patterns Agent Forge uses)
