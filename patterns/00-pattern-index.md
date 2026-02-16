# Pattern Index

Reusable architectural patterns for agentic workflows. Each pattern is documented with what it is, when to use it, and how to implement it.

| # | Pattern | When to Use |
|---|---------|-------------|
| 01 | [Orchestrator](01-orchestrator-pattern.md) | Any multi-step process that needs coordination |
| 02 | [Specialized Agents](02-specialized-agents.md) | When steps require fundamentally different expertise |
| 03 | [Approval Gates](03-approval-gates.md) | Before expensive operations or at branching decisions |
| 04 | [Quality Loops](04-quality-loops.md) | When output quality is measurable and iteration can improve it |
| 05 | [Structured Output](05-structured-output.md) | Any workflow that produces multiple artifacts across steps |
| 06 | [CLI Commands](06-cli-commands.md) | Every workflow (enables both sequential and targeted execution) |
| 07 | [Template Scaffold](07-template-scaffold.md) | When each execution needs an identical starting structure |
| 08 | [Self-Similar Architecture](08-self-similar-architecture.md) | Frameworks that generate structures like their own |
| 09 | [Fix Command](09-fix-command.md) | Every workflow (built-in diagnostic and repair) |

## How to Apply

When designing a new workflow, scan this index and select the patterns that match your needs. Most workflows use patterns 01, 02, 03, and 06 as a baseline. Patterns 04, 05, and 07 are added based on specific requirements.
