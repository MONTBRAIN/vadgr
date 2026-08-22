use rusqlite::Connection;
use vadgr_daemon::db::{Db, SCHEMA, runs};

#[test]
fn an_existing_0_4_6_database_keeps_its_runs_through_provider_migration() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("vadgr.db");
    let connection = Connection::open(&path).unwrap();
    connection.execute_batch(SCHEMA).unwrap();
    connection
        .execute(
            "INSERT INTO runs (id, title, status, provider, model)
             VALUES ('run-old', 'historical work', 'completed', 'anthropic_oauth', 'claude-old')",
            [],
        )
        .unwrap();
    drop(connection);

    let db = Db::open(&path).unwrap();

    let run = runs::get(&db, "run-old").unwrap().unwrap();
    assert_eq!(run["agent_name"], "historical work");
    assert_eq!(run["provider"], "anthropic_oauth");
    assert_eq!(run["model"], "claude-old");
    assert_eq!(
        db.with(|connection| connection.query_row(
            "SELECT count(*) FROM machine_settings",
            [],
            |row| row.get::<_, i64>(0),
        ))
        .unwrap(),
        1
    );
}

// ---------------------------------------------------------------- the ladder

/// Fresh and upgraded databases end at the same schema, `device_peers` and
/// its primary key included, because a fresh database runs the ladder too.
#[test]
fn a_version_one_database_and_a_fresh_one_end_with_the_same_schema() {
    let directory = tempfile::tempdir().unwrap();

    // A version-one database: the 0.4.9 shape, base schema plus migration
    // one, stamped user_version 1.
    let upgraded_path = directory.path().join("v1.db");
    {
        let connection = Connection::open(&upgraded_path).unwrap();
        connection.execute_batch(SCHEMA).unwrap();
        connection
            .execute_batch(
                "CREATE TABLE provider_connections (provider_id TEXT PRIMARY KEY,
                     auth_method TEXT NOT NULL, secret_ref TEXT NOT NULL UNIQUE,
                     account_id TEXT, credential_expires_at TEXT, updated_at TEXT NOT NULL);
                 CREATE TABLE provider_catalogs (provider_id TEXT PRIMARY KEY,
                     verified_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                     FOREIGN KEY (provider_id) REFERENCES provider_connections(provider_id)
                     ON DELETE CASCADE);
                 CREATE TABLE provider_models (provider_id TEXT NOT NULL, model_id TEXT NOT NULL,
                     name TEXT NOT NULL, capabilities TEXT NOT NULL,
                     PRIMARY KEY (provider_id, model_id),
                     FOREIGN KEY (provider_id) REFERENCES provider_catalogs(provider_id)
                     ON DELETE CASCADE);
                 CREATE TABLE machine_settings (id INTEGER PRIMARY KEY CHECK (id = 1),
                     default_provider TEXT, default_model TEXT,
                     CHECK ((default_provider IS NULL) = (default_model IS NULL)),
                     FOREIGN KEY (default_provider, default_model)
                     REFERENCES provider_models(provider_id, model_id)
                     ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED);
                 INSERT INTO machine_settings (id, default_provider, default_model)
                 VALUES (1, NULL, NULL);
                 PRAGMA user_version = 1;",
            )
            .unwrap();
    }

    let upgraded = Db::open(&upgraded_path).unwrap();
    let fresh = Db::open(directory.path().join("fresh.db")).unwrap();

    let tables = |db: &Db| {
        db.with(|c| {
            let mut stmt = c.prepare(
                "SELECT name FROM sqlite_master WHERE type IN ('table','index')
                 AND name NOT LIKE 'sqlite_%' ORDER BY name",
            )?;
            stmt.query_map([], |r| r.get::<_, String>(0))?.collect()
        })
        .unwrap()
    };
    let upgraded_tables: Vec<String> = tables(&upgraded);
    assert_eq!(upgraded_tables, tables(&fresh));
    assert!(upgraded_tables.contains(&"device_peers".to_string()));

    // A version-one database was not re-run through migration one: had it
    // been, the CREATE TABLE would have failed and nothing would open. The
    // seeded settings row proves the old rung's data survived.
    let settings: i64 = upgraded
        .with(|c| c.query_row("SELECT count(*) FROM machine_settings", [], |r| r.get(0)))
        .unwrap();
    assert_eq!(settings, 1);

    // The versions ended equal, and a second open is a no-op.
    for db in [&upgraded, &fresh] {
        let version: i64 = db
            .with(|c| c.query_row("PRAGMA user_version", [], |r| r.get(0)))
            .unwrap();
        assert_eq!(version, 2);
    }
    drop(upgraded);
    let reopened = Db::open(&upgraded_path).unwrap();
    let version: i64 = reopened
        .with(|c| c.query_row("PRAGMA user_version", [], |r| r.get(0)))
        .unwrap();
    assert_eq!(version, 2);
}
