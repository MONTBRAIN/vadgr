# Step 3: Code Generation

**Purpose:** Generate all starter code files based on the approved architecture.

**Prompt:** `agent/Prompts/02_Code_Generator.md`

---

## Inputs
- Approved architecture document from Step 2
- Previous step context: `output/agent_outputs/step_02_agent_output.md`
- Project brief from Step 1: `output/agent_outputs/step_01_agent_output.md`

---

## Workflow

1. Review the approved architecture document from Step 2
2. Copy the template from `templates/project-template/` into `output/{project-name}/`
3. Fill in the template README.md with the project name and description
4. Generate the main entry point file with proper imports and a minimal working structure
5. For each component in the architecture:
   a. Create the file at the specified path
   b. Add proper imports/includes
   c. Define types, interfaces, or structs as appropriate
   d. Add function stubs with documentation comments
   e. Include minimal inline documentation
6. For each component, generate a corresponding test file in `tests/`:
   a. Import the component
   b. Write at least one test stub per public function
7. Generate language-appropriate config files (e.g., `go.mod`, `package.json`, `Gemfile`)
8. Generate a `.gitignore` appropriate for the language/framework

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/agent_outputs/step_03_agent_output.md`
- List of all files generated with their paths
- Entry point file path
- Config files generated
- Count of source files and test files

### User Output (deliverables)
Save to: `output/{project-name}/`
- All generated source files under `src/`
- All generated test files under `tests/`
- README.md (filled in from template)
- Language-appropriate config files
- `.gitignore`

---

## Quality Check

- Every component from the architecture has a source file?
- Every component has at least one test stub?
- Entry point file generated?
- README.md has no unfilled placeholders?
- Config files and .gitignore present?
- Agent output saved to `output/agent_outputs/step_03_agent_output.md`?
