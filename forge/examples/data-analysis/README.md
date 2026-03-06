# Data Analysis Pipeline

Workflow for automated data analysis, from dataset discovery to final report generation.

## Usage

Point your AI coding agent at the orchestrator:

```
Read agentic.md and start
```

For agents with slash commands:

```
/start-analysis            # Full workflow from scratch
```

Individual steps:

| Command | Step | Description |
|---------|------|-------------|
| `/start-analysis` | All | Full workflow: runs Steps 1-6 |
| `/discover-data` | 01 | Discover and validate the dataset |
| `/profile-data` | 02 | Run profiling script, present summary stats |
| `/design-analysis` | 03 | Design analysis approach and visualizations |
| `/run-analysis` | 04 | Generate and execute analysis scripts |
| `/generate-report` | 05 | Compile results into a markdown report |
| `/review-delivery` | 06 | Final review and delivery |
| `/fix [problem]` | -- | Diagnose and fix workflow issues |
