# Step 7: Review and Deliver

**Purpose:** Run the quality reviewer's checklist against the generated workflow and deliver.

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

2. Run the quality reviewer's checklist against the generated workflow:

   **Self-review checklist:**

   - [ ] README.md exists and points to agentic.md
   - [ ] agentic.md has all steps with step file references
   - [ ] Every step in agentic.md has a corresponding step file in `agent/steps/`
   - [ ] Every step in agentic.md has a corresponding slash command in `.claude/commands/`
   - [ ] Every agent referenced in step files has a prompt file in `agent/Prompts/`
   - [ ] Step files define inputs, workflow, and required outputs
   - [ ] Step files reference `output/{run_id}/agent_outputs/step_{NN}_agent_output.md` for inter-step context (at runtime via the API, `{run_id}` is provided by the executor; for standalone/interactive use, `output/agent_outputs/`)
   - [ ] Step files reference `output/{run_id}/user_outputs/step_{NN}/` for user deliverables (where applicable)
   - [ ] Approval gates are marked at appropriate decision points
   - [ ] Output structure is documented in agentic.md
   - [ ] CLAUDE.md lists all commands and describes the project structure
   - [ ] Agent prompts have all required sections (Context, I/O, Quality, Rules, Actual Input, Expected Workflow)
   - [ ] No circular dependencies between steps
   - [ ] The workflow is self-contained (no references to files outside its own directory)
   - [ ] agent/ directory exists with Prompts/, steps/, scripts/, utils/
   - [ ] agent/scripts/ contains src/, tests/, requirements.txt, README.md
   - [ ] agent/scripts/.venv/ exists and has working pip
   - [ ] agent/utils/ contains code/ and docs/
   - [ ] agent/scripts/README.md includes venv setup instructions
   - [ ] If scripts identified in Step 2: each script exists in agent/scripts/src/
   - [ ] If scripts identified in Step 2: each script has tests in agent/scripts/tests/
   - [ ] If scripts identified in Step 2: dependencies are in agent/scripts/requirements.txt and installed in .venv
   - [ ] .claude/commands/fix.md exists (standard in all workflows)
   - [ ] agent/Prompts/00_Workflow_Fixer.md exists (standard in all workflows)
   - [ ] agent/Prompts/01_Senior_Prompt_Engineer.md exists (standard in all workflows)
   - [ ] output/ directory exists (scaffold creates base; at runtime the API creates output/{run_id}/agent_outputs/ and output/{run_id}/user_outputs/ per run)
   - [ ] If computer use: Computer Use Agent prompt exists?
   - [ ] If computer use: Execution commands (execute-workflow, pause, resume) generated?
   - [ ] If computer use: computer_use/config.yaml present in generated project?

3. **Fix any issues found before delivering.**

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
   │   │   ├── 01_{Agent_Name}.md
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

No new files saved in this step. All deliverables were saved in Steps 3-6.
- Final summary presented to user with the complete file listing and usage instructions

---

## Quality Check

- Self-review checklist passes all items?
- Workflow is self-contained (no references outside its directory)?
- Step files properly structured with inputs and required outputs?
- Final summary presented to user?
