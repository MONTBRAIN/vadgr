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
