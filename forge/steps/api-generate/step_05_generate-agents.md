# Step 5: Generate Agent Prompts and Step Files

**Purpose:** Generate specialized agent prompts and self-contained step definition files.

**Prompt:** `forge/Prompts/03_Prompt_Writer.md`, `forge/Prompts/01_Senior_Prompt_Engineer.md`

---

## Inputs

- Parsed input from Step 1
- Architecture design from Step 2
- Scaffold created in Step 3 (write into existing directory)
- Orchestrator from Step 4

---

## Workflow

1. **Read:** `forge/Prompts/03_Prompt_Writer.md`
2. **Read:** `forge/utils/scaffold/agent-prompt.md.template`
3. **Read:** `forge/Prompts/01_Senior_Prompt_Engineer.md` -- use for craft guidance on complex or domain-specific prompts. The Prompt Writer covers the structural template; the Senior Prompt Engineer covers writing high-quality, production-grade prompts.

4. For each agent in the roster from Step 2:
   1. Generate a complete prompt following the canonical template:
      - Context (role and expertise, 2-4 sentences, second person)
      - Input and Outputs (concrete, specific, measurable)
      - Quality Requirements (numerical thresholds where possible)
      - Clarifications (if the domain benefits from it)
      - Quality Examples (good and bad samples, if the domain benefits from it)
      - Rules (Always/Never, at least 3 each, actionable behaviors)
      - Actual Input (placeholders matching what the orchestrator passes)
      - Expected Workflow (numbered list, starts with input validation)

   2. For steps with `computer_use: true`, generate a Computer Use Agent prompt based on `forge/Prompts/05_Computer_Use_Agent.md`. Adapt it to the specific desktop tasks that step needs to perform. Only steps explicitly marked with `computer_use: true` get a Computer Use Agent prompt.

   3. Calibrate prompts against quality samples if provided. For each sample:
      - Read the content and label.
      - Identify the patterns, structure, tone, and level of detail that characterize it.
      - Add Quality Requirements and Quality Examples to the relevant prompt(s) that encode these characteristics concretely. Do not copy the sample verbatim into the prompt.

   4. Number prompt files sequentially starting at 02: `02_{Agent_Name}.md`, `03_{Agent_Name}.md`, etc. (01 is reserved for Senior Prompt Engineer, 00 for Workflow Fixer).

5. For each step in the workflow, generate a step definition file at `agent/steps/step_{NN}_{step-name}.md` with:

   ```markdown
   # Step {N}: {Step Name}

   **Purpose:** {what this step accomplishes}

   **Prompt:** `agent/Prompts/{NN}_{Agent_Name}.md` (or "None" for mechanical steps)

   ---

   ## Inputs
   - {what context/data this step receives}
   - Previous step context: `output/{run_id}/agent_outputs/step_{NN-1}_agent_output.md` (if not first step)

   ---

   ## Workflow
   1. {action 1}
   2. {action 2}
   3. {action N}

   ---

   ## Required Outputs

   ### Agent Output (inter-step context)
   Save to: `output/{run_id}/agent_outputs/step_{NN}_agent_output.md`
   - {what context to pass to next steps}

   ### User Output (deliverables)
   Save to: `output/{run_id}/user_outputs/step_{NN}/`
   - {files/artifacts the user receives, if any for this step}
   ```

6. **Script emission:** While writing agent prompts and step files, identify any scripts that the agent needs at runtime. For each script requirement discovered during prompt writing, add a `## Script Requirements` section at the end of the step file:

   ```markdown
   ## Script Requirements

   Scripts needed by this step (collected by Step 6: Generate Scripts):
   - `gen_report.py`: Generates PDF reports from markdown input. Deps: reportlab, markdown.
     CLI: `python3 agent/scripts/src/gen_report.py output/report.pdf --input report_data.json`
   - `fetch_data.py`: Fetches data from external API. Deps: requests.
     CLI: `python3 agent/scripts/src/fetch_data.py --url https://api.example.com --output data.json`
   ```

   Each script entry must include both a description and the CLI command the step will use to call it at runtime. Step 6 uses both fields: the description to generate the script, and the CLI line to validate the argparse interface. Only add this section when the step genuinely needs a script.

7. **Save:**
   - `output/{folder_name}/agent/Prompts/{NN}_{Agent_Name}.md` for each agent
   - `output/{folder_name}/agent/steps/step_{NN}_{step-name}.md` for each step

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that all agent prompts and step files have been generated
- List of script requirements emitted from step files (for Step 6)

### User Output (deliverables)

Save to: `output/{folder_name}/`
- `agent/Prompts/{NN}_{Agent_Name}.md` for each agent
- `agent/steps/step_{NN}_{step-name}.md` for each step

---

## Quality Check

- All agents generated with all required sections?
- Senior Prompt Engineer guidance applied for complex prompts?
- All step files generated with proper structure?
- Each step file references `output/{run_id}/agent_outputs/step_{NN}_agent_output.md`?
- Each step file references `output/{run_id}/user_outputs/step_{NN}/` where applicable?
- Step files reference correct agent prompts?
- Script Requirements sections added where steps need scripts?
- Each script entry in Script Requirements includes the CLI command the step will use?
