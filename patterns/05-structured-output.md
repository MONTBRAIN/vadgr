# Pattern 05: Structured Output

## What

Predictable, numbered output folders and files that make artifacts easy to find, navigate, and reference. Every workflow execution produces the same folder structure.

## When to Use

Any workflow that produces multiple artifacts across steps (documents, code, evaluations, etc.).

## Structure

```
output/
├── {task-id}/
│   ├── 01_prompt.md
│   ├── 02_rubrics.md
│   ├── 03_evaluation.md
│   └── artifacts/
│       ├── 1. {Item}/
│       └── 2. {Item}/
```

Or date-organized:
```
output/
├── 2026-02-14/
│   ├── 001/
│   │   ├── 01_prompt.md
│   │   └── ...
│   └── 002/
│       └── ...
```

## Naming Conventions

| Convention | Example | When to Use |
|------------|---------|-------------|
| Numbered prefix | `01_prompt.md` | Sequential step outputs |
| Numbered + Name | `01_Research_Analyst.md` | Agent prompts, lessons, topics |
| Date + ID | `2026-02-14/001/` | Task-level organization |
| TASK_INFO.md | `TASK_INFO.md` | Progress tracking per task |

## Key Conventions

1. Use consistent numbering (zero-padded for sorting: `01`, `02`, `03`)
2. Step outputs map to numbered files (Step 1 → `01_*.md`)
3. Include a progress tracker file (`TASK_INFO.md`) with checkboxes for each step
4. Output structure must be documented in `agentic.md`
5. Create directories upfront with `.gitkeep` files
