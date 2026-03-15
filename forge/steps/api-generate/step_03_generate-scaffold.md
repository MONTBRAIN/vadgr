# Step 3: Generate Project Scaffold

**Purpose:** Create the full project skeleton deterministically before any content generation begins.

**Prompt:** None (orchestrator handles this directly using scaffold scripts)

---

## Inputs

- Parsed input from Step 1
- Architecture design from Step 2

---

## Workflow

1. Call the scaffold CLI to create the project deterministically:

```bash
python3 -m forge.scripts.src.scaffold generate \
  --config '{"workflow_name":"{name}","workflow_description":"{description}","folder_name":"{folder_name}","steps":[{"number":1,"name":"Step Name","command":"step-name"}],"agents":[{"number":2,"name":"Agent_Name"}],"computer_use":false}' \
  --base-dir output
```

Or pass the config from a JSON file:

```bash
python3 -m forge.scripts.src.scaffold generate --config scaffold_config.json --base-dir output
```

The command outputs JSON to stdout including the `root` path for subsequent steps.

For programmatic use (when calling from Python rather than a shell), the Python
import approach is still available:

```python
from forge.scripts.src.scaffold import generate_scaffold, ScaffoldConfig

config = ScaffoldConfig(
    workflow_name="{name}",
    workflow_description="{description}",
    folder_name="{folder_name}",
    steps=[{"number": N, "name": "Step Name", "command": "step-name"}, ...],
    agents=[{"number": N, "name": "Agent_Name"}, ...],
    computer_use=True|False,
)
root = generate_scaffold(config, base_dir="output")
```

This creates the full project structure:
- README.md, CLAUDE.md
- `.claude/commands/` with start command, per-step commands, and fix command
- `agent/Prompts/` with standard prompts (00_Workflow_Fixer.md, 01_Senior_Prompt_Engineer.md)
- `agent/steps/` directory (empty, populated in Step 5)
- `agent/scripts/` with src/, tests/, requirements.txt, README.md, .venv/
- `agent/utils/` with code/ and docs/
- `output/` directory (at runtime the API creates `output/{run_id}/agent_outputs/` and `output/{run_id}/user_outputs/` per run)

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that scaffold was created with all directories and standard files
- The `root` path for subsequent steps to write into

### User Output (deliverables)

Save to: `output/{folder_name}/`
- Complete project skeleton: README.md, CLAUDE.md, .claude/commands/, agent/, output/

---

## Quality Check

- Scaffold CLI `generate` command ran successfully?
- All directories present?
- Standard prompts copied?
- Commands created?
- Venv created?
