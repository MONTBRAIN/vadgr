# Pattern 01: Orchestrator

## What

A single `agentic.md` file that defines a complete step-by-step workflow. It is the central coordination point, where every step, gate, and output is described in one document.

## When to Use

Any multi-step process that needs coordination between different phases of work.

## Structure

```markdown
# {Workflow Name}, Workflow Orchestrator

## Trigger Commands
- commands that start the workflow

## Workflow Overview
- ASCII diagram showing step flow and gates

## Step 1: {Name}
- Purpose, agent reference, actions, output

## Step N: {Name}
...

## After Each Step
- Approval protocol

## Output Structure
- Folder/file tree

## Quality Checks
- Table mapping steps to verification criteria
```

## Key Conventions

1. Steps are numbered sequentially (Step 1, Step 2, ...)
2. Each step references its agent prompt file (if applicable): `Read: Prompts/N. Agent Name.md`
3. Steps end with a **Save** action describing what gets persisted
4. Approval gates are marked with ⏸
5. The file includes an output structure diagram showing the final folder tree
6. A quality checks table at the end maps each step to its verification criteria

## Example

A learning workflow orchestrator:
```
Step 1: Ask topic → Step 2: Generate roadmap ⏸ → Step 3: Approve → Step 4: Generate lessons → Step 5: Create exercises → Step 6: Present summary
```

Each step reads its specialized agent prompt, produces specific outputs, and pauses at gate points for human review.
