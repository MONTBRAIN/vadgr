# Step 4: Apply the Update

**Purpose:** Apply targeted patches or full regeneration based on the classification.

**Prompt:** `forge/Prompts/03_Prompt_Writer.md`, `forge/Prompts/01_Senior_Prompt_Engineer.md`

---

## Inputs

- Update classification from Step 3
- Existing file contents from Step 2
- Parsed input from Step 1

---

## Workflow

### If update_mode is patch

Apply targeted edits to each affected file. Do not touch files that are not affected
by the change set.

**Description changed:**

1. Read the existing agent prompt(s) in `{forge_path}/agent/Prompts/`.
2. **Read:** `forge/Prompts/01_Senior_Prompt_Engineer.md` -- use for craft guidance when rewriting prompt sections.
3. Identify sections that are driven by the description: Context, Actual Input,
   Expected Workflow, and (if present) Quality Requirements.
4. Rewrite only those sections to reflect the updated description.
   Keep all other sections (Rules, Quality Examples, Clarifications) intact unless
   they directly contradict the new description.
5. In `agentic.md`, update the step purpose lines and any narrative text that
   references the original description. Do not change the step count or structure.
6. If step files exist in `agent/steps/`, update the Purpose and Workflow sections
   of affected step files. Keep Required Outputs structure intact.

**Samples changed:**

1. Read the updated samples. For each sample:
   - Identify the patterns, structure, tone, and level of detail that characterize it.
   - Express these as updated Quality Requirements or Quality Examples in the relevant
     prompt(s).
   - Do not copy the sample verbatim into the prompt. Derive the principles and express
     them as measurable criteria.

2. If samples were removed, remove only the Quality Requirements and Quality Examples
   derived from those specific samples. Keep general quality standards.

**`computer_use` changed from false to true:**

1. Read `forge/Prompts/05_Computer_Use_Agent.md`.
2. Generate a Computer Use Agent prompt adapted to the agent's description.
   Save it as `{forge_path}/agent/Prompts/05_Computer_Use_Agent.md`.
3. Add a Computer Use Configuration section to `{forge_path}/agentic.md`.

**`computer_use` changed from true to false:**

1. Delete `{forge_path}/agent/Prompts/05_Computer_Use_Agent.md` if it exists.
2. Remove the Computer Use Configuration section from `{forge_path}/agentic.md`.

**Multiple fields changed:**

Apply each change in the order listed above. After all changes, do a consistency pass:
verify that cross-references between `agentic.md`, step files, and prompt files are intact.

### If update_mode is regenerate

Run the same process as `api-generate.md` Steps 2 through 4, using the updated fields
as the input. Use `original.name` as the agent name (do not rename the folder).

Write the new files to `{forge_path}`, overwriting the existing files. Do not create
scripts/, utils/, README.md, CLAUDE.md, or .claude/ directories.

Ensure the regenerated files use the new step file architecture:
- Thin orchestrator in `agentic.md` with step file references
- Step files in `agent/steps/` with inputs, workflow, and required outputs
- Output directories: `output/agent_outputs/` and `output/user_outputs/`

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that all targeted files have been patched or regenerated

### User Output (deliverables)

Save to: `{forge_path}/`
- Updated `agentic.md` (if affected)
- Updated agent prompt files in `agent/Prompts/` (if affected)
- Updated step files in `agent/steps/` (if affected)

---

## Quality Check

- Only affected files modified (patch mode)?
- Cross-references intact after changes?
- Step files updated if they exist?
- Regenerated files use new step file architecture?
