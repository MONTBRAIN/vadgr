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

**Purpose:** Gather all requirements needed to scaffold a new code project.

**On trigger, ask ONE question at a time. Wait for each response.**

Question 1:
```
What is the project name? (Use kebab-case, e.g., "my-web-app")
```

Question 2:
```
What language and/or framework should this project use?
(e.g., "Python with FastAPI", "Go", "TypeScript with React", "Ruby on Rails")
```

Question 3:
```
Describe the project in 2-3 sentences. What does it do?
```

Question 4:
```
What are the key features or components? List 3-5 main features this project needs.
```

Question 5:
```
Who is the target audience or user of this project?
(e.g., "developers consuming an API", "end users of a web app", "CLI tool users")
```

**After all questions answered:** Compile a project brief summarizing the name, language/framework, description, features, and target audience. Present it to the user for confirmation.

**Save:** Hold project brief in context for subsequent steps.

---

## Step 2: Architecture Design ⏸

**Purpose:** Design the project folder structure, component breakdown, and dependency map.

**Read:** `Prompts/1. Software Architect.md`

**Workflow:**

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

## Step 3: Code Generation

**Purpose:** Generate all starter code files based on the approved architecture.

**Read:** `Prompts/2. Code Generator.md`

**Workflow:**

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

**Save:** All generated files into `output/{project-name}/`

---

## Step 4: Validation and Delivery ⏸

**Purpose:** Verify completeness and deliver the finished project scaffold.

**Workflow:**

1. Read the architecture document from Step 2
2. List all files generated in `output/{project-name}/`
3. Verify completeness:
   - Every component in the architecture has a corresponding source file
   - Every component has at least one test file
   - The entry point file exists
   - README.md is filled in (no unfilled placeholders)
   - Config files are present
   - .gitignore is present
4. Verify code quality:
   - All files have proper imports
   - No empty files (every file has at least a stub)
   - Naming follows language conventions
5. If any issues found, fix them before presenting
6. Present the final summary to the user:

```
Project "{project-name}" is ready!

Location: output/{project-name}/

Files created:
{complete file tree}

Components: {count}
Test files: {count}
Entry point: {entry point path}

To get started:
1. cd output/{project-name}/
2. {language-specific setup command}
3. {language-specific run command}
```

**Wait for user approval.**

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
