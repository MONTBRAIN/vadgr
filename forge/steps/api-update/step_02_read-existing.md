# Step 2: Read Existing Workflow Files

**Purpose:** Read the current state of the agent's workflow files to understand what exists.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- Parsed input from Step 1 (specifically `forge_path`)

---

## Workflow

1. Read `{forge_path}/agentic.md`. This is required. If it does not exist, stop:
   ```json
   {"error": "agentic.md not found at forge_path"}
   ```

2. List all files under `{forge_path}/agent/Prompts/`. Read each one.
   If the directory does not exist or is empty, note this. It is not a hard error,
   but it means there are no prompts to patch.

3. Check if `{forge_path}/agent/steps/` exists. If it does, read all step files.
   If it does not exist, the agent uses the old monolithic format (no step files).

**While reading, note:**
- How many steps the orchestrator has.
- Which agent prompts exist and what their numbered names are.
- Whether step files exist (new format) or not (old format).
- Whether `computer_use` is already configured (look for a Computer Use Configuration
  section in `agentic.md` or a `05_Computer_Use_Agent.md` prompt file).
- The current complexity: `simple` (1 step, 1 prompt) or `multi_step` (2+ steps).

**Hold the file contents in context.**

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- File contents of existing workflow files
- Structural notes: step count, prompt list, format (old/new), computer_use state, complexity

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- agentic.md read successfully?
- All prompts read?
- Step files checked for existence?
- Format detection (old vs new) noted?
