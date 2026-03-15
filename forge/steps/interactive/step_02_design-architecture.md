# Step 2: Design Architecture

**Purpose:** Design the workflow structure, identify agents, patterns, and scripts needed.

**Prompt:** `forge/Prompts/02_Workflow_Architect.md`

---

## Inputs

- Requirements summary from Step 1

---

## Workflow

1. **Read:** `forge/Prompts/02_Workflow_Architect.md`

2. Using the gathered requirements, design the workflow architecture:
   1. Determine the number of steps (5-9)
   2. Identify which steps need approval gates ⏸
   3. Identify which steps need quality loops (evaluate-iterate pattern)
   4. Determine how many specialized agents are needed and their roles
   5. Design the output folder structure
   6. Decide which patterns from `forge/patterns/` apply
   7. Identify scripts the workflow needs. For each script, specify:
      - Name (e.g., `fetch_data.py`, `gen_html.py`)
      - Type: **format** (document/file generation) or **general** (API client, validator, scraper, etc.)
      - Purpose (1-2 sentences)
      - Dependencies (pip packages)
      If the workflow does not need scripts, state "Scripts: none".

3. **Read relevant patterns from `forge/patterns/` based on the requirements.** For example:
   - If the workflow needs human review: read `forge/patterns/03-approval-gates.md`
   - If the workflow needs iterative quality: read `forge/patterns/04-quality-loops.md`
   - If each execution needs a fresh copy: read `forge/patterns/07-template-scaffold.md`
   - If the workflow needs desktop interaction: read `forge/patterns/10-computer-use.md`

4. **Present the architecture to the user:**

   ```
   Proposed Workflow Architecture:

   Name: {workflow-name}
   Steps: {N}

   1. {Step Name}, {description}
   2. {Step Name}, {description} ⏸
   ...

   Agents Needed:
   - {Agent 1 Name}: {role description}
   - {Agent 2 Name}: {role description}

   Scripts Needed:
   - {script_name.py} (format|general): {purpose} [deps: {packages}]
   - (or "none")

   Output Structure:
   {folder tree}

   Patterns Applied:
   - {Pattern name}: {why}
   ```

5. **Wait for user approval. If changes requested, iterate.**

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Step definitions with approval gates
- Agent roster with roles
- Script list (or "none")
- Output folder structure
- Applied patterns

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- Architecture reviewed and approved by user?
- Patterns identified?
- Agents listed with roles?
- Scripts identified (or "none")?
