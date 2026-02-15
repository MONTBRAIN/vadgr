# Pattern 03: Approval Gates

## What

Pause points (marked with ⏸) where the human must review and approve before the workflow continues. They create a human-in-the-loop checkpoint at critical decision moments.

## When to Use

- After generation steps where quality matters (e.g., after generating a roadmap, architecture, or rubric)
- Before expensive operations (e.g., before generating 10 lesson files)
- At branching decisions (e.g., "automatic tests or manual validation?")
- When the output of one step fundamentally shapes all subsequent steps

## Implementation

In `agentic.md`, a gated step looks like:

```markdown
## Step N: {Step Name} ⏸

{step instructions...}

**Present the output to the user.**
**Wait for approval. If changes requested, iterate.**

**Save:** {files}
```

The approval protocol (defined once in the "After Each Step" section):

```markdown
1. Show output to the user
2. Ask: "Does this look good? Any changes needed?"
3. Wait for user approval
   - If changes requested → Modify and show again
   - If approved → Continue
4. Save files
5. Confirm: "Saved"
```

## Key Conventions

1. Gates are marked with ⏸ in the step header
2. The workflow diagram shows which steps have gates
3. Gates are **iterative**, the user can request changes multiple times
4. Only proceed after explicit approval
5. Every workflow should have at least one gate

## Placement Guide

| Scenario | Gate? |
|----------|-------|
| After generating a plan/architecture | Yes |
| After generating content (lessons, docs, code) | Depends on volume |
| Before deleting or overwriting | Yes |
| Between independent generation steps | No |
| At the final delivery step | Yes |
