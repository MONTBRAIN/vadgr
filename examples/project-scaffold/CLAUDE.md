# Project Scaffolding Workflow

## Project Structure

```
project-scaffold/
├── README.md                          # Entry point
├── CLAUDE.md                          # This file, project rules
├── agentic.md                         # 4-step orchestrator
├── .claude/
│   └── commands/                      # 5 slash commands (one per step + master)
│       ├── start-project.md
│       ├── define-requirements.md
│       ├── design-architecture.md
│       ├── generate-code.md
│       └── validate-project.md
├── agent/                             # Core engine
│   ├── Prompts/                       # 2 specialized agent prompts
│   │   ├── 01_Software_Architect.md
│   │   └── 02_Code_Generator.md
│   ├── scripts/                       # Utility scripts
│   │   ├── src/
│   │   ├── tests/
│   │   ├── requirements.txt           # Python dependencies
│   │   └── README.md
│   └── utils/
│       ├── code/
│       └── docs/
├── templates/
│   └── project-template/              # Base template for generated projects
│       └── README.md
└── output/                            # Generated projects land here
```

## How to Use

Start the full workflow:
```
/start-project
```

Or run individual steps:
```
/define-requirements          # Step 1: Gather project requirements
/design-architecture          # Step 2: Design project structure
/generate-code                # Step 3: Generate starter code files
/validate-project             # Step 4: Validate and deliver
```

## Key Rules

- Always read `agentic.md` fully before starting any step
- Never skip approval gates (marked with pause)
- No actual code execution during generation. Only file creation
- All generated code uses the template in `templates/project-template/` as base
- Follow established conventions for the chosen language/framework
- Scripts require a Python venv: `python3 -m venv agent/scripts/.venv && source agent/scripts/.venv/bin/activate && pip install -r agent/scripts/requirements.txt`
- No external dependencies beyond what the template provides
- Generated projects go into `output/{project-name}/`
- Every generated project must include: README.md, src/ directory, tests/ directory, config files, .gitignore

## Naming Conventions

- Slash commands: `kebab-case` (e.g., `start-project.md`)
- Agent prompts in `Prompts/`: zero-padded with underscores (e.g., `01_Software_Architect.md`)
- Template placeholders: `{{PLACEHOLDER_NAME}}` (double curly braces, UPPER_SNAKE_CASE)
- Output folders: `kebab-case` for project names
