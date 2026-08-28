//! The SQLite connection and repository boundary.

pub mod devices;
pub mod migrations;
pub mod providers;
pub mod runs;

use anyhow::{Context, Result};
use rusqlite::Connection;
use std::path::Path;
use std::sync::{Arc, Mutex};

/// The legacy tables stay byte-for-byte compatible while forward migrations
/// add Rust-owned state beside them.
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
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        let conn = if path == Path::new(":memory:") {
            Connection::open_in_memory()?
        } else {
            if let Some(parent) = path
                .parent()
                .filter(|parent| !parent.as_os_str().is_empty())
            {
                std::fs::create_dir_all(parent)
                    .with_context(|| format!("creating database directory {}", parent.display()))?;
            }
            drop(crate::private_fs::touch(path)?);
            Connection::open(path)?
        };
        // The two pragmas every connection sets. WAL is the
        // journal mode the migration's database copies assume (`VACUUM INTO`,
        // never `cp`), so the Rust daemon must not quietly write a different
        // one into a shared file.
        conn.execute_batch("PRAGMA foreign_keys = ON")?;
        let _mode: String = conn.query_row("PRAGMA journal_mode = WAL", [], |r| r.get(0))?;
        conn.execute_batch(SCHEMA)?;
        migrations::apply(&conn)?;
        if path != Path::new(":memory:") {
            crate::private_fs::harden(path)?;
            crate::private_fs::harden(&path.with_extension("db-wal"))?;
            crate::private_fs::harden(&path.with_extension("db-shm"))?;
        }
        Ok(Self(Arc::new(Mutex::new(conn))))
    }

    pub fn with<T>(
        &self,
        f: impl FnOnce(&Connection) -> rusqlite::Result<T>,
    ) -> rusqlite::Result<T> {
        let guard = self.0.lock().expect("db mutex poisoned");
        f(&guard)
    }

    pub fn with_mut<T>(
        &self,
        f: impl FnOnce(&mut Connection) -> rusqlite::Result<T>,
    ) -> rusqlite::Result<T> {
        let mut guard = self.0.lock().expect("db mutex poisoned");
        f(&mut guard)
    }
}

/// The one clock the repositories write with, shaped like the timestamp every client already parses
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

#[cfg(all(test, unix))]
mod permission_tests {
    use super::Db;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn an_existing_database_is_hardened_for_the_owner() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("vadgr.db");
        std::fs::write(&path, []).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o666)).unwrap();

        let _db = Db::open(&path).unwrap();

        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        for sidecar in [path.with_extension("db-wal"), path.with_extension("db-shm")] {
            assert_eq!(
                std::fs::metadata(sidecar).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
    }
}
