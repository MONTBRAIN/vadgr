# Pattern 08: Self-Similar Architecture

## What

The framework uses the same architectural patterns it teaches and generates. Its own structure IS the documentation. Users learn the patterns by using the framework.

## When to Use

- Frameworks that generate structures similar to their own
- Tools that create tools
- Systems that bootstrap other systems

## How Agent Forge Achieves This

| Agent Forge's Own Structure | What It Generates |
|---------------------------|-------------------|
| `forge/agentic.md` (orchestrator) | `output/{name}/agentic.md` (orchestrator) |
| `forge/Prompts/` (agent prompts) | `output/{name}/Prompts/` (agent prompts) |
| `.claude/commands/` (slash commands) | `output/{name}/.claude/commands/` (slash commands) |
| `README.md` + `CLAUDE.md` | `output/{name}/README.md` + `CLAUDE.md` |
| Approval gates ⏸ in its workflow | Approval gates ⏸ in generated workflows |

The framework doesn't just document the patterns. It demonstrates them. Every file in Agent Forge is a living example of the pattern it represents.

## The Meta-Principle

Any good framework should "eat its own dog food." If the architecture is worth generating for others, it's worth using yourself. This creates:

1. **Built-in documentation**, the framework IS the example
2. **Pattern validation**, if a pattern doesn't work for the framework, it won't work for users
3. **Consistency**, generated projects feel familiar because they match the framework's own structure
4. **Credibility**, users can inspect the framework to understand exactly what they'll get

## Key Convention

When adding a new pattern to the framework, apply it to the framework itself first. If it doesn't fit, reconsider whether it belongs in the pattern library.
