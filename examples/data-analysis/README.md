# Data Analysis Pipeline

Workflow for automated data analysis, from dataset discovery to final report generation.

### Claude Code (recommended)

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

### Other AI tools (Cursor, Windsurf, etc.)

```bash
# Point the tool at agentic.md:
# "Read agentic.md and start"
```
