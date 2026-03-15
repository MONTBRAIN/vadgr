# Step 2: Design Architecture

**Purpose:** Analyze complexity and design the agent's workflow architecture.

**Prompt:** `forge/Prompts/02_Workflow_Architect.md`

---

## Inputs

- Parsed input from Step 1

---

## Workflow

1. **Read:** `forge/Prompts/02_Workflow_Architect.md`

2. Analyze the description to determine:

   1. **Complexity level.** One of:
      - `simple`: The task is a single, bounded operation. One step, one prompt. Example: "Summarize this text in bullet points."
      - `multi_step`: The task has multiple phases that build on each other. 2-5 steps, 2-4 prompts. Example: "Research a topic and write a structured report."

   2. **Steps.** If the caller provided `steps`, use those. Otherwise infer from the description. Each step should produce one clear artifact.

   3. **Agent roster.** Which specialized agents are needed and what expertise each covers. Use the guidance in `forge/Prompts/02_Workflow_Architect.md`:
      - Simple: 1 agent.
      - Multi-step: 2-4 agents, each covering a distinct expertise area.
      - Not every step needs an agent. Mechanical steps (file writing, format conversion) need none.

   4. **Input schema.** What inputs the agent needs when it runs. Infer from the description. Each input has a name and type (text, file, number, boolean).

   5. **Output schema.** What the agent produces. Infer from the description. Each output has a name and type.

   6. **Output structure.** Design the output folder structure:
      - `output/{folder_name}/output/agent_outputs/` -- inter-step context files
      - `output/{folder_name}/output/user_outputs/` -- user-facing deliverables
      Each step writes agent output to: `output/{run_id}/agent_outputs/step_{NN}_agent_output.md` (at runtime via the API; for standalone/interactive use, `output/agent_outputs/step_{NN}_agent_output.md`)
      Each step writes user deliverables to: `output/{run_id}/user_outputs/step_{NN}/` (at runtime via the API; for standalone/interactive use, `output/user_outputs/step_{NN}/`)

   7. **Computer use.** Check each step's `computer_use` flag. Steps marked `computer_use: true` need desktop automation. Steps marked `computer_use: false` or plain string steps are CLI-only. Do not infer -- trust the caller's per-step flags.

   8. **Scripts.** Identify scripts the workflow needs. For each script, specify:
      - Name (e.g., `fetch_data.py`, `gen_html.py`)
      - Type: **format** (document/file generation) or **general** (API client, validator, scraper, etc.)
      - Purpose (1-2 sentences)
      - Dependencies (pip packages)
      If the workflow does not need custom scripts, state "Scripts: none". Note: `gen_document.py` (PDF/DOCX) and `gen_xlsx.py` (Excel) are built-in and copied automatically -- only list scripts for formats or tasks not already covered.

3. **Save in context:**
   ```
   complexity: simple | multi_step
   steps: [{number, name, description, agent_name or null, computer_use: true|false}]
   agents: [{name, role, expertise}]
   scripts: [{name, type (format|general), purpose, dependencies}] or "none"
   input_schema: [{name, type, required}]
   output_schema: [{name, type}]
   output_structure: {folder tree}
   computer_use: true | false (agent-level, true if any step has computer_use)
   ```

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- `complexity`, `steps`, `agents`, `scripts`, `input_schema`, `output_schema`, `output_structure`, `computer_use`

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- Complexity correctly classified?
- Steps well-defined with clear artifacts?
- Input/output schema inferred?
- Output structure uses agent_outputs/ and user_outputs/?
