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
    "samples": [],
    "computer_use": false
  },
  "updated": {
    "description": "New description reflecting changed requirements.",
    "samples": ["new sample"],
    "computer_use": true
  }
}
```

**Required:** `forge_path`, `original.name`, `updated` (at least one field inside it)

**Optional fields inside `updated`:** Any subset of `description`, `samples`, `computer_use`.
Only include the fields that changed. Fields absent from `updated` are treated as unchanged.

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
  `content` and optional `label` fields. This matches the format used by `api-generate.md`.

---

## What This Orchestrator Does

This orchestrator reads an existing agent folder, computes what changed, and applies
targeted edits. It does not regenerate from scratch unless the change requires it.

1. Parse and validate input.
2. Read the existing workflow files at `forge_path`.
3. Diff the original fields against the updated fields.
4. Classify the change as a patch or a full regeneration.
5. Apply the update: patch affected files, or regenerate if needed.
6. Print a structured JSON result to stdout.

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

Read the JSON input provided after "update an existing agent from:".

Extract:
- `forge_path` (string, path to the existing agent folder)
- `original` (object with `name`, `description`, `samples`, `computer_use`)
- `updated` (object with any subset of `description`, `samples`, `computer_use`)

Run validation in this order:

1. If `forge_path` is missing or empty:
   ```json
   {"error": "forge_path is required"}
   ```
   Print this and stop.

2. If `original.name` is missing or empty:
   ```json
   {"error": "original.name is required"}
   ```
   Print this and stop.

3. If `updated` is missing or has no keys:
   ```json
   {"error": "updated must contain at least one changed field"}
   ```
   Print this and stop.

4. If the directory at `forge_path` does not exist on disk:
   ```json
   {"error": "forge_path does not exist: <value>"}
   ```
   Print this and stop.

Build a change set: a list of field names that differ between `original` and `updated`.
For each field in `updated`, compare its value to the same field in `original`.

**Comparison rules:**
- `description`: strings differ if they are not identical.
- `samples`: arrays differ if their length or any item content differs.
- `computer_use`: booleans differ if one is true and the other is false.

**Hold the parsed input and change set in context. Do not print anything to the user.**

---

## Step 2: Read Existing Workflow Files

Read every file in the existing agent folder at `forge_path`:

1. Read `{forge_path}/agentic.md`. This is required. If it does not exist, stop:
   ```json
   {"error": "agentic.md not found at forge_path"}
   ```

2. List all files under `{forge_path}/agent/Prompts/`. Read each one.
   If the directory does not exist or is empty, note this. It is not a hard error,
   but it means there are no prompts to patch.

**Hold the file contents in context.**

**While reading, note:**
- How many steps the orchestrator has.
- Which agent prompts exist and what their numbered names are.
- Whether `computer_use` is already configured (look for a Computer Use Configuration
  section in `agentic.md` or a `05_Computer_Use_Agent.md` prompt file).
- The current complexity: `simple` (1 step, 1 prompt) or `multi_step` (2+ steps).

---

## Step 3: Classify the Change

Use the change set from Step 1 and the existing workflow state from Step 2 to decide
whether to patch or fully regenerate.

### Patch (targeted edits to existing files)

Apply a patch when the change is additive or refinable within the current structure:

- Only `description` changed, and the new description implies the same number of steps
  and the same areas of expertise as the original.
- Only `samples` changed (new or updated calibration examples).
- `computer_use` changed from false to true, and the existing structure is otherwise
  valid (orchestrator and at least one prompt exist).
- `computer_use` changed from true to false.
- A combination of the above.

A description change is safe to patch when:
- The original and updated descriptions both imply the same complexity level
  (`simple` or `multi_step`).
- The core task is the same but the wording, scope, or domain has shifted moderately.
- No new phases of work appear that would require a new step or a new agent.

### Full Regeneration

Regenerate the entire agent folder (using the same approach as `api-generate.md`) when:

- The updated description implies a different complexity level than the original
  (e.g., a single-step task becomes a multi-step workflow, or a multi-step workflow
  collapses to a single step).
- The updated description introduces fundamentally different phases of work that
  require new agents not present in the current roster.
- The existing files are structurally broken: `agentic.md` is missing required sections,
  fewer than the expected number of prompt files exist, or cross-references are broken.

**When in doubt, patch.** A patch that is slightly too conservative is safer than a
regeneration that discards existing customizations. Only regenerate when the gap between
the original and updated requirements is large enough that patching would require
rewriting more than half of every affected file.

**Save in context:**
```
update_mode: patch | regenerate
change_set: [list of changed field names]
affected_files: [list of files that need changes]
```

---

## Step 4: Apply the Update

### If update_mode is patch

Apply targeted edits to each affected file. Do not touch files that are not affected
by the change set.

**Description changed:**

1. Read the existing agent prompt(s) in `{forge_path}/agent/Prompts/`.
2. Identify sections that are driven by the description: Context, Actual Input,
   Expected Workflow, and (if present) Quality Requirements.
3. Rewrite only those sections to reflect the updated description.
   Keep all other sections (Rules, Quality Examples, Clarifications) intact unless
   they directly contradict the new description.
4. In `agentic.md`, update the step purpose lines and any narrative text that
   references the original description. Do not change the step count or structure.

**Samples changed:**

Read the updated samples. For each sample:
- Identify the patterns, structure, tone, and level of detail that characterize it.
- Express these as updated Quality Requirements or Quality Examples in the relevant
  prompt(s).
- Do not copy the sample verbatim into the prompt. Derive the principles and express
  them as measurable criteria.

If samples were removed (present in `original.samples` but absent from `updated.samples`),
remove only the Quality Requirements and Quality Examples that were derived from
those specific samples. Keep any requirements that reflect general quality standards.

**`computer_use` changed from false to true:**

1. Read `forge/Prompts/05_Computer_Use_Agent.md`.
2. Generate a Computer Use Agent prompt adapted to the agent's description.
   Save it as `{forge_path}/agent/Prompts/05_Computer_Use_Agent.md`.
3. Add a Computer Use Configuration section to `{forge_path}/agentic.md`.
   Place it after the last step and before the Quality Checks table.

**`computer_use` changed from true to false:**

1. Delete `{forge_path}/agent/Prompts/05_Computer_Use_Agent.md` if it exists.
2. Remove the Computer Use Configuration section from `{forge_path}/agentic.md`.

**Multiple fields changed:**

Apply each change in the order listed above. After all changes are applied, do a
consistency pass: verify that cross-references between `agentic.md` and the prompt
files are intact.

### If update_mode is regenerate

Run the same process as `api-generate.md` Steps 2 through 4, using the updated fields
as the input. Use `original.name` as the agent name (do not rename the folder).

Write the new files to `{forge_path}`, overwriting the existing files. Do not create
scripts/, utils/, README.md, CLAUDE.md, or .claude/ directories.

---

## Step 5: Write Output and Return JSON

After all files are written, print a single JSON object to stdout. This is the only
output the API reads.

```json
{
  "forge_path": "output/{name}/",
  "forge_config": {
    "complexity": "simple | multi_step",
    "steps": 1,
    "prompts": ["01_Agent_Name.md"]
  },
  "input_schema": [
    { "name": "input_name", "type": "text", "required": true }
  ],
  "output_schema": [
    { "name": "output_name", "type": "text" }
  ]
}
```

This format is identical to the output of `api-generate.md`. The API handles both
responses the same way.

**Field definitions:**

- `forge_path`: The value from the input `forge_path` field, unchanged.
- `forge_config.complexity`: The complexity of the workflow after the update
  (`"simple"` or `"multi_step"`).
- `forge_config.steps`: Number of steps in `agentic.md` after the update.
- `forge_config.prompts`: List of prompt filenames in `agent/Prompts/` after the
  update, reflecting any additions or removals.
- `input_schema`: Inferred inputs the agent needs at runtime. Derive from the updated
  description. Each item has `name`, `type` (one of: `text`, `file`, `number`,
  `boolean`), and `required` (boolean).
- `output_schema`: Inferred outputs the agent produces. Derive from the updated
  description. Each item has `name` and `type`.

Print only this JSON object. No preamble, no summary, no explanation. The API parses
this directly.

---

## Quality Standards

Updated agents must meet the same quality bar as agents created through `api-generate.md`.

**Patch quality:**
- Only files in the change set are touched.
- All required prompt sections remain present after the patch (Context, Input/Output,
  Quality Requirements, Rules, Actual Input, Expected Workflow).
- Cross-references between `agentic.md` and prompt files are intact after the patch.
- Existing customizations in unaffected sections are preserved exactly.

**Regeneration quality:**
- All standards from `api-generate.md` Quality Standards apply.
- The agent name and `forge_path` are preserved. The folder is not renamed.

**Self-containment (both modes):**
- The updated agent folder must work without Agent Forge installed.
- No references to `forge/`, `forge/patterns/`, or `forge/examples/` inside the
  generated files.

---

## Clarifications

### Patch vs Regeneration Decision Examples

**Patch (description change, same complexity):**

Original: "Summarize customer support tickets into bullet points."
Updated: "Summarize customer support tickets into bullet points, grouping related
issues by category and flagging urgent ones."

The task is still a single-step summarization. The added requirements (grouping,
flagging) affect what the prompt must instruct the agent to do, not how many steps
or agents exist. Patch the Context, Quality Requirements, and Expected Workflow
sections of the existing prompt.

**Regenerate (description change, complexity shift):**

Original: "Summarize customer support tickets into bullet points."
Updated: "Analyze customer support tickets, identify root causes, and produce a
weekly trend report with recommendations for the support team."

The updated description implies three distinct phases (analyze, identify trends,
write recommendations) that each require different expertise. The original single-step
structure cannot accommodate this. Regenerate.

**Patch (computer_use added):**

Original `computer_use`: false
Updated `computer_use`: true

The workflow logic does not change. Add the Computer Use Agent prompt and the
configuration section in `agentic.md`. All other files stay the same.

**Patch (samples updated, nothing else):**

The agent description and structure are unchanged. New samples refine the quality
expectations. Update Quality Requirements and Quality Examples in the affected
prompt(s) to reflect what the new samples demonstrate. No structural changes.

### Preserving Existing Customizations

When patching, treat each prompt section as independently owned. A section that is
not driven by a changed field must not be modified, even if you think it could be
improved. The minimal fix principle applies: change only what the updated requirements
require.

If a section is both affected by the change and contains customizations that are still
valid, keep the customizations and add or modify only the parts that the change requires.

### Deriving Input and Output Schema After an Update

After a patch, re-derive the `input_schema` and `output_schema` from the updated
description. Do not copy the original schema forward if the description changed. The
schema reflects what the agent needs at runtime, which may shift even for moderate
description changes.

After a regeneration, the schema is derived fresh from the updated description,
following the same rules as `api-generate.md` Step 2.

### Naming Conventions

Follow the same conventions as `api-generate.md`:
- Agent folder: kebab-case, matches `original.name`. Never rename the folder.
- Prompt files: zero-padded with underscores (`01_Research_Analyst.md`).
- Step names in `agentic.md`: Title Case.
- Output files produced by the agent: lowercase with hyphens or numbered prefixes.

### Computer Use in Patch Mode

When adding computer use to an existing agent, adapt the Computer Use Agent prompt
to the specific desktop tasks described in the updated description. Do not use a
generic Computer Use prompt. Read `forge/Prompts/05_Computer_Use_Agent.md` for the
structural template, then tailor it to the agent's domain.

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
4. Read `{forge_path}/agentic.md` and all prompt files in `{forge_path}/agent/Prompts/`.
5. Classify the change as patch or regeneration using the rules in Step 3.
6. If patch: identify the specific files and sections affected by each changed field.
7. If patch: apply targeted edits to each affected file. Leave unaffected files and
   sections untouched.
8. If regenerate: run the full generation process from `api-generate.md` Steps 2
   through 4, using the updated fields and `original.name` as the agent name.
   Overwrite existing files at `forge_path`.
9. Run a consistency pass: verify that all cross-references between `agentic.md` and
   prompt files are intact. Verify that all required prompt sections are present.
10. Derive the `input_schema` and `output_schema` from the updated description.
11. Print the output JSON to stdout. No other output.
