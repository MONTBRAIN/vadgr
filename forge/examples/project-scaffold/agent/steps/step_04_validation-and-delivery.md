# Step 4: Validation and Delivery

**Purpose:** Verify completeness and deliver the finished project scaffold.

**Prompt:** None

---

## Inputs
- Architecture document from Step 2: `output/agent_outputs/step_02_agent_output.md`
- Generated files manifest from Step 3: `output/agent_outputs/step_03_agent_output.md`
- Generated project directory: `output/{project-name}/`

---

## Workflow

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

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/agent_outputs/step_04_agent_output.md`
- Validation results (pass/fail for each check)
- Final file tree
- Any issues found and fixed

### User Output (deliverables)
Save to: `output/{project-name}/`
- Validated, complete project scaffold (all files from Step 3, with any fixes applied)

---

## Quality Check

- Every component has a source file and at least one test?
- No empty files?
- No unfilled README.md placeholders?
- All issues found during validation fixed?
- Final summary presented and approved by user?
- Agent output saved to `output/agent_outputs/step_04_agent_output.md`?
