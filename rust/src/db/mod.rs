//! The SQLite layer. **The schema is copied, not designed.**
//!
//! Two tables and one index is the whole schema after the `0.4.4` deletion.
//! It is applied verbatim from `api/persistence/database.py:12`: an improvement
//! here would make every evidence comparison in the migration meaningless,
//! which is the constraint rather than a preference.

pub mod devices;
pub mod runs;

use anyhow::Result;
use rusqlite::Connection;
use std::sync::{Arc, Mutex};

/// Verbatim from `api/persistence/database.py:12`. Do not tidy.
pub const SCHEMA: &str = r#"
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
"#;

/// One connection behind a mutex rather than a pool.
///
/// The daemon is one process serving one owner's phone and one CLI, and SQLite
/// serialises writes anyway. A pool would add a failure mode - a reader seeing
/// a half-applied write through a second connection - to buy concurrency this
/// workload does not have.
#[derive(Clone)]
pub struct Db(Arc<Mutex<Connection>>);

impl Db {
    pub fn open(path: &str) -> Result<Self> {
        let conn = if path == ":memory:" {
            Connection::open_in_memory()?
        } else {
            Connection::open(path)?
        };
        // The same two pragmas the Python daemon sets on connect. WAL is the
        // journal mode the migration's database copies assume (`VACUUM INTO`,
        // never `cp`), so the Rust daemon must not quietly write a different
        // one into a shared file.
        conn.execute_batch("PRAGMA foreign_keys = ON")?;
        let _mode: String = conn.query_row("PRAGMA journal_mode = WAL", [], |r| r.get(0))?;
        conn.execute_batch(SCHEMA)?;
        Ok(Self(Arc::new(Mutex::new(conn))))
    }

    pub fn with<T>(
        &self,
        f: impl FnOnce(&Connection) -> rusqlite::Result<T>,
    ) -> rusqlite::Result<T> {
        let guard = self.0.lock().expect("db mutex poisoned");
        f(&guard)
    }
}

/// The one clock the repositories write with, shaped like the Python
/// daemon's: UTC, microseconds, `+00:00`. Both daemons read one set of rows
/// during the migration, and a column holding two timestamp shapes is a
/// parser bug waiting in whichever client reads it next.
pub fn now_iso() -> String {
    let format = time::macros::format_description!(
        "[year]-[month]-[day]T[hour]:[minute]:[second].[subsecond digits:6]+00:00"
    );
    time::OffsetDateTime::now_utc()
        .format(&format)
        .expect("a fixed format cannot fail on a real instant")
}
