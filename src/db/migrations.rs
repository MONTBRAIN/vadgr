use rusqlite::{Connection, Error};

const CURRENT_VERSION: i64 = 1;

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
    tx.execute_batch(MIGRATION_ONE)?;
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
