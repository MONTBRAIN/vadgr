# API Update, Programmatic Agent Update

## Purpose

This file is the non-interactive entry point for updating an existing agent workflow.
The API calls this instead of `api-generate.md` when requirements change on an agent
that already has a generated folder at `forge_path`.

Invoke via:
```
claude -p "Read forge/api-update.md and update an existing agent from: {JSON}"
```

Where `{JSON}` is a JSON object conforming to the input format described below.

---

## Input Format

Accept a JSON object with the following fields:

```json
{
  "forge_path": "output/agent-name/",
  "original": {
    "name": "agent-name",
    "description": "Original description used when the agent was created.",
    "steps": [
      {"name": "Research sources", "computer_use": false},
      {"name": "Create PR", "computer_use": true}
    ],
    "samples": [],
    "computer_use": true
  },
  "updated": {
    "description": "New description reflecting changed requirements.",
    "steps": [
      {"name": "Research sources", "computer_use": false},
      {"name": "Write code", "computer_use": false},
      {"name": "Create PR", "computer_use": true}
    ],
    "samples": ["new sample"],
    "computer_use": true
  }
}
```

**Required:** `forge_path`, `original.name`, `updated` (at least one field inside it)

**Optional fields inside `updated`:** Any subset of `description`, `steps`, `samples`, `computer_use`.
Only include the fields that changed. Fields absent from `updated` are treated as unchanged.

**Steps format:** Steps are arrays of objects with `name` (string) and `computer_use` (boolean). Steps with `computer_use: true` need desktop automation. The agent-level `computer_use` is true if any step has `computer_use: true`.

**Validation:**
- If `forge_path` is missing or empty, write an error JSON to stdout and stop:
  `{"error": "forge_path is required"}`
- If `original.name` is missing or empty, write an error JSON to stdout and stop:
  `{"error": "original.name is required"}`
- If `updated` is missing or empty (no fields changed), write an error JSON to stdout and stop:
  `{"error": "updated must contain at least one changed field"}`
- If the directory at `forge_path` does not exist, write an error JSON to stdout and stop:
  `{"error": "forge_path does not exist: output/agent-name/"}`
- `samples` items may be strings (treated as content with no label) or objects with
  `content` and optional `label` fields.

---

## What This Orchestrator Does

This orchestrator reads an existing agent folder, computes what changed, and applies
targeted edits. It does not regenerate from scratch unless the change requires it.

1. Parse and validate input.
2. Read the existing workflow files at `forge_path`.
3. Classify the change as a patch or a full regeneration.
4. Apply the update: patch affected files, or regenerate if needed.
5. Print a structured JSON result to stdout.

**Skipped (non-interactive mode):**
- Interactive questions
- Approval gates and user confirmation prompts
- CLI command files (`.claude/commands/`)
- Project scaffold files (README.md, CLAUDE.md)
- Scripts and utils directories
- Quality review step

The output is the same JSON format as `api-generate.md`. The API handles both responses
identically.

---

## Step 1: Parse and Validate Input

**Step file:** `forge/steps/api-update/step_01_parse-validate.md`

Read the step file and execute it.

---

## Step 2: Read Existing Workflow Files

**Step file:** `forge/steps/api-update/step_02_read-existing.md`

Read the step file and execute it.

---

## Step 3: Classify the Change

**Step file:** `forge/steps/api-update/step_03_classify-change.md`

Read the step file and execute it.

---

## Step 4: Apply the Update

**Step file:** `forge/steps/api-update/step_04_apply-update.md`

Read the step file and execute it.

---

## Step 5: Write Output and Return JSON

**Step file:** `forge/steps/api-update/step_05_return-json.md`

Read the step file and execute it.

---

## Quality Standards

Updated agents must meet the same quality bar as agents created through `api-generate.md`.

**Patch quality:**
- Only files in the change set are touched.
- All required prompt sections remain present after the patch.
- Cross-references between `agentic.md`, step files, and prompt files are intact after the patch.
- Existing customizations in unaffected sections are preserved exactly.
- Step files updated if they exist (new format support).

**Regeneration quality:**
- All standards from `api-generate.md` Quality Standards apply.
- The agent name and `forge_path` are preserved. The folder is not renamed.
- Regenerated files use the new step file architecture.

**Self-containment (both modes):**
- The updated agent folder must work without Agent Forge installed.
- No references to `forge/`, `forge/patterns/`, or `forge/examples/` inside the
  generated files.

---

## Clarifications

### Backward Compatibility

The update orchestrator handles both old (monolithic agentic.md) and new (thin orchestrator + step files) formats:
- **Old format detected:** `agent/steps/` directory does not exist. Patch edits go directly into `agentic.md` and prompt files.
- **New format detected:** `agent/steps/` directory exists. Patch edits go into step files and prompt files. The thin orchestrator is only updated if step references change.
- **Regeneration always produces new format:** Even if the original agent used the old format, regeneration creates the new step file architecture.

### Patch vs Regeneration Decision Examples

**Patch (description change, same complexity):**

Original: "Summarize customer support tickets into bullet points."
Updated: "Summarize customer support tickets into bullet points, grouping related
issues by category and flagging urgent ones."

The task is still a single-step summarization. Patch the Context, Quality Requirements, and Expected Workflow sections.

**Regenerate (description change, complexity shift):**

Original: "Summarize customer support tickets into bullet points."
Updated: "Analyze customer support tickets, identify root causes, and produce a
weekly trend report with recommendations for the support team."

The updated description implies three distinct phases. Regenerate.

**Patch (computer_use added):**

The workflow logic does not change. Add the Computer Use Agent prompt and the
configuration section. All other files stay the same.

### Preserving Existing Customizations

When patching, treat each prompt section as independently owned. A section that is
not driven by a changed field must not be modified. The minimal fix principle applies.

### Deriving Input and Output Schema After an Update

After a patch, re-derive the `input_schema` and `output_schema` from the updated
description. Do not copy the original schema forward if the description changed.

### Naming Conventions

Follow the same conventions as `api-generate.md`:
- Agent folder: kebab-case, matches `original.name`. Never rename the folder.
- Prompt files: zero-padded with underscores (`02_Research_Analyst.md`).
- Step files: `step_{NN}_{step-name}.md`.
- Step names in `agentic.md`: Title Case.

---

## Actual Input

**UPDATE REQUEST:**
```json
{
  "forge_path": "[Path to the existing agent folder, e.g., output/ticket-summarizer/]",
  "original": {
    "name": "[Agent name in kebab-case, e.g., ticket-summarizer]",
    "description": "[Original description used when the agent was created]",
    "samples": [],
    "computer_use": false
  },
  "updated": {
    "description": "[New description reflecting changed requirements, if changed]",
    "samples": ["[New sample content, if samples changed]"],
    "computer_use": true
  }
}
```

---

## Expected Workflow

1. Read the JSON input provided after "update an existing agent from:".
2. Validate all required fields. If any validation fails, print the error JSON and stop.
3. Build the change set: list the fields that differ between `original` and `updated`.
4. Read `{forge_path}/agentic.md`, all prompt files, and all step files (if they exist).
5. Classify the change as patch or regeneration using the rules in Step 3.
6. If patch: identify the specific files and sections affected by each changed field.
7. If patch: apply targeted edits to each affected file. Leave unaffected files untouched.
8. If regenerate: run the full generation process using updated fields. Produce new step file architecture.
9. Run a consistency pass: verify cross-references between agentic.md, step files, and prompt files.
10. Derive the `input_schema` and `output_schema` from the updated description.
11. Print the output JSON to stdout. No other output.
