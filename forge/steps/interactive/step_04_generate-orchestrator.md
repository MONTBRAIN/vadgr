# Step 4: Generate Orchestrator

**Purpose:** Generate the workflow's `agentic.md` using the template and approved architecture.

**Prompt:** `forge/Prompts/03_Prompt_Writer.md`

---

## Inputs

- Requirements summary from Step 1
- Architecture design from Step 2
- Scaffold created in Step 3 (write into existing directory)

---

## Workflow

1. **Read:** `forge/utils/scaffold/agentic.md.template`
2. **Read:** `forge/Prompts/03_Prompt_Writer.md`

3. Generate the workflow's `agentic.md` using the template as structural guide:
   1. Fill in the workflow name and trigger commands
   2. Create the workflow overview diagram
   3. For each step, create a step reference entry with:
      - Step number and name
      - Reference to the step file: `agent/steps/step_{NN}_{step-name}.md`
      - Approval gate marker (if applicable)
   4. Add the "After Each Step" approval protocol
   5. Add the output structure diagram
   6. Add the quality checks table

4. **Present the complete agentic.md to the user for review.**
5. **Wait for approval. If changes requested, iterate.**

6. **Save:** `output/{workflow-name}/agentic.md` (into the scaffold from Step 3)

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmed orchestrator structure with all step references and gates

### User Output (deliverables)

Save to: `output/{workflow-name}/`
- `agentic.md` -- the workflow orchestrator with all steps, gates, and output structure

---

## Quality Check

- Orchestrator follows template?
- All steps present with step file references?
- Gates correct?
- User approval received before saving?
