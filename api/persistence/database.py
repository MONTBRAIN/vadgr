"""SQLite connection and schema management."""

import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    provider TEXT DEFAULT NULL,
    model TEXT DEFAULT NULL,
    log_path TEXT DEFAULT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    machine_name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    paired_at TEXT NOT NULL,
    last_seen TEXT
);

CREATE INDEX IF NOT EXISTS idx_devices_token_hash ON devices(token_hash);
"""


# The rebuild that takes the owner columns off `runs` and drops the five tables
# the workflow layer owned. Written as SQLite's documented table rebuild rather
# than `ALTER TABLE ... DROP COLUMN`, which only exists from SQLite 3.35 (2021).
# This daemon runs on four platforms against whatever SQLite each one's Python
# bundles, and the rebuild works on every version through one code path.
_REBUILD = """
PRAGMA foreign_keys=OFF;
BEGIN;
-- 1. give every run its title while the agents table still exists
ALTER TABLE runs ADD COLUMN title TEXT NOT NULL DEFAULT '';
UPDATE runs SET title =
    COALESCE((SELECT a.name FROM agents a WHERE a.id = runs.agent_id), '');

-- 2. the children go first, so nothing references a table being rebuilt
DROP TABLE IF EXISTS agent_runs;
DROP TABLE IF EXISTS project_edges;
DROP TABLE IF EXISTS project_nodes;

-- 3. rebuild runs without the two owner columns and their REFERENCES clauses
CREATE TABLE runs_new (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    inputs TEXT DEFAULT '{}',
    outputs TEXT DEFAULT '{}',
    provider TEXT DEFAULT NULL,
    model TEXT DEFAULT NULL,
    log_path TEXT DEFAULT NULL,
    started_at TEXT,
    completed_at TEXT
);
INSERT INTO runs_new
    (id, title, status, inputs, outputs, provider, model, log_path,
     started_at, completed_at)
SELECT id, title, status, inputs, outputs, provider, model, log_path,
       started_at, completed_at
FROM runs;
DROP TABLE runs;
ALTER TABLE runs_new RENAME TO runs;

-- 4. the parents, now that nothing references them
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS agents;
COMMIT;
PRAGMA foreign_keys=ON;
"""

BACKUP_SUFFIX = ".pre-0.4.4"


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
        # Migrations for existing databases.
        #
        # Ugly and load-bearing: they exist for databases predating these three
        # columns, and the rebuild below SELECTs all three by name. Tidying them
        # away would make the rebuild fail on exactly the oldest databases it
        # most needs to handle, so they run first and stay.
        try:
            await self._conn.execute("ALTER TABLE runs ADD COLUMN log_path TEXT DEFAULT NULL")
            await self._conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self._conn.execute("ALTER TABLE runs ADD COLUMN provider TEXT DEFAULT NULL")
            await self._conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            await self._conn.execute("ALTER TABLE runs ADD COLUMN model TEXT DEFAULT NULL")
            await self._conn.commit()
        except Exception:
            pass  # Column already exists
        await self._drop_workflow_tables()

    async def _drop_workflow_tables(self):
        """Take the owner columns off `runs` and drop the workflow tables.

        Guarded on the columns themselves, so it is idempotent and a database
        created from the current SCHEMA never enters it.

        Unlike the ALTERs above this does not swallow failures. It runs inside
        the lifespan, so raising here means the daemon refuses to start and
        names the backup to restore from. The alternative is a daemon serving a
        half-migrated database over the routes the phone reads, which is the one
        outcome worth being down for.
        """
        cols = {r[1] for r in await self.conn.execute_fetchall("PRAGMA table_info(runs)")}
        if "agent_id" not in cols and "project_id" not in cols:
            return

        # Said out loud, because it drops five tables and rewrites a column.
        # A migration that runs in silence leaves nothing in the log to read
        # afterwards, and the only sign it happened at all is a file appearing
        # on disk beside the database.
        logger.info(
            "migrating %s: dropping the workflow tables and rebuilding runs",
            self.path,
        )

        backup = None
        if self.path != ":memory:":
            backup = self.path + BACKUP_SUFFIX
            # VACUUM INTO refuses an existing file, and Windows will not let one
            # be replaced while a handle is open, so the path is cleared first.
            if os.path.exists(backup):
                os.remove(backup)
            # VACUUM INTO rather than a file copy: the database runs in WAL mode
            # and a copy that misses the -wal and -shm sidecars is a backup of a
            # stale page cache. This writes one consistent file. It cannot run
            # inside a transaction, hence the commit.
            await self.conn.commit()
            await self.conn.execute("VACUUM INTO ?", (backup,))

        # executescript commits pending work first and then runs the script
        # verbatim, so the PRAGMA statements land outside the transaction where
        # they take effect.
        await self.conn.executescript(_REBUILD)

        bad = await self.conn.execute_fetchall("PRAGMA foreign_key_check")
        if bad:
            raise RuntimeError(
                "database migration left dangling foreign keys: "
                f"{[tuple(row) for row in bad]}. The database before the "
                f"migration is at {backup or '(in-memory, not backed up)'}; "
                "restore it over the live file and report this."
            )

        # After the check, never before it: a success line printed ahead of the
        # thing that decides whether it succeeded is the log lying.
        logger.info(
            "migration complete: %s now holds runs and devices%s",
            self.path,
            f"; the database before it is at {backup}" if backup else "",
        )

    async def disconnect(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn
