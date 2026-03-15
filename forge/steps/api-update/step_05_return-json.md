# Step 5: Write Output and Return JSON

**Purpose:** Run consistency checks and return the structured JSON result to the API.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- Updated files from Step 4
- Parsed input from Step 1

---

## Workflow

1. Run a consistency pass on the updated agent folder:
   - Verify `agentic.md` exists and has valid step references
   - Verify all referenced step files exist in `agent/steps/` (if using new format)
   - Verify all referenced prompt files exist in `agent/Prompts/`
   - Verify cross-references between agentic.md, step files, and prompt files are intact
   - Verify all required prompt sections are present

2. Derive the `input_schema` and `output_schema` from the updated description.
   Do not copy the original schema forward if the description changed.

3. Print a single JSON object to stdout. This is the only output the API reads.

   ```json
   {
     "forge_path": "output/{name}/",
     "forge_config": {
       "complexity": "simple | multi_step",
       "steps": 1,
       "prompts": ["02_Agent_Name.md"]
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
   - `forge_config.complexity`: The complexity of the workflow after the update.
   - `forge_config.steps`: Number of steps in `agentic.md` after the update.
   - `forge_config.prompts`: List of prompt filenames in `agent/Prompts/` after the
     update, reflecting any additions or removals.
   - `input_schema`: Inferred inputs the agent needs at runtime.
   - `output_schema`: Inferred outputs the agent produces.

   Print only this JSON object. No preamble, no summary, no explanation.

---

## Required Outputs

### Agent Output (inter-step context)

None. This is the final step.

### User Output (deliverables)

No files saved. Output is printed to stdout only.
- JSON result object printed to stdout (parsed by the API)

---

## Quality Check

- Consistency pass successful?
- JSON output valid and complete?
- Schema derived from updated description (not copied from original)?
