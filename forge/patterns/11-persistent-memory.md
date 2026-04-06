# Pattern 11: Persistent Memory

Agents can remember facts, preferences, and context across runs using persistent memory files stored at `FORGE_HOME/memory/`.

## When to use

- The agent works with the same context repeatedly (e.g., same repo, same user profile)
- Re-analyzing the context each run wastes time and tokens
- The agent benefits from learning across runs (getting faster, more accurate)
- Computer use steps benefit from consistent element hints for spatial cache

## How it works

Memory files are markdown with YAML frontmatter stored at `FORGE_HOME/memory/{agent-name}/{key}.md`. Any CLI provider (Claude Code, Codex, Gemini) can read markdown naturally.

### File format

```markdown
---
agent: my-agent
key: global
updated: 2026-04-05T12:00:00Z
---

- User prefers dark theme
- Default output format: PDF
```

### Directory structure

```
FORGE_HOME/memory/
  my-agent/
    global.md          -- agent-wide knowledge (default key)
    custom-key.md      -- optional scoped memory
```

### Usage in steps

```python
from forge.scripts.src.memory import read_memory, write_memory

# Read at the start of a step
previous = read_memory("my-agent")

# Write at the end of a step
write_memory("my-agent", content="- learned: user prefers pytest over unittest")
```

### Per-repo memory

Agents that work across multiple repos can scope memory by repo path:

```python
from forge.scripts.src.memory import read_memory, write_memory, repo_key

key = repo_key("/home/user/my-project")  # -> "repo-home-user-my-project"
context = read_memory("software-engineer", key=key)
write_memory("software-engineer", key=key, content="- Stack: FastAPI + React")
```

## CUA element hints

Agents that use computer use can store standardized element hints so the spatial cache gets consistent keys across runs. This makes repeated clicks faster via the muscle memory system.

```python
write_memory("my-agent", key="cua-hints", content="""
# VS Code
- run tests: "run tests button"
- terminal: "terminal panel"

# Chrome
- address bar: "url bar"
""")
```

Steps that use computer use should read `cua-hints` and use the exact strings as `element_hint` in click/navigate calls.

## Constraints

- Max 30 lines per memory file (keeps token cost low)
- Memory is overwritten each run, not appended (prevents unbounded growth)
- Memory is per-agent, not shared between agents
- Human-editable: users can open and modify memory files directly
