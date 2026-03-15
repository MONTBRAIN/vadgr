# Project Scaffolding, Workflow Orchestrator

## Trigger Commands

- `scaffold a new project`
- `create a new code project`
- `start project scaffolding`
- `/start-project`

---

## Workflow Overview

```
Step 1              Step 2              Step 3              Step 4
Project        -->  Architecture   -->  Code           -->  Validation &
Definition          Design              Generation          Delivery
                    ⏸                                       ⏸
```

---

## Step 1: Project Definition

**Step file:** `agent/steps/step_01_project-definition.md`

Read the step file and execute it. Gather all project requirements from the user by asking one question at a time: project name, language/framework, description, features, and target audience.

---

## Step 2: Architecture Design ⏸

**Step file:** `agent/steps/step_02_architecture-design.md`

Read the step file and execute it. Design the project folder structure, component breakdown, and dependency map based on the project brief from Step 1. Present to user for approval.

---

## Step 3: Code Generation

**Step file:** `agent/steps/step_03_code-generation.md`

Read the step file and execute it. Generate all starter code files, tests, and config files based on the approved architecture from Step 2.

---

## Step 4: Validation and Delivery ⏸

**Step file:** `agent/steps/step_04_validation-and-delivery.md`

Read the step file and execute it. Verify all generated files match the architecture, fix any issues, and present the final project summary to the user.

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

## Output Structure

```
output/{project-name}/
├── README.md
├── src/
│   ├── {entry-point}
│   └── {component files...}
├── tests/
│   └── {test files...}
├── {config files...}
└── .gitignore
```

---

## Quality Checks

| Step | Check |
|------|-------|
| 01 | Project name, language, description, features, and audience defined? User confirmed? |
| 02 | Folder structure follows language conventions? Components identified? Dependencies mapped? User approved? |
| 03 | All components generated? Entry point exists? Tests created? Config files present? Imports correct? |
| 04 | All architecture components have files? No empty files? No unfilled placeholders? User approved? |
