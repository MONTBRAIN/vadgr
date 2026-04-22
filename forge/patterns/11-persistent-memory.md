# Pattern 11: Persistent Memory

Agents can remember facts, preferences, and context across runs using persistent memory files stored at `FORGE_HOME/memory/`.

## When to use

- The agent works with the same context repeatedly (e.g., same repo, same user profile)
- Re-analyzing the context each run wastes time and tokens
- The agent benefits from learning across runs (getting faster, more accurate)
- Computer use steps benefit from remembered UI descriptions so the agent can locate elements in screenshots with fewer reasoning rounds

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

## CUA hints

Computer use agents can keep a natural-language cheat sheet of where things live in the apps they control. The agent still finds elements visually in each screenshot; the remembered description only primes attention so the search is faster and more accurate.

### How to write a hint

Every hint answers three things:

1. **Container** -- the named visible region the element is inside (e.g. "VS Code editor tab bar", "Chrome top toolbar", "Activity bar on the far left")
2. **Zone within that container** -- top / middle / bottom, left / center / right, or sequential position (first, last, nth)
3. **Visual feature** -- one or two distinguishing details ("green play triangle", "gear icon", "three-dot menu")

```python
write_memory("my-agent", key="cua-hints", content="""
# VS Code
- run tests: editor tab bar, right side, small play triangle
- settings: activity bar on the far left, bottom, gear icon
- terminal panel: bottom strip of the window when open, Ctrl+` toggles

# Chrome
- address bar: top toolbar, between the back/forward arrows and the profile avatar
- new tab: immediately right of the last open tab, small plus
""")
```

Steps that use computer use should read `cua-hints` at the start and splice the relevant snippets into the prompt alongside the first screenshot. These are prompt-time hints for the LLM, not parameters to any engine call.

### Do / don't

Zones of a **container** are robust. Zones of the **screen** are not.

- DO: "editor tab bar, right side, small play triangle"
- DON'T: "run button: top-right" (unscoped -- top-right of what?)

- DO: "activity bar, bottom, gear icon"
- DON'T: "settings: bottom-left corner" (unscoped, breaks when the window is not maximized)

- DO: "top toolbar, between the back/forward arrows and the profile avatar"
- DON'T: "address bar: middle of screen" (breaks on multi-monitor, floating windows, popups)

Anti-patterns that reintroduce the old pixel-cache trap and must be avoided:

- Absolute pixels: `(1820, 48)`
- Fractions of the screen: `top 20%`, `right 10%`
- Fixed pixel offsets: `50px from the right edge`
- Screen-anchored directions: `right of the screen`, `bottom of the monitor`

### Lifecycle

- **Written by the agent**, not the human -- the agent phrases the hint the way it will recognize it later.
- **Written at step end** after a successful interaction, as a description of how it found the element.
- **Read at step start**, spliced verbatim into the prompt context.
- **Self-healing**: if a hint is stale (element not where it says after 2 attempts), the agent overwrites it with the corrected landmark.

## Constraints

- Max 30 lines per memory file (keeps token cost low)
- Memory is overwritten each run, not appended (prevents unbounded growth)
- Memory is per-agent, not shared between agents
- Human-editable: users can open and modify memory files directly
