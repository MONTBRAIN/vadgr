# Step 5: Generate Specialized Agents

**Purpose:** Generate agent prompt files and step definition files for each workflow step.

**Prompt:** `forge/Prompts/03_Prompt_Writer.md`

---

## Inputs

- Requirements summary from Step 1
- Architecture design from Step 2
- Scaffold created in Step 3 (write into existing directory)
- Orchestrator from Step 4

---

## Workflow

1. **Read:** `forge/Prompts/03_Prompt_Writer.md`
2. **Read:** `forge/utils/scaffold/agent-prompt.md.template`

3. Optionally, read the **Senior Prompt Engineer** prompt at `forge/Prompts/01_Senior_Prompt_Engineer.md` for complex or domain-specific prompts that require deeper expertise. The Prompt Writer prompt covers the structural template; the Senior Prompt Engineer covers the craft of writing high-quality, production-grade prompts.

4. For each agent identified in Step 2:
   1. Generate a comprehensive prompt following the canonical template:
      - Context (role and expertise)
      - Input/Output specifications
      - Quality requirements
      - Rules (Always/Never lists)
      - Actual Input section with placeholders
      - Expected Workflow section
   2. Number the prompt files sequentially: `02_{Agent_Name}.md`, `03_{Agent_Name}.md`, etc.
   3. If the workflow needs desktop interaction (computer_use flag set in Step 1), generate a `05_Computer_Use_Agent.md` prompt based on `forge/Prompts/05_Computer_Use_Agent.md`. Adapt it to the specific workflow's desktop tasks.

5. For each step in the workflow, generate a step definition file at `agent/steps/step_{NN}_{step-name}.md` with:
   - Step name and purpose
   - Prompt reference (which agent prompt to read, if any)
   - Inputs (what context this step receives)
   - Workflow (numbered actions for this step)
   - Required outputs:
     - `output/{run_id}/agent_outputs/step_{NN}_agent_output.md` -- inter-step context (at runtime via the API, `{run_id}` is provided by the executor to isolate concurrent runs; for standalone/interactive use, outputs go directly to `output/agent_outputs/`)
     - `output/{run_id}/user_outputs/step_{NN}/` -- user-facing deliverables (if any)

6. **Script emission:** While writing agent prompts and step files, identify any scripts that the agent needs at runtime. For each script requirement discovered during prompt writing, add a `## Script Requirements` section at the end of the step file:

   ```markdown
   ## Script Requirements

   Scripts needed by this step (collected by Step 6: Generate Scripts):
   - `gen_report.py`: Generates PDF reports from markdown input. Deps: reportlab, markdown.
     CLI: `python3 agent/scripts/src/gen_report.py output/report.pdf --input report_data.json`
   - `fetch_data.py`: Fetches data from external API. Deps: requests.
     CLI: `python3 agent/scripts/src/fetch_data.py --url https://api.example.com --output data.json`
   ```

   Each script entry must include both a description and the CLI command the step will use to call it at runtime. Step 6 uses both fields: the description to generate the script, and the CLI line to validate the argparse interface. Only add this section when the step genuinely needs a script -- not every step requires one.

7. **Save:**
   - `output/{workflow-name}/agent/Prompts/{NN}_{Agent_Name}.md` for each agent
   - `output/{workflow-name}/agent/steps/step_{NN}_{step-name}.md` for each step

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that all agent prompts and step files have been generated
- List of script requirements emitted from step files (for Step 6)

### User Output (deliverables)

Save to: `output/{workflow-name}/`
- `agent/Prompts/{NN}_{Agent_Name}.md` for each agent
- `agent/steps/step_{NN}_{step-name}.md` for each step

---

## Quality Check

- All agents generated with all required sections?
- All step files generated with proper inputs and outputs?
- Agent output paths in generated step files use `output/{run_id}/agent_outputs/`?
- User output paths in generated step files use `output/{run_id}/user_outputs/`?
- Script Requirements sections added where steps need scripts?
- Each script entry in Script Requirements includes the CLI command the step will use?
