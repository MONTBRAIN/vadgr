# Step 1: Project Definition

**Purpose:** Gather all requirements needed to scaffold a new code project.

**Prompt:** None

---

## Inputs
- User trigger command (e.g., `/start-project`, `scaffold a new project`)

---

## Workflow

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

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/agent_outputs/step_01_agent_output.md`
- Project name (kebab-case)
- Language/framework choice
- Project description (2-3 sentences)
- Key features list (3-5 items)
- Target audience
- Full compiled project brief

### User Output (deliverables)
None. This step produces inter-step context only.

---

## Quality Check

- All five questions answered?
- Project brief confirmed by user?
- Agent output saved to `output/agent_outputs/step_01_agent_output.md`?
