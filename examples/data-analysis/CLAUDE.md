# Data Analysis Pipeline

## Project Structure

```
data-analysis/
├── README.md                          # Entry point
├── CLAUDE.md                          # This file, project rules
├── agentic.md                         # 6-step orchestrator
├── .claude/
│   └── commands/                      # 7 slash commands (one per step + master)
│       ├── start-analysis.md
│       ├── discover-data.md
│       ├── profile-data.md
│       ├── design-analysis.md
│       ├── run-analysis.md
│       ├── generate-report.md
│       └── review-delivery.md
├── agent/                             # Core engine
│   ├── Prompts/                       # 3 specialized agent prompts
│   │   ├── 01_Data_Profiler.md
│   │   ├── 02_Analysis_Architect.md
│   │   └── 03_Report_Writer.md
│   ├── scripts/                       # Python tooling
│   │   ├── src/
│   │   ├── tests/
│   │   ├── README.md
│   │   ├── requirements.txt
│   │   ├── profile_data.py
│   │   └── generate_report.py
│   └── utils/
│       ├── analysis-template/         # Copied per task, never modified
│       │   ├── analysis.py
│       │   └── requirements.txt
│       ├── code/
│       └── docs/
└── tasks/                             # Output organized by date
```

## How to Use

Start the full workflow:
```
/start-analysis
```

Or run individual steps:
```
/discover-data           # Step 1: Discover and validate the dataset
/profile-data            # Step 2: Run profiling script, present summary stats
/design-analysis         # Step 3: Design analysis approach and visualizations
/run-analysis            # Step 4: Generate and execute analysis scripts
/generate-report         # Step 5: Compile results into a markdown report
/review-delivery         # Step 6: Final review and delivery
```

## Key Rules

- Always read `agentic.md` fully before starting any step
- Never skip approval gates (marked with pause)
- Scripts require a Python venv: `python3 -m venv agent/scripts/.venv && source agent/scripts/.venv/bin/activate && pip install -r agent/scripts/requirements.txt`
- All analysis code uses `agent/utils/analysis-template/` as base. Copy per task, never modify the original
- Tasks organized by date: `tasks/YYYY-MM-DD/TASK_ID/`
- Always wait for user approval before saving
- No emojis in generated content
- No "Co-Authored-By" or AI attribution in generated content

## Naming Conventions

- Slash commands: `kebab-case` (e.g., `start-analysis.md`)
- Agent prompts in `agent/Prompts/`: zero-padded with underscores (e.g., `01_Data_Profiler.md`)
- Task folders: `tasks/YYYY-MM-DD/{descriptive-id}/`
- Output files within tasks follow the numbered naming pattern (e.g., `01_dataset_info.md`)
