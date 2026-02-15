# Pattern 02: Specialized Agents

## What

Decompose expertise into separate prompt files in an `agent/Prompts/` directory. Each agent is a constrained expert that handles one area of knowledge.

## When to Use

When different steps in the workflow require fundamentally different expertise or constraints. For example, a "Research Analyst" and an "Academic Writer" need different skills, tone, and rules.

## Structure

```
agent/
└── Prompts/
    ├── 01_Agent_Name.md
    ├── 02_Agent_Name.md
    └── 03_Agent_Name.md
```

Each prompt follows a canonical template:
```markdown
# {Agent Name}
## Context          , Role and expertise
## Input and Outputs , What it receives and produces
## Quality Requirements , Standards to meet
## Rules            , Always/Never lists
## Actual Input     , Placeholders for runtime data
## Expected Workflow , Step-by-step process
```

## Key Conventions

1. Files are zero-padded and use underscores to indicate the order they are first used: `01_Agent_Name.md`
2. Each agent is **self-contained**, it should work without knowledge of other agents
3. Agents are organized by **expertise area**, not by step (one agent can serve multiple steps)
4. The canonical template has 7 sections that must all be present

## Sizing Guide

| Workflow Steps | Typical Agents |
|----------------|---------------|
| 3-5 steps | 1-2 agents |
| 5-7 steps | 2-3 agents |
| 7-9 steps | 3-4 agents |

## Anti-Patterns

- **One agent per step**, too granular. Agents should map to expertise, not steps.
- **One mega-agent**, too broad. If an agent needs to be expert in unrelated domains, split it.
- **Overlapping responsibilities**, two agents that can both do the same thing creates confusion.
