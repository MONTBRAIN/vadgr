# Pattern 07: Template Scaffold

## What

A template directory that gets copied as-is for each new task or workflow execution. This ensures every execution starts from an identical, pre-configured base.

## When to Use

- When each workflow execution needs an identical starting structure
- When the starting structure includes pre-configured dependencies, files, or boilerplate
- When consistency across executions matters

## Structure

```
utils/
└── {template-name}/
    ├── package.json        # Pre-configured dependencies
    ├── src/
    │   ├── main.tsx
    │   └── App.tsx
    └── config files...
```

## Implementation

In `agentic.md`, the template copy step:

```markdown
## Step N: Initialize Task

1. Copy template to task directory:
   ```
   cp -r forge/utils/{template-name}/ output/{task-id}/
   ```
2. Initialize fresh state:
   ```
   cd output/{task-id}/
   rm -rf .git
   git init
   git add .
   git commit -m "Initial commit from template"
   ```
3. Customize task-specific files (if needed)
```

## Key Conventions

1. Templates are **immutable**, never modify the template directory during execution
2. Copy the entire template, then customize the copy
3. Initialize fresh git history in the copy (not inherited from template)
4. No new dependencies, everything needed is pre-installed in the template
5. Templates live in `utils/` within the workflow's core directory

## When NOT to Use

- If the workflow only produces markdown files (no template needed, just create them)
- If every execution has a completely different structure
- If the "template" would be just one or two files (overkill)
