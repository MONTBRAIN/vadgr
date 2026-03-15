# Step 7: Quality Review and Return JSON

**Purpose:** Run quality checks and return the structured JSON result to the API.

**Prompt:** `forge/Prompts/04_Quality_Reviewer.md`

---

## Inputs

- Scaffold from Step 3
- Orchestrator from Step 4
- Agent prompts and step files from Step 5
- Scripts from Step 6 (if any)
- Architecture design from Step 2

---

## Workflow

1. **Read:** `forge/Prompts/04_Quality_Reviewer.md`

2. Run the quality checklist against the generated workflow. Fix any issues silently before returning.

   **Checklist:**

   - [ ] README.md exists and points to agentic.md
   - [ ] CLAUDE.md lists all commands and describes the project structure
   - [ ] agentic.md has all steps with step file references
   - [ ] Every step in agentic.md has a corresponding step file in `agent/steps/`
   - [ ] Every step in agentic.md has a corresponding slash command in `.claude/commands/`
   - [ ] Every agent referenced in step files has a prompt file in `agent/Prompts/`
   - [ ] Step files define inputs, workflow, and required outputs
   - [ ] Step files reference `output/{run_id}/agent_outputs/step_{NN}_agent_output.md`
   - [ ] Step files reference `output/{run_id}/user_outputs/step_{NN}/` where applicable
   - [ ] Output structure is documented in agentic.md
   - [ ] Agent prompts have all required sections (Context, I/O, Quality, Rules, Actual Input, Expected Workflow)
   - [ ] No circular dependencies between steps
   - [ ] The workflow is self-contained (no references to files outside its own directory)
   - [ ] agent/ directory exists with Prompts/, steps/, scripts/, utils/
   - [ ] agent/scripts/.venv/ exists and has working pip
   - [ ] If scripts identified in Step 2: each script exists with tests
   - [ ] .claude/commands/fix.md exists
   - [ ] agent/Prompts/00_Workflow_Fixer.md exists
   - [ ] agent/Prompts/01_Senior_Prompt_Engineer.md exists
   - [ ] output/ directory exists (scaffold creates base; at runtime the API creates output/{run_id}/agent_outputs/ and output/{run_id}/user_outputs/ per run)
   - [ ] If computer use: Computer Use Agent prompt exists?
   - [ ] If computer use: Execution commands generated?

3. After all checks pass, print a single JSON object to stdout. This is the only output the API reads.

   ```json
   {
     "forge_path": "output/{folder_name}/",
     "forge_config": {
       "complexity": "simple | multi_step",
       "steps": 3,
       "prompts": ["02_Agent_Name.md", "03_Agent_Name.md"]
     },
     "steps": [
       { "name": "Step Name", "computer_use": false }
     ],
     "input_schema": [
       { "name": "input_name", "type": "text", "required": true }
     ],
     "output_schema": [
       { "name": "output_name", "type": "text" }
     ]
   }
   ```

   **Field definitions:**

   - `forge_path`: Relative path to the generated agent folder from the repo root.
   - `forge_config.complexity`: `"simple"` or `"multi_step"`.
   - `forge_config.steps`: Number of steps in the generated `agentic.md`.
   - `forge_config.prompts`: List of generated prompt filenames in `agent/Prompts/` (excluding standard 00/01 prompts).
   - `steps`: Array of step objects from the generated `agentic.md`. Each has `name` (Title Case, matching step headings) and `computer_use` (boolean). Order must match the step numbering in `agentic.md`.
   - `input_schema`: Inferred inputs the agent needs at runtime. Each item has `name`, `type` (one of: `text`, `file`, `number`, `boolean`), and `required` (boolean).
   - `output_schema`: Inferred outputs the agent produces. Each item has `name` and `type`.

   Print only this JSON object. No preamble, no summary, no explanation. The API parses this directly.

4. **Present the final summary:**

   ```
   Workflow "{workflow-name}" is ready!

   Location: output/{workflow-name}/

   Files created:
   ├── README.md
   ├── CLAUDE.md
   ├── agentic.md ({N} steps)
   ├── .claude/commands/ ({M} commands)
   │   ├── {command-1}.md
   │   └── ...
   ├── agent/
   │   ├── Prompts/ ({K} agents + fixer)
   │   │   ├── 00_Workflow_Fixer.md
   │   │   ├── 01_Senior_Prompt_Engineer.md
   │   │   ├── 02_{Agent_Name}.md
   │   │   └── ...
   │   ├── steps/ ({N} step files)
   │   │   ├── step_01_{step-name}.md
   │   │   └── ...
   │   ├── scripts/
   │   │   ├── src/
   │   │   ├── tests/
   │   │   ├── requirements.txt
   │   │   └── README.md
   │   └── utils/
   │       ├── code/
   │       └── docs/
   ├── output/  (at runtime: output/{run_id}/agent_outputs/ and output/{run_id}/user_outputs/)
   └── {output-dirs}/

   To use this workflow:
   1. Open the project folder in your AI coding agent (e.g., Claude Code, OpenCode)
   2. Point it at agentic.md: "Read agentic.md and start"
   3. Follow the step-by-step instructions

   Patterns applied: {list}
   ```

---

## Required Outputs

### Agent Output (inter-step context)

None. This is the final step.

### User Output (deliverables)

No files saved. Output is printed to stdout only.
- JSON result object printed to stdout (parsed by the API)

---

## Quality Check

- All checklist items pass?
- JSON output is valid and complete?
- Step files properly structured?
