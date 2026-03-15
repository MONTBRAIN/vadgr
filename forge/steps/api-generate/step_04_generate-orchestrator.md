# Step 4: Generate the Agent Orchestrator

**Purpose:** Generate the thin `agentic.md` orchestrator with step file references.

**Prompt:** `forge/Prompts/03_Prompt_Writer.md`

---

## Inputs

- Parsed input from Step 1
- Architecture design from Step 2
- Scaffold created in Step 3 (write into existing directory)

---

## Workflow

1. **Read:** `forge/utils/scaffold/agentic.md.template`

2. Generate `agentic.md` for the agent using the template as structural guide.

3. **Rules for API-mode orchestrators:**

   - Remove the "After Each Step" approval protocol block entirely. The execution service does not wait for human approval.
   - Remove approval gate markers. Replace any gate steps with direct save-and-continue steps.
   - Keep the trigger commands section but use API-style triggers:
     - `run {agent-name}`
     - `execute {agent-name}`
   - Each step entry in the orchestrator references its step file:
     ```
     ## Step {N}: {Step Name}
     **Step file:** `agent/steps/step_{NN}_{step-name}.md`
     Read the step file and execute it.
     ```
   - Include the Output Structure diagram showing the complete folder tree, including:
     - `agent/steps/` with all step files
     - `output/` directory (at runtime: `output/{run_id}/agent_outputs/` and `output/{run_id}/user_outputs/` created per run)
   - Include the Quality Checks table.
   - If `computer_use` is true, include the Computer Use Configuration section from the template.

4. **Generated orchestrators must be self-contained.** No references to `forge/`, `forge/patterns/`, or `forge/examples/`. The agent folder must work without Agent Forge installed.

5. **Save:** `output/{folder_name}/agentic.md` (into the scaffold from Step 3)

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that agentic.md was generated and saved

### User Output (deliverables)

Save to: `output/{folder_name}/`
- `agentic.md` -- the thin orchestrator with step file references and output structure

---

## Quality Check

- Orchestrator follows template?
- All steps reference step files?
- No approval gates (API mode)?
- Output structure includes agent_outputs/ and user_outputs/ with a note about {run_id} isolation at runtime?
- Self-contained (no forge/ references)?
