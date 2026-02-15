# Research Paper

## Project Structure

```
research-paper/
├── README.md                          # Entry point
├── CLAUDE.md                          # This file, project rules
├── agentic.md                         # 5-step orchestrator
├── .claude/
│   └── commands/                      # 5 slash commands (one per step + master)
│       ├── start-paper.md
│       ├── research-topic.md
│       ├── create-outline.md
│       ├── write-sections.md
│       └── review-paper.md
├── agent/
│   ├── Prompts/                       # 3 specialized agent prompts
│   │   ├── 01_Research_Analyst.md
│   │   ├── 02_Outline_Architect.md
│   │   └── 03_Academic_Writer.md
│   ├── scripts/                       # Python tooling
│   │   ├── src/
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   └── README.md
│   └── utils/
│       ├── code/
│       └── docs/
└── output/                            # Generated papers land here
```

## How to Use

Start the full workflow:
```
/start-paper
```

Or run individual steps:
```
/research-topic          # Step 2: Research sources and compile bibliography
/create-outline          # Step 3: Generate structured outline with thesis
/write-sections          # Step 4: Write each section sequentially
/review-paper            # Step 5: Final review and assembly
```

## Key Rules

- Always read `agentic.md` fully before starting any step
- Never skip approval gates (marked with pause)
- All generated papers go into `output/{paper-name}/`
- Always wait for user approval before saving or proceeding to the next step
- Scripts require a Python venv: `python3 -m venv agent/scripts/.venv && source agent/scripts/.venv/bin/activate && pip install -r agent/scripts/requirements.txt`
- No emojis in generated content
- No "Co-Authored-By" or AI attribution in generated content

## Naming Conventions

- Slash commands: `kebab-case` (e.g., `start-paper.md`)
- Agent prompts in `Prompts/`: zero-padded with underscores (e.g., `01_Research_Analyst.md`)
- Paper output folders: `output/{paper-name}/` using kebab-case
- Section files: numbered with name (e.g., `1. Introduction.md`)
