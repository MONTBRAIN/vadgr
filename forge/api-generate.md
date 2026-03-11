# API Generate, Programmatic Agent Generation

## Purpose

This file is the non-interactive entry point for agent generation. The API calls this
instead of `agentic.md` when it needs to generate an agent folder from structured input
without human interaction.

Invoke via:
```
claude -p "Read forge/api-generate.md and generate an agent from: {JSON}"
```

Where `{JSON}` is a JSON object conforming to the input format described below.

---

## Input Format

Accept a JSON object with the following fields:

```json
{
  "id": "optional-unique-id",
  "name": "kebab-case-agent-name",
  "description": "Plain-language description of what the agent should accomplish.",
  "samples": [
    {
      "content": "Example of what good output looks like.",
      "label": "Optional short label describing what this sample shows."
    }
  ],
  "steps": [
    {"name": "Research sources", "computer_use": false},
    {"name": "Create pull request", "computer_use": true}
  ],
  "computer_use": true
}
```

**Required:** `name`, `description`

**Optional:** `id` (string, when provided use `output/{id}/` as the output folder instead of `output/{name}/`), `samples` (array, may be empty or omitted), `computer_use` (boolean, defaults to false), `steps` (array of step objects or strings)

**Steps format:** Steps can be plain strings (e.g. `"Research sources"`) or objects with per-step computer use (e.g. `{"name": "Create PR", "computer_use": true}`). When steps are objects, each step's `computer_use` flag indicates whether that specific step needs desktop automation (open apps, click, browse). Steps without `computer_use` or plain strings default to CLI-only.

**Validation:**
- If `name` is missing or empty, derive it from the description: take the first 4-5 significant words, lowercase, hyphens between words.
- If `description` is missing or empty, write an error JSON to stdout and stop: `{"error": "description is required"}`.
- `samples` items may be strings (treated as content with no label) or objects with `content` and optional `label` fields.
- `computer_use` at the agent level is true if any step has `computer_use: true`. Do not infer -- trust the caller's flags.

---

## What This Orchestrator Does

This orchestrator runs a focused subset of the full forge generation process:

1. Analyze the description to determine complexity and steps.
2. Design the agent architecture.
3. Generate `agentic.md` for the agent.
4. Generate agent prompt files.
5. Write all files to `output/{name}/`.
6. Print a structured JSON result to stdout.

**Skipped (non-interactive mode):**
- Interactive questions
- Approval gates and user confirmation prompts
- CLI command files (`.claude/commands/`)
- Project scaffold files (README.md, CLAUDE.md)
- Scripts and utils directories
- Quality review step

The output is a lean, runnable agent folder: an orchestrator and prompt files. That is
all the execution service needs to run the agent.

---

## Step 1: Parse and Validate Input

Read the JSON input provided after "generate an agent from:".

Extract:
- `id` (string, optional -- when present, use as the output folder name instead of `name`)
- `name` (string, kebab-case)
- `description` (string)
- `samples` (array, may be empty)
- `computer_use` (boolean, default false)

Determine the output folder name: if `id` is present and non-empty, use `id`; otherwise use `name` (kebab-cased). Call this `folder_name` and use `output/{folder_name}/` as the output path throughout.

If `description` is missing or empty:
```json
{"error": "description is required"}
```
Print this and stop.

Normalize `name` to kebab-case if it is not already (lowercase, spaces to hyphens, remove special characters).

**Hold the parsed input in context. Do not print anything to the user.**

---

## Step 2: Analyze Complexity

**Read:** `forge/Prompts/02_Workflow_Architect.md`

Analyze the description to determine:

1. **Complexity level.** One of:
   - `simple`: The task is a single, bounded operation. One step, one prompt. Example: "Summarize this text in bullet points."
   - `multi_step`: The task has multiple phases that build on each other. 2-5 steps, 2-4 prompts. Example: "Research a topic and write a structured report."

2. **Steps.** The major phases of the work (2-5 for multi-step, 1 for simple). Each step should produce one clear artifact.

3. **Agent roster.** Which specialized agents are needed and what expertise each covers. Use the guidance in `forge/Prompts/02_Workflow_Architect.md`:
   - Simple: 1 agent.
   - Multi-step: 2-4 agents, each covering a distinct expertise area.
   - Not every step needs an agent. Mechanical steps (file writing, format conversion) need none.

4. **Input schema.** What inputs the agent needs when it runs. Infer from the description. Each input has a name and type (text, file, number, boolean).

5. **Output schema.** What the agent produces. Infer from the description. Each output has a name and type.

6. **Computer use.** Check each step's `computer_use` flag. Steps marked `computer_use: true` need desktop automation (browsers, GUI apps, clicking, typing on screen). Steps marked `computer_use: false` or plain string steps are CLI-only. Do not infer -- trust the caller's per-step flags.

**Save in context:**
```
complexity: simple | multi_step
steps: [{number, name, description, agent_name or null, computer_use: true|false}]
agents: [{name, role, expertise}]
input_schema: [{name, type, required}]
output_schema: [{name, type}]
computer_use: true | false (agent-level, true if any step has computer_use)
```

---

## Step 3: Generate the Agent Orchestrator

**Read:** `forge/utils/scaffold/agentic.md.template`

Generate `agentic.md` for the agent using the template as structural guide.

**Rules for API-mode orchestrators:**

- Remove the "After Each Step" approval protocol block entirely. The execution service does not wait for human approval.
- Remove approval gate markers (⏸). Replace any gate steps with direct save-and-continue steps.
- Keep the trigger commands section but use API-style triggers:
  - `run {agent-name}`
  - `execute {agent-name}`
- Each step should have: a purpose description, which prompt to read (if applicable), numbered workflow actions, and a save directive.
- The output structure should reference `output/{folder_name}/` paths.
- Include the Quality Checks table.
- If `computer_use` is true, include the Computer Use Configuration section from the template.

**Generated orchestrators must be self-contained.** No references to `forge/`, `forge/patterns/`, or `forge/examples/`. The agent folder must work without Agent Forge installed.

**Save:** `output/{folder_name}/agentic.md`

---

## Step 4: Generate Agent Prompts

**Read:** `forge/Prompts/03_Prompt_Writer.md`
**Read:** `forge/utils/scaffold/agent-prompt.md.template`

For complex or domain-specific prompts, also read `forge/Prompts/01_Senior_Prompt_Engineer.md` for craft guidance.

For each agent in the roster from Step 2:

1. Generate a complete prompt following the canonical template:
   - Context (role and expertise, 2-4 sentences, second person)
   - Input and Outputs (concrete, specific, measurable)
   - Quality Requirements (numerical thresholds where possible)
   - Clarifications (if the domain benefits from it)
   - Quality Examples (good and bad samples, if the domain benefits from it)
   - Rules (Always/Never, at least 3 each, actionable behaviors)
   - Actual Input (placeholders matching what the orchestrator passes)
   - Expected Workflow (numbered list, starts with input validation)

2. For steps with `computer_use: true`, generate a Computer Use Agent prompt based on `forge/Prompts/05_Computer_Use_Agent.md`. Adapt it to the specific desktop tasks that step needs to perform. Only steps explicitly marked with `computer_use: true` get a Computer Use Agent prompt -- CLI steps do not.

3. Calibrate prompts against quality samples if provided. For each sample:
   - Read the content and label.
   - Identify the patterns, structure, tone, and level of detail that characterize it.
   - Add Quality Requirements and Quality Examples to the relevant prompt(s) that encode these characteristics concretely. Do not copy the sample verbatim into the prompt. Extract what makes it good and express that as a rule or requirement.

4. Number prompt files sequentially: `01_{Agent_Name}.md`, `02_{Agent_Name}.md`, etc.

**Save:** `output/{folder_name}/agent/Prompts/{NN}_{Agent_Name}.md` for each agent

---

## Step 5: Write Output and Return JSON

Create the output directory structure:

```
output/{folder_name}/
├── agentic.md
└── agent/
    └── Prompts/
        ├── 01_{Agent_Name}.md
        └── ...
```

Write all files. Do not create scripts/, utils/, README.md, CLAUDE.md, or .claude/ directories. Those are for the interactive forge flow.

After writing all files, print a single JSON object to stdout. This is the only output the API reads.

```json
{
  "forge_path": "output/{folder_name}/",
  "forge_config": {
    "complexity": "simple | multi_step",
    "steps": 1,
    "prompts": ["01_Agent_Name.md"]
  },
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
- `forge_config.prompts`: List of generated prompt filenames in `agent/Prompts/`.
- `input_schema`: Inferred inputs the agent needs at runtime. Each item has `name`, `type` (one of: `text`, `file`, `number`, `boolean`), and `required` (boolean).
- `output_schema`: Inferred outputs the agent produces. Each item has `name` and `type`.

Print only this JSON object. No preamble, no summary, no explanation. The API parses this directly.

---

## Quality Standards

Generated agents must meet the same quality bar as agents created interactively through `agentic.md`.

**Orchestrators:**
- Each step has a purpose, numbered actions, and a save directive.
- Steps are atomic (one phase of work per step).
- The output structure diagram matches the actual files generated.
- No references to files outside the agent folder.

**Prompts:**
- All required sections present (Context, Input/Output, Quality Requirements, Rules, Actual Input, Expected Workflow).
- Context is specific (expertise, not generic "AI assistant").
- Quality Requirements use measurable thresholds.
- Rules are actionable behaviors, not aspirations.
- Actual Input placeholders match what the orchestrator passes at runtime.
- No emojis, no em-dashes, no AI attribution.
- Plain English throughout.

**Self-containment:**
- The generated agent folder must work without Agent Forge installed.
- No references to `forge/`, `forge/patterns/`, or `forge/examples/` inside the generated files.

---

## Clarifications

### Simple vs Multi-Step

When in doubt, prefer simple. A simple one-step agent with a well-written prompt delivers
more reliably than a multi-step agent with unnecessary phases.

Good signals for multi-step:
- The description implies distinct phases that each require different expertise (research, then write, then review).
- The output of one phase is the input to the next in a meaningful way.
- A single prompt would need to hold too much context at once.

Good signals for simple:
- The task is a bounded transformation (input X produces output Y).
- One area of expertise covers the whole task.
- The description fits in a single, clear prompt.

### Calibrating From Samples

Quality samples are calibration signals, not templates to copy. When a sample is provided:

- Identify structural patterns: Does it use specific section headers? A particular list format? A fixed length?
- Identify quality signals: What makes this sample good? Level of detail, citation style, specific terminology?
- Encode these as rules or Quality Requirements in the relevant prompt.

Do not add a "Quality Examples" section to a prompt that pastes the user's sample verbatim. Instead, derive the principles from the sample and express them as measurable criteria.

### Naming Conventions

Follow the same naming conventions as the full forge flow:
- Agent folder: when `id` is provided, use the `id`; otherwise kebab-case matching the `name` field.
- Prompt files: zero-padded with underscores (`01_Research_Analyst.md`).
- Step names in agentic.md: Title Case.
- Output files produced by the agent: lowercase with hyphens or numbered prefixes.

### Computer Use in API Mode

When `computer_use` is true, include a Computer Use Agent prompt based on
`forge/Prompts/05_Computer_Use_Agent.md`. Adapt the desktop task description from the
agent description. Include the Computer Use Configuration section in `agentic.md`.

List `05_Computer_Use_Agent.md` in `forge_config.prompts` in the JSON output.
