# Step 1: Parse and Validate Input

**Purpose:** Parse the JSON input and validate required fields.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- JSON object provided after "generate an agent from:"

---

## Workflow

1. Read the JSON input provided after "generate an agent from:".

2. Extract:
   - `id` (string, optional -- when present, use as the output folder name instead of `name`)
   - `name` (string, kebab-case)
   - `description` (string)
   - `samples` (array, may be empty)
   - `computer_use` (boolean, default false)
   - `steps` (array, optional)

3. Determine the output folder name: if `id` is present and non-empty, use `id`; otherwise use `name` (kebab-cased). Call this `folder_name` and use `output/{folder_name}/` as the output path throughout.

4. If `description` is missing or empty:
   ```json
   {"error": "description is required"}
   ```
   Print this and stop.

5. Normalize `name` to kebab-case if it is not already (lowercase, spaces to hyphens, remove special characters).

6. `samples` items may be strings (treated as content with no label) or objects with `content` and optional `label` fields.

7. `computer_use` at the agent level is true if any step has `computer_use: true`. Do not infer -- trust the caller's flags.

**Hold the parsed input in context. Do not print anything to the user.**

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- `id`, `name`, `folder_name`, `description`, `samples`, `computer_use`, `steps`

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- All required fields present?
- Name normalized to kebab-case?
- folder_name correctly derived?
