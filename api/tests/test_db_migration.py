"""The 0.4.4 schema move, against databases that carry real rows.

A migration tested only against an empty database tests the DDL and not the
data, so the fixture here is the previous schema verbatim with rows in all five
tables that leave.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from api.persistence.database import BACKUP_SUFFIX, Database


# The schema as it shipped at 0.4.3, copied rather than imported: the point is
# to migrate from what is on an owner's disk, and importing the current one
# would test the migration against its own output.
_SCHEMA_0_4_3 = """
CREATE TABLE agents (
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
    model TEXT NOT NULL DEFAULT 'claude-opus-5',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE project_nodes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    config TEXT DEFAULT '{}',
    position_x REAL DEFAULT 0,
    position_y REAL DEFAULT 0
);

CREATE INDEX idx_nodes_project ON project_nodes(project_id);

CREATE TABLE project_edges (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_node_id TEXT NOT NULL REFERENCES project_nodes(id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES project_nodes(id) ON DELETE CASCADE,
    source_output TEXT NOT NULL,
    target_input TEXT NOT NULL
);

CREATE INDEX idx_edges_project ON project_edges(project_id);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    provider TEXT DEFAULT NULL,
    model TEXT DEFAULT NULL,
    log_path TEXT DEFAULT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_runs_project ON runs(project_id);
CREATE INDEX idx_runs_agent ON runs(agent_id);

CREATE TABLE agent_runs (
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

CREATE INDEX idx_agent_runs_run ON agent_runs(run_id);

CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    machine_name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    paired_at TEXT NOT NULL,
    last_seen TEXT
);

CREATE INDEX idx_devices_token_hash ON devices(token_hash);
"""

# The database as it was before `log_path`, `provider` and `model` were added by
# the three ad-hoc ALTERs. The rebuild SELECTs all three by name, which is why
# those ALTERs run first and stay.
_SCHEMA_PRE_COLUMNS = """
CREATE TABLE agents (
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
    model TEXT NOT NULL DEFAULT 'claude-opus-5',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    started_at TEXT,
    completed_at TEXT
);
"""


def _seed_0_4_3(path) -> None:
    """A database with rows in every table that leaves."""
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_0_4_3)
    now = "2026-01-01T00:00:00"
    conn.execute(
        "INSERT INTO agents (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("agent-1", "Research", now, now),
    )
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("proj-1", "Pipeline", now, now),
    )
    conn.execute(
        "INSERT INTO project_nodes (id, project_id, agent_id) VALUES (?, ?, ?)",
        ("node-1", "proj-1", "agent-1"),
    )
    conn.execute(
        "INSERT INTO project_nodes (id, project_id, agent_id) VALUES (?, ?, ?)",
        ("node-2", "proj-1", "agent-1"),
    )
    conn.execute(
        """INSERT INTO project_edges
           (id, project_id, source_node_id, target_node_id, source_output, target_input)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("edge-1", "proj-1", "node-1", "node-2", "out", "in"),
    )
    conn.execute(
        """INSERT INTO runs (id, project_id, agent_id, status, inputs, provider, model)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("run-owned", None, "agent-1", "completed", json.dumps({"topic": "AI"}),
         "claude_code", "claude-opus-5"),
    )
    conn.execute(
        "INSERT INTO runs (id, project_id, agent_id, status) VALUES (?, ?, ?, ?)",
        ("run-orphan", None, None, "failed"),
    )
    conn.execute(
        "INSERT INTO runs (id, project_id, agent_id, status) VALUES (?, ?, ?, ?)",
        ("run-project", "proj-1", None, "queued"),
    )
    conn.execute(
        "INSERT INTO agent_runs (id, run_id, node_id) VALUES (?, ?, ?)",
        ("ar-1", "run-owned", "node-1"),
    )
    conn.execute(
        """INSERT INTO devices (id, machine_name, token_hash, paired_at)
           VALUES (?, ?, ?, ?)""",
        ("dev-1", "Pixel", "hash-1", now),
    )
    conn.commit()
    conn.close()


def _names(path, kind="table") -> list[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
            (kind,),
        ).fetchall()
    finally:
        conn.close()
    return sorted(r[0] for r in rows)


async def _migrate(path) -> Database:
    db = Database(str(path))
    await db.connect()
    await db.create_tables()
    return db


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "agent_forge.db"
    _seed_0_4_3(path)
    return path


class TestPopulatedDatabase:

    @pytest.mark.asyncio
    async def test_a_run_takes_its_agents_name_as_its_title(self, seeded):
        db = await _migrate(seeded)
        try:
            row = await db.conn.execute_fetchall(
                "SELECT title FROM runs WHERE id = 'run-owned'"
            )
            assert row[0]["title"] == "Research"
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_an_orphaned_run_takes_the_empty_string(self, seeded):
        """Its agent was already gone, so there is no name to carry."""
        db = await _migrate(seeded)
        try:
            row = await db.conn.execute_fetchall(
                "SELECT title FROM runs WHERE id = 'run-orphan'"
            )
            assert row[0]["title"] == ""
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_an_orphan_reaches_the_wire_as_an_empty_agent_name(self, seeded):
        """The shipped phone renders an empty name as the run id, exactly as it
        rendered a null one."""
        from api.persistence.repositories import RunRepository

        db = await _migrate(seeded)
        try:
            run = await RunRepository(db).get("run-orphan")
            assert run["agent_name"] == ""
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_every_run_survives(self, seeded):
        db = await _migrate(seeded)
        try:
            rows = await db.conn.execute_fetchall("SELECT id FROM runs ORDER BY id")
            assert [r["id"] for r in rows] == ["run-orphan", "run-owned", "run-project"]
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_a_runs_own_columns_are_carried_across(self, seeded):
        db = await _migrate(seeded)
        try:
            row = (await db.conn.execute_fetchall(
                "SELECT * FROM runs WHERE id = 'run-owned'"
            ))[0]
            assert row["status"] == "completed"
            assert json.loads(row["inputs"]) == {"topic": "AI"}
            assert row["provider"] == "claude_code"
            assert row["model"] == "claude-opus-5"
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_the_owner_columns_are_gone(self, seeded):
        db = await _migrate(seeded)
        try:
            cols = {r["name"] for r in await db.conn.execute_fetchall("PRAGMA table_info(runs)")}
            assert "title" in cols
            assert "agent_id" not in cols
            assert "project_id" not in cols
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_no_dangling_foreign_keys(self, seeded):
        db = await _migrate(seeded)
        try:
            assert await db.conn.execute_fetchall("PRAGMA foreign_key_check") == []
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_only_the_two_tables_and_one_index_remain(self, seeded):
        db = await _migrate(seeded)
        await db.disconnect()
        assert _names(seeded, "table") == ["devices", "runs"]
        assert _names(seeded, "index") == ["idx_devices_token_hash"]

    @pytest.mark.asyncio
    async def test_devices_are_untouched(self, seeded):
        db = await _migrate(seeded)
        try:
            rows = await db.conn.execute_fetchall("SELECT id FROM devices")
            assert [r["id"] for r in rows] == ["dev-1"]
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_the_backup_is_a_readable_database_with_the_old_tables(self, seeded):
        db = await _migrate(seeded)
        await db.disconnect()
        backup = seeded.with_name(seeded.name + BACKUP_SUFFIX)
        assert backup.exists()
        assert _names(backup, "table") == [
            "agent_runs", "agents", "devices", "project_edges",
            "project_nodes", "projects", "runs",
        ]
        conn = sqlite3.connect(backup)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_running_it_twice_changes_nothing(self, seeded):
        db = await _migrate(seeded)
        try:
            first = await db.conn.execute_fetchall("SELECT id, title FROM runs ORDER BY id")
            first_rows = [tuple(r) for r in first]
            await db.create_tables()
            second = await db.conn.execute_fetchall("SELECT id, title FROM runs ORDER BY id")
            assert [tuple(r) for r in second] == first_rows
        finally:
            await db.disconnect()
        assert _names(seeded, "table") == ["devices", "runs"]

    @pytest.mark.asyncio
    async def test_the_backup_is_replaced_rather_than_refused_on_a_rerun(self, seeded):
        """VACUUM INTO refuses an existing file, so the path is cleared first."""
        backup = seeded.with_name(seeded.name + BACKUP_SUFFIX)
        backup.write_text("stale")
        db = await _migrate(seeded)
        await db.disconnect()
        assert _names(backup, "table")


class TestFreshDatabase:

    @pytest.mark.asyncio
    async def test_a_fresh_database_skips_the_migration_entirely(self, tmp_path):
        path = tmp_path / "fresh.db"
        db = await _migrate(path)
        await db.disconnect()
        assert _names(path, "table") == ["devices", "runs"]
        assert not path.with_name(path.name + BACKUP_SUFFIX).exists()

    @pytest.mark.asyncio
    async def test_a_fresh_in_memory_database_is_the_new_schema(self):
        db = Database(":memory:")
        await db.connect()
        await db.create_tables()
        try:
            cols = {r["name"] for r in await db.conn.execute_fetchall("PRAGMA table_info(runs)")}
            assert "title" in cols
            assert "agent_id" not in cols
        finally:
            await db.disconnect()


class TestOldestDatabases:

    @pytest.mark.asyncio
    async def test_a_database_predating_provider_model_and_log_path_migrates(self, tmp_path):
        path = tmp_path / "ancient.db"
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA_PRE_COLUMNS)
        now = "2026-01-01T00:00:00"
        conn.execute(
            "INSERT INTO agents (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("agent-1", "Older", now, now),
        )
        conn.execute(
            "INSERT INTO runs (id, agent_id, status) VALUES (?, ?, ?)",
            ("run-1", "agent-1", "completed"),
        )
        conn.commit()
        conn.close()

        db = await _migrate(path)
        try:
            row = (await db.conn.execute_fetchall("SELECT * FROM runs WHERE id = 'run-1'"))[0]
            assert row["title"] == "Older"
            assert row["provider"] is None
            assert row["log_path"] is None
        finally:
            await db.disconnect()


class TestAFailedMigrationStopsTheDaemon:

    @pytest.mark.asyncio
    async def test_dangling_foreign_keys_raise_out_of_create_tables(self, seeded, monkeypatch):
        """Asserted through `create_tables`, because that is what the lifespan
        calls: a raise here is a daemon that refuses to start."""
        import api.persistence.database as database_mod

        broken = database_mod._REBUILD.replace(
            "DROP TABLE IF EXISTS agent_runs;", "",
        )
        monkeypatch.setattr(database_mod, "_REBUILD", broken)

        db = Database(str(seeded))
        await db.connect()
        try:
            with pytest.raises(RuntimeError, match="dangling foreign keys"):
                await db.create_tables()
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_the_failure_names_the_backup_to_restore_from(self, seeded, monkeypatch):
        import api.persistence.database as database_mod

        monkeypatch.setattr(
            database_mod, "_REBUILD",
            database_mod._REBUILD.replace("DROP TABLE IF EXISTS agent_runs;", ""),
        )
        db = Database(str(seeded))
        await db.connect()
        try:
            with pytest.raises(RuntimeError) as excinfo:
                await db.create_tables()
            assert BACKUP_SUFFIX in str(excinfo.value)
        finally:
            await db.disconnect()
