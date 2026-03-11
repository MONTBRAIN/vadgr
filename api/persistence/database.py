"""SQLite connection and schema management."""

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'agent',
    status TEXT NOT NULL DEFAULT 'creating',
    forge_path TEXT DEFAULT '',
    steps TEXT DEFAULT '[]',
    samples TEXT DEFAULT '[]',
    input_schema TEXT DEFAULT '[]',
    output_schema TEXT DEFAULT '[]',
    computer_use INTEGER DEFAULT 0,
    forge_config TEXT DEFAULT '{}',
    provider TEXT NOT NULL DEFAULT 'claude_code',
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_nodes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    config TEXT DEFAULT '{}',
    position_x REAL DEFAULT 0,
    position_y REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_nodes_project ON project_nodes(project_id);

CREATE TABLE IF NOT EXISTS project_edges (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL REFERENCES project_nodes(id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES project_nodes(id) ON DELETE CASCADE,
    source_output TEXT NOT NULL,
    target_input TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edges_project ON project_edges(project_id);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON runs(agent_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES project_nodes(id),
    status TEXT NOT NULL DEFAULT 'pending',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    logs TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_run ON agent_runs(run_id);
"""


class Database:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")

    async def create_tables(self):
        await self._conn.executescript(SCHEMA)

    async def disconnect(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn
