# Step 1: Parse and Validate Input

**Purpose:** Parse the update JSON input, validate required fields, and build the change set.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- JSON object provided after "update an existing agent from:"

---

## Workflow

1. Read the JSON input provided after "update an existing agent from:".

2. Extract:
   - `forge_path` (string, path to the existing agent folder)
   - `original` (object with `name`, `description`, `steps`, `samples`, `computer_use`)
   - `updated` (object with any subset of `description`, `steps`, `samples`, `computer_use`)

3. Run validation in this order:

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

4. Build a change set: a list of field names that differ between `original` and `updated`.
   For each field in `updated`, compare its value to the same field in `original`.

   **Comparison rules:**
   - `description`: strings differ if they are not identical.
   - `steps`: arrays differ if their length, any step name, or any step's `computer_use` flag differs.
   - `samples`: arrays differ if their length or any item content differs.
   - `computer_use`: booleans differ if one is true and the other is false.

**Hold the parsed input and change set in context. Do not print anything to the user.**

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Parsed and validated input: `forge_path`, `original`, `updated`
- Change set: list of changed field names

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- All required fields present?
- Validation order correct?
- Change set accurately computed?
