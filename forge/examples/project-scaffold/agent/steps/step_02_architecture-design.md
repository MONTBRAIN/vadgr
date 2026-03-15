# Step 2: Architecture Design

**Purpose:** Design the project folder structure, component breakdown, and dependency map.

**Prompt:** `agent/Prompts/01_Software_Architect.md`

---

## Inputs
- Project brief from Step 1
- Previous step context: `output/agent_outputs/step_01_agent_output.md`

---

## Workflow

1. Review the project brief from Step 1
2. Identify the idiomatic project structure for the chosen language/framework
3. Design the folder tree following language conventions (e.g., `src/` for Go, `lib/` for Ruby, `src/` for TypeScript)
4. Break the project into components based on the listed features
5. For each component, define: name, responsibility, file path
6. Map dependencies between components
7. Identify the main entry point for the project
8. Present the complete architecture document to the user:

```
Project Architecture: {project-name}

Language/Framework: {language}

Folder Structure:
{folder tree}

Components:
| # | Name | Responsibility | File Path |
|---|------|---------------|-----------|
| 1 | {name} | {responsibility} | {path} |
| ... | ... | ... | ... |

Dependencies:
{component} --> {component}
...

Entry Point: {file path}
```

**Wait for user approval. If changes requested, revise and present again.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/agent_outputs/step_02_agent_output.md`
- Complete architecture document (folder tree, components table, dependency map, entry point)
- Approved language/framework conventions used

### User Output (deliverables)
None. This step produces inter-step context only.

---

## Quality Check

- Folder structure follows language conventions?
- All components from the feature list defined?
- Dependencies mapped between components?
- Entry point identified?
- Architecture approved by user?
- Agent output saved to `output/agent_outputs/step_02_agent_output.md`?
