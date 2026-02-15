# Agent Forge — Meta-Workflow Orchestrator

## Trigger Commands

- `create new workflow`
- `new agentic project`
- `build workflow for [domain]`
- `/create-workflow`

---

## Workflow Overview

```
Step 1         Step 2          Step 3          Step 4       Step 5       Step 6          Step 7
Gather    -->  Design     -->  Generate   -->  Generate --> Generate --> Generate   -->  Review
Requirements   Architecture    Orchestrator    Agents       Commands     Scaffold        & Deliver
               ⏸               ⏸                                        ⏸               ⏸
```

---

## Step 1: Gather Requirements

**Purpose:** Understand what the user wants to automate and how.

**On trigger, ask ONE question at a time. Wait for each response.**

Question 1:
```
What is the purpose of this workflow? Describe what it should accomplish
in 2-3 sentences.
```

Question 2:
```
Who is the user of this workflow? (e.g., "me for personal use",
"a team of developers", "students learning a topic")
```

Question 3:
```
Describe the main steps or phases of the work. What does someone
currently do manually that this workflow should automate or orchestrate?
```

Question 4:
```
Are there any points where a human MUST review/approve before continuing?
If yes, describe them.
```

Question 5:
```
What are the expected outputs? Describe the files, folders, or artifacts
this workflow should produce.
```

Question 6:
```
Where should the generated workflow project be created?
Default: output/{workflow-name}/
```

**After all questions answered:** Compile a requirements summary. Present it to the user for confirmation.

**Save:** Hold requirements summary in context for subsequent steps.

---

## Step 2: Design Architecture ⏸

**Read:** `forge/Prompts/1. Workflow Architect.md`

Using the gathered requirements, design the workflow architecture:

1. Determine the number of steps (5-9)
2. Identify which steps need approval gates ⏸
3. Identify which steps need quality loops (evaluate-iterate pattern)
4. Determine how many specialized agents are needed and their roles
5. Design the output folder structure
6. Decide which patterns from `patterns/` apply

**Read relevant patterns from `patterns/` based on the requirements.** For example:
- If the workflow needs human review: read `patterns/03-approval-gates.md`
- If the workflow needs iterative quality: read `patterns/04-quality-loops.md`
- If each execution needs a fresh copy: read `patterns/07-template-scaffold.md`

**Present the architecture to the user:**

```
Proposed Workflow Architecture:

Name: {workflow-name}
Steps: {N}

1. {Step Name} — {description}
2. {Step Name} — {description} ⏸
...

Agents Needed:
- {Agent 1 Name}: {role description}
- {Agent 2 Name}: {role description}

Output Structure:
{folder tree}

Patterns Applied:
- {Pattern name}: {why}
```

**Wait for user approval. If changes requested, iterate.**

---

## Step 3: Generate Orchestrator ⏸

**Read:** `forge/utils/scaffold/agentic.md.template`
**Read:** `forge/Prompts/2. Prompt Writer.md`

Generate the workflow's `agentic.md` using the template as structural guide:

1. Fill in the workflow name and trigger commands
2. Create the workflow overview diagram
3. Write each step with:
   - Purpose description
   - Which agent prompt to read (if applicable)
   - Numbered workflow actions
   - What to save
   - Approval gate marker ⏸ (if applicable)
4. Add the "After Each Step" approval protocol
5. Add the output structure diagram
6. Add the quality checks table

**Present the complete agentic.md to the user for review.**
**Wait for approval. If changes requested, iterate.**

**Save:** `output/{workflow-name}/agentic.md`

---

## Step 4: Generate Specialized Agents

**Read:** `forge/Prompts/2. Prompt Writer.md`
**Read:** `forge/utils/scaffold/agent-prompt.md.template`

For each agent identified in Step 2:

1. Generate a comprehensive prompt following the canonical template:
   - Context (role and expertise)
   - Input/Output specifications
   - Quality requirements
   - Rules (Always/Never lists)
   - Actual Input section with placeholders
   - Expected Workflow section
2. Number the prompt files sequentially: `1. {Agent Name}.md`, `2. {Agent Name}.md`, etc.

**Save:** `output/{workflow-name}/Prompts/{N}. {Agent Name}.md` for each agent

---

## Step 5: Generate CLI Commands

**Read:** `forge/utils/scaffold/command.md.template`

For each step in the designed workflow:

1. Create a `.claude/commands/` file with:
   - YAML frontmatter (description, argument-hint)
   - Instruction to read `agentic.md`
   - Instruction to read the relevant prompt file (if the step uses an agent)
   - Reference to the specific step number and name
   - Brief summary of what the step does (3-5 lines)

2. Additionally create a **master start command** that runs the full workflow from Step 1 through the last step.

**Save:** `output/{workflow-name}/.claude/commands/{command-name}.md` for each command

---

## Step 6: Generate Project Scaffold ⏸

**Read:** `forge/utils/scaffold/README.md.template`
**Read:** `forge/utils/scaffold/CLAUDE.md.template`

Generate the remaining project files:

1. **README.md** — Entry point with "Read `agentic.md` and start" pattern, workflow description, command listing
2. **CLAUDE.md** — Project rules, structure listing, how-to-use, key rules, naming conventions
3. **Output directories** — Create any directories referenced in the output structure with `.gitkeep` files
4. **Templates** (if the workflow uses the template-scaffold pattern) — Create the template directory with starter files

**Present the complete file listing to the user.**
**Wait for approval.**

**Save:** All remaining files into `output/{workflow-name}/`

---

## Step 7: Review and Deliver ⏸

**Read:** `forge/Prompts/3. Quality Reviewer.md`

Run the quality reviewer's checklist against the generated workflow:

**Self-review checklist:**

- [ ] README.md exists and points to agentic.md
- [ ] agentic.md has all steps with clear instructions
- [ ] Every step in agentic.md has a corresponding slash command in `.claude/commands/`
- [ ] Every agent referenced in agentic.md has a prompt file in `Prompts/`
- [ ] Approval gates are marked at appropriate decision points
- [ ] Output structure is documented in agentic.md
- [ ] CLAUDE.md lists all commands and describes the project structure
- [ ] Agent prompts have all required sections (Context, I/O, Quality, Rules, Actual Input, Expected Workflow)
- [ ] No circular dependencies between steps
- [ ] The workflow is self-contained (no references to files outside its own directory)

**Fix any issues found before delivering.**

**Present the final summary:**

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
├── Prompts/ ({K} agents)
│   ├── 1. {Agent Name}.md
│   └── ...
└── {output-dirs}/

To use this workflow:
1. Open the project folder in Claude Code
2. Type: /{start-command}
3. Follow the step-by-step instructions

Patterns applied: {list}
```

---

## After Each Step

**ALWAYS ask for user approval before saving/marking complete:**

1. Show output to the user
2. Ask: "Does this look good? Any changes needed?"
3. **Wait for user approval**
   - If changes requested → Modify and show again
   - If approved → Continue
4. Save files
5. Confirm: "Saved"

**NEVER proceed to the next step without user confirmation.**

---

## Clarifications

### Self-Similar Architecture
Agent Forge generates workflows that follow the **same architecture** as Agent Forge itself. If you're unsure how to structure something in the generated workflow, look at how Agent Forge does it. The `forge/` directory IS the reference implementation.

### Templates vs From Scratch
**ALWAYS** start from the scaffold templates in `forge/utils/scaffold/`. Never write an `agentic.md`, `README.md`, `CLAUDE.md`, agent prompt, or command file from scratch. The templates exist to enforce consistency — fill in the placeholders, adapt the structure, but keep the skeleton.

### When to Add Approval Gates
Not every step needs a gate. Add `⏸` only at **decision points** where:
- The user needs to review a design before generation starts (e.g., architecture review)
- Generated content must be approved before building on top of it (e.g., orchestrator review)
- The final deliverable is ready for sign-off

Steps that are purely mechanical (e.g., "generate commands from an already-approved architecture") do NOT need gates.

### When to Add Quality Loops
Only add evaluate-iterate loops when:
- There is a **measurable quality bar** (e.g., "90% of rubric criteria met")
- The output can be objectively improved through iteration
- The user expects iterative refinement as part of the workflow

Do NOT add quality loops to steps where the output is either correct or not (binary).

### Step Count
5-9 steps is the sweet spot. Fewer than 5 usually means steps are too broad and the agent won't know what to focus on. More than 9 usually means steps are too granular and the workflow becomes tedious. If you find yourself designing more than 9, combine related steps.

### Agent Count
Not every step needs a dedicated agent. Agents are for steps that require **specialized expertise** (e.g., "Software Architect" for design, "Code Generator" for implementation). Mechanical steps like "copy a template" or "create folders" don't need agents — the orchestrator handles them directly.

### Generated Workflows Must Be Self-Contained
Every workflow in `output/` must work **without Agent Forge installed**. This means:
- No references to `forge/`, `patterns/`, or `examples/`
- All prompts, commands, and templates are included in the generated project
- A user can copy the output folder anywhere and it works

### The Orchestrator is the Source of Truth
The `agentic.md` file is the **single source of truth** for any workflow. Slash commands are shortcuts that point INTO it, not replacements for it. Agent prompts are read BY it, not independently. Everything flows through the orchestrator.

### Naming Generated Workflows
- Workflow folder: `kebab-case` (e.g., `content-pipeline`)
- Slash commands: `kebab-case` matching step names (e.g., `generate-content.md`)
- Agent prompts: numbered with title case (e.g., `1. Content Strategist.md`)
- Master command: always named `start-{workflow-name}.md` or `create-{workflow-name}.md`

### What Agent Forge Does NOT Do
- It does **not** generate application code (apps, APIs, scripts). It generates **workflow definitions** (orchestrators, prompts, commands).
- It does **not** execute the workflows it generates. It only creates the files.
- It does **not** install dependencies or set up environments. Generated workflows handle that themselves.

---

## Quality Checks

| Step | Check |
|------|-------|
| 01 | All 6 questions answered? Requirements clear? |
| 02 | Architecture reviewed? Patterns identified? Agents listed? |
| 03 | Orchestrator follows template? All steps present? Gates correct? |
| 04 | All agents generated? Each has all required sections? |
| 05 | One command per step? Master command exists? Frontmatter complete? |
| 06 | README, CLAUDE.md, output dirs created? Templates if needed? |
| 07 | Self-review passes all checks? Workflow is self-contained? |
