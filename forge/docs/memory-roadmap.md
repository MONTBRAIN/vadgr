# Memory System Roadmap

## Phase 1: Markdown files (current)

File-based persistent memory at `FORGE_HOME/memory/{agent}/{key}.md`.

- Markdown + YAML frontmatter format
- CLI-agnostic (works with Claude Code, Codex, Gemini)
- Human readable and editable
- Max 30 lines per file (token cost control)
- Overwrite strategy (no unbounded growth)
- Computer use agents can store CUA hints (natural-language UI cheat sheets) under the `cua-hints` key

### Interface

```python
from forge.scripts.src.memory import read_memory, write_memory, list_memories, clear_memory, repo_key

content = read_memory("agent-name")
write_memory("agent-name", content="- learned fact")
write_memory("agent-name", key=repo_key("/path/to/repo"), content="- stack: FastAPI")
write_memory("agent-name", key="cua-hints", content="# App\n- run button: top right, play icon")
memories = list_memories("agent-name")
clear_memory("agent-name")
```

### Limitations

- No search (must know exact key)
- Linear scan of files
- No semantic matching
- Max ~30 lines per file

---

## Phase 2: SQLite

Replace `.md` file read/write with SQLite queries. Same `memory.py` interface, different backend.

### Storage

Single file: `FORGE_HOME/memory.db`

### Schema

```sql
CREATE TABLE memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL,
    key         TEXT NOT NULL DEFAULT 'global',
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(agent_name, key)
);

CREATE INDEX idx_memories_agent ON memories(agent_name);
```

### Why

- Full text search via SQLite FTS5: `SELECT * FROM memories WHERE content MATCH 'pytest'`
- Handles hundreds of memories without file system overhead
- Still zero external dependencies (sqlite3 is built into Python)
- Still local, no network calls, no external services
- Single file backup (`memory.db`)

### Migration

```python
# Read all .md files, insert into SQLite, remove .md files
for agent_dir in MEMORY_DIR.iterdir():
    for md_file in agent_dir.glob("*.md"):
        meta, body = _parse_frontmatter(md_file.read_text())
        db.execute("INSERT INTO memories ...", (meta["agent"], meta["key"], body, meta["updated"]))
        md_file.unlink()
```

### When to upgrade

When any of these become true:
- An agent has 50+ memory files
- Users request search across memories ("what did I learn about React projects?")
- Memory management becomes a pain (too many files in `FORGE_HOME/memory/`)

---

## Phase 3: sqlite-vec (vector search)

Add local embeddings for semantic similarity search. Still SQLite, still local, still free.

### Dependencies

- `sqlite-vec`: SQLite extension for vector operations
- `sentence-transformers` with `all-MiniLM-L6-v2` model (~80MB, runs on CPU)

### Schema addition

```sql
CREATE VIRTUAL TABLE memory_vectors USING vec0(
    memory_id INTEGER,
    embedding FLOAT[384]
);
```

### New interface method

```python
def search_memory(agent_name: str, query: str, top_k: int = 5) -> list[dict]:
    """Semantic search across memories. Returns top_k most relevant."""
    embedding = model.encode(query)
    results = db.execute("""
        SELECT m.*, v.distance
        FROM memory_vectors v
        JOIN memories m ON m.id = v.memory_id
        WHERE m.agent_name = ?
        ORDER BY v.distance
        LIMIT ?
    """, (agent_name, top_k))
    return results
```

### Why

- "Find memories relevant to this task" without exact key matching
- Agents get smarter with every run
- Cross-pollination: lessons from one context help with similar contexts
- Still fully local, no API calls, no external services, no charges

### When to upgrade

When any of these become true:
- An agent accumulates 50+ memories and needs to recall relevant ones
- Simple key-based lookup isn't finding the right memories
- Users want "smart recall" where the agent automatically knows what's relevant

---

## Design principles (all phases)

1. **Same interface** -- `read_memory`, `write_memory`, `list_memories`, `clear_memory` never change. Backend swaps transparently.
2. **Local only** -- no external services, no API keys, no charges. Everything on the user's machine.
3. **CLI-agnostic** -- works identically with Claude Code, Codex, Gemini, or any future provider.
4. **Human editable** -- users can always inspect and modify memories (even in SQLite via CLI tools).
5. **Token-conscious** -- memories are compact, selectively loaded, never dumped wholesale into context.
