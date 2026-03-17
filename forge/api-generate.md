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

**Steps format:** Steps can be plain strings (e.g. `"Research sources"`) or objects with per-step computer use (e.g. `{"name": "Create PR", "computer_use": true}`). When steps are objects, each step's `computer_use` flag indicates whether that specific step needs desktop automation. Steps without `computer_use` or plain strings default to CLI-only.

**Validation:**
- If `name` is missing or empty, derive it from the description: take the first 4-5 significant words, lowercase, hyphens between words.
- If `description` is missing or empty, write an error JSON to stdout and stop: `{"error": "description is required"}`.
- `samples` items may be strings (treated as content with no label) or objects with `content` and optional `label` fields.
- `computer_use` at the agent level is true if any step has `computer_use: true`. Do not infer -- trust the caller's flags.

---

## What This Orchestrator Does

This orchestrator runs the full forge generation process in non-interactive mode:

1. Parse and validate the input.
2. Analyze complexity and design architecture.
3. Generate project scaffold (README.md, CLAUDE.md, directories, commands).
4. Generate `agentic.md` orchestrator with step file references.
5. Generate agent prompt files and step definition files.
6. Generate workflow-specific scripts (if needed).
7. Quality review and return JSON result.

**Differences from interactive `agentic.md`:**
- No interactive questions (input comes as JSON).
- No approval gates or user confirmation prompts.
- All steps run sequentially without pausing.
- Output is a JSON object printed to stdout.

The output is a complete, self-contained agent folder that follows the same structure
and quality bar as agents created interactively through `agentic.md`.

---

## Step 1: Parse and Validate Input

**Step file:** `forge/steps/api-generate/step_01_parse-validate.md`

Read the step file and execute it.

---

## Step 2: Design Architecture

**Step file:** `forge/steps/api-generate/step_02_design-architecture.md`

Read the step file and execute it.

---

## Step 3: Generate Project Scaffold

**Step file:** `forge/steps/api-generate/step_03_generate-scaffold.md`

Read the step file and execute it.

---

## Step 4: Generate the Agent Orchestrator

**Step file:** `forge/steps/api-generate/step_04_generate-orchestrator.md`

Read the step file and execute it.

---

## Step 5: Generate Agent Prompts and Step Files

**Step file:** `forge/steps/api-generate/step_05_generate-agents.md`

Read the step file and execute it.

---

## Step 6: Generate Scripts

**Step file:** `forge/steps/api-generate/step_06_generate-scripts.md`

Read the step file and execute it. Skip if no scripts are needed.

---

## Step 7: Quality Review and Return JSON

**Step file:** `forge/steps/api-generate/step_07_quality-review.md`

Read the step file and execute it.

After all checks pass, print a single JSON object to stdout. This is the only output the API reads.

```json
{
  "forge_path": "output/{folder_name}/",
  "forge_config": {
    "complexity": "simple | multi_step",
    "steps": 3,
    "prompts": ["02_Agent_Name.md", "03_Agent_Name.md"]
  },
  "input_schema": [
    {
      "name": "topic",
      "type": "text",
      "required": true,
      "label": "Research Topic",
      "description": "The main subject to research and analyze",
      "placeholder": "e.g. AI market trends 2026"
    }
  ],
  "output_schema": [
    {
      "name": "report",
      "type": "markdown",
      "required": false,
      "label": "Research Report",
      "description": "Full analysis with findings and recommendations"
    }
  ]
}
```

**Field definitions:**

- `forge_path`: Relative path to the generated agent folder from the repo root.
- `forge_config.complexity`: `"simple"` or `"multi_step"`.
- `forge_config.steps`: Number of steps in the generated `agentic.md`.
- `forge_config.prompts`: List of generated prompt filenames in `agent/Prompts/` (excluding standard 00/01 prompts).
- `input_schema`: Inferred inputs the agent needs at runtime. Each item has:
  - `name`: snake_case key used in the inputs dict at runtime
  - `type`: one of `text`, `url`, `textarea`, `select`, `number`, `boolean`, `file`
  - `required`: boolean
  - `label`: Human-readable display name (e.g. "Research Topic" not "topic")
  - `description`: One-sentence helper text shown below the input field
  - `placeholder`: Example value shown inside the input (optional)
  - `options`: Array of strings for `select` type only (e.g. `["quick", "standard", "deep"]`)
  - `accept`: Array of accepted file extensions for `file`, `archive`, or `directory` inputs when obvious (e.g. `[".docx"]`, `[".csv"]`, `[".zip"]`)
  - `mime_types`: Array of accepted MIME types for artifact inputs when obvious
  - `max_size_mb`: Integer size limit for artifact inputs when obvious from the task
  - `output_schema`: Inferred outputs the agent produces. Each item has:
  - `name`: snake_case key that will appear in the run outputs dict
  - `type`: one of `text`, `markdown`, `json`, `url`, `number`, `boolean`
  - `label`: Human-readable display name for the output file/artifact
  - `description`: What this output contains

**Schema generation rules:**
- Infer inputs from the agent description -- if the agent researches a topic, it needs a `topic` input
- Every input that varies per run must appear in `input_schema`; hardcoded config does not
- Label must be title-cased and human-friendly (never snake_case)
- Description must be one concise sentence explaining the field
- Placeholder must be a realistic example value, not a generic hint like "Enter value here"
- For `select` inputs, always include the `options` array
- For artifact inputs (`file`, `archive`, `directory`), include `accept` and `mime_types` whenever the expected format is clear from the description. Examples: DOCX brief -> `[".docx"]`, CSV dataset -> `[".csv"]`, ZIP source bundle -> `[".zip"]`.
- For artifact inputs, include `max_size_mb` when the task implies large uploads should be bounded. Prefer a reasonable default like `10` if the input is a single document or dataset.
- Output names must match the JSON keys the agent will actually return at runtime

Print only this JSON object. No preamble, no summary, no explanation. The API parses this directly.

---

## Quality Standards

Generated agents must meet the same quality bar as agents created interactively through `agentic.md`.

**Orchestrators:**
- Thin format: step order + step file references (no inline instructions).
- Each step file has: purpose, prompt reference, inputs, workflow actions, required outputs.
- Step outputs go to `output/{run_id}/agent_outputs/` (inter-step context) and `output/{run_id}/user_outputs/` (user deliverables). The `{run_id}` is provided by the API executor at runtime to isolate concurrent runs. Output directories are created automatically before execution starts.
- No references to files outside the agent folder.

**Prompts:**
- All required sections present (Context, Input/Output, Quality Requirements, Rules, Actual Input, Expected Workflow).
- Context is specific (expertise, not generic "AI assistant").
- Quality Requirements use measurable thresholds.
- Rules are actionable behaviors, not aspirations.
- Actual Input placeholders match what the step file passes at runtime.
- No emojis, no em-dashes, no AI attribution.
- Plain English throughout.

**Self-containment:**
- The generated agent folder must work without Agent Forge installed.
- No references to `forge/`, `forge/patterns/`, or `forge/examples/` inside the generated files.

**Project completeness:**
- README.md, CLAUDE.md, agentic.md all present.
- .claude/commands/ with one command per step, master start command, and fix command.
- agent/Prompts/ with all agents, Workflow Fixer (00), and Senior Prompt Engineer (01).
- agent/steps/ with one step file per workflow step.
- agent/scripts/ with src/, tests/, requirements.txt, README.md.
- agent/utils/ with code/ and docs/.
- output/ directory exists (scaffold creates base; at runtime the API creates output/{run_id}/inputs/, output/{run_id}/agent_outputs/, output/{run_id}/user_outputs/, and output/{run_id}/agent_logs/ per run).

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

### Step File Architecture

Generated agents use a thin orchestrator + step files pattern:
- `agentic.md` contains step order and references to step files in `agent/steps/`
- Each step file is self-contained with: prompt reference, inputs, workflow, required outputs
- Agent outputs (inter-step context): `output/{run_id}/agent_outputs/step_{NN}_agent_output.md`
- User outputs (deliverables): `output/{run_id}/user_outputs/step_{NN}/`

### Calibrating From Samples

Quality samples are calibration signals, not templates to copy. When a sample is provided:

- Identify structural patterns: Does it use specific section headers? A particular list format? A fixed length?
- Identify quality signals: What makes this sample good? Level of detail, citation style, specific terminology?
- Encode these as rules or Quality Requirements in the relevant prompt.

Do not add a "Quality Examples" section to a prompt that pastes the user's sample verbatim. Instead, derive the principles from the sample and express them as measurable criteria.

### Naming Conventions

Follow the same naming conventions as the full forge flow:
- Agent folder: when `id` is provided, use the `id`; otherwise kebab-case matching the `name` field.
- Prompt files: zero-padded with underscores (`02_Research_Analyst.md`). 00 and 01 are reserved for standard prompts.
- Step files: `step_{NN}_{step-name}.md` (e.g., `step_01_research-sources.md`).
- Step names in agentic.md: Title Case, human-readable.
- Output files produced by the agent at runtime: lowercase with hyphens or numbered prefixes.

### Computer Use in API Mode

When `computer_use` is true, include a Computer Use Agent prompt based on
`forge/Prompts/05_Computer_Use_Agent.md`. Adapt the desktop task description from the
agent description. Include the Computer Use Configuration section in `agentic.md`.
Generate execution commands (execute-workflow, pause-execution, resume-execution).

### Templates Are Mandatory

**ALWAYS** start from the scaffold templates in `forge/utils/scaffold/`. Never write an
`agentic.md`, `README.md`, `CLAUDE.md`, agent prompt, or command file from scratch. The
templates exist to enforce consistency. Fill in the placeholders, adapt the structure, but
keep the skeleton.

### Output Folder Separation

Step results (the files created when the agent runs) go in the agent's `output/` directory.
The scaffold creates an empty `output/` directory. At runtime, the API creates per-run directories:
- `output/{run_id}/inputs/` holds staged runtime input artifacts
- `output/{run_id}/agent_outputs/` holds inter-step context files (e.g., `step_01_agent_output.md`)
- `output/{run_id}/user_outputs/` holds user-facing deliverables organized by step (e.g., `step_01/report.pdf`)
- `output/{run_id}/agent_logs/` holds run and step JSONL logs

These directories are created automatically by the execution service before the agent runs, so agents don't need to create them.

Workflow definition files (agentic.md, agent/, .claude/, README.md, CLAUDE.md) live at
`output/{folder_name}/`. This separation ensures step results never get mixed with the
workflow structure.
