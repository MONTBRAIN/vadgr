use rusqlite::{Connection, Error};

const CURRENT_VERSION: i64 = 3;

const MIGRATION_ONE: &str = r#"
CREATE TABLE provider_connections (
    provider_id TEXT PRIMARY KEY,
    auth_method TEXT NOT NULL,
    secret_ref TEXT NOT NULL UNIQUE,
    account_id TEXT,
    credential_expires_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE provider_catalogs (
    provider_id TEXT PRIMARY KEY,
    verified_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES provider_connections(provider_id)
        ON DELETE CASCADE
);

CREATE TABLE provider_models (
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    name TEXT NOT NULL,
    capabilities TEXT NOT NULL,
    PRIMARY KEY (provider_id, model_id),
    FOREIGN KEY (provider_id) REFERENCES provider_catalogs(provider_id)
        ON DELETE CASCADE
);

CREATE TABLE machine_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    default_provider TEXT,
    default_model TEXT,
    CHECK ((default_provider IS NULL) = (default_model IS NULL)),
    FOREIGN KEY (default_provider, default_model)
        REFERENCES provider_models(provider_id, model_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO machine_settings (id, default_provider, default_model)
VALUES (1, NULL, NULL);
"#;

/// The identity a transport proved at claim, bound to the device that
/// claimed. A table rather than a `devices` column named after one transport:
/// a fourth transport that proves identities binds a row here, and the
/// primary key gives per-transport uniqueness for free. No backfill: a device
/// with no row cannot pass the built-in transport's peer gate yet, which is
/// the honest state of every earlier pairing.
const MIGRATION_TWO: &str = r#"
CREATE TABLE device_peers (
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    transport TEXT NOT NULL,
    peer_id   TEXT NOT NULL,
    PRIMARY KEY (transport, peer_id)
);
CREATE INDEX idx_device_peers_device ON device_peers(device_id);
"#;

const MIGRATION_THREE: &str = r#"
ALTER TABLE machine_settings ADD COLUMN machine_id TEXT NOT NULL DEFAULT '';
ALTER TABLE machine_settings ADD COLUMN name TEXT NOT NULL DEFAULT '';
ALTER TABLE machine_settings ADD COLUMN role_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE machine_settings ADD COLUMN autonomy_mode TEXT NOT NULL DEFAULT 'default';
ALTER TABLE machine_settings ADD COLUMN workspace TEXT;
ALTER TABLE machine_settings ADD COLUMN granted_skills TEXT NOT NULL DEFAULT '[]';
ALTER TABLE machine_settings ADD COLUMN granted_mcp_servers TEXT NOT NULL DEFAULT '["control-plane","vadgr-computer-use"]';
"#;

/// The ladder, in order. `apply` runs every rung above the stored version,
/// so a version-one database takes rung two alone and is never re-run
/// through rung one.
const MIGRATIONS: [(i64, &str); 3] = [(1, MIGRATION_ONE), (2, MIGRATION_TWO), (3, MIGRATION_THREE)];

pub fn apply(conn: &Connection) -> rusqlite::Result<()> {
    let version: i64 = conn.query_row("PRAGMA user_version", [], |row| row.get(0))?;
    if version > CURRENT_VERSION {
        return Err(Error::InvalidParameterName(format!(
            "database schema version {version} is newer than supported version {CURRENT_VERSION}"
        )));
    }
    if version == CURRENT_VERSION {
        return Ok(());
    }

    let tx = conn.unchecked_transaction()?;
    for (rung, sql) in MIGRATIONS {
        if rung > version {
            tx.execute_batch(sql)?;
        }
    }
    tx.pragma_update(None, "user_version", CURRENT_VERSION)?;
    tx.commit()
}

#[cfg(test)]
mod tests {
    use super::{CURRENT_VERSION, apply};
    use rusqlite::Connection;

    #[test]
    fn migration_one_is_atomic_and_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch("PRAGMA foreign_keys = ON").unwrap();
        apply(&conn).unwrap();
        apply(&conn).unwrap();
        let version: i64 = conn
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .unwrap();
        assert_eq!(version, CURRENT_VERSION);
        let settings: i64 = conn
            .query_row("SELECT count(*) FROM machine_settings", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(settings, 1);
    }

    #[test]
    fn a_newer_database_is_refused() {
        let conn = Connection::open_in_memory().unwrap();
        conn.pragma_update(None, "user_version", 99).unwrap();
        assert!(apply(&conn).unwrap_err().to_string().contains("newer"));
    }

    #[test]
    fn a_failed_migration_rolls_back_every_statement_and_the_version() {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch("CREATE TABLE provider_connections (broken TEXT)")
            .unwrap();

        assert!(apply(&conn).is_err());

        let version: i64 = conn
            .query_row("PRAGMA user_version", [], |row| row.get(0))
            .unwrap();
        assert_eq!(version, 0);
        let catalogs: i64 = conn
            .query_row(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='provider_catalogs'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(catalogs, 0);
    }
}
