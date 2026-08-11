//! The device repository: row shape, ordering, and the timestamps both
//! daemons must be able to read from one table.

use vadgr_daemon::db::{devices, now_iso, Db};

#[test]
fn create_returns_the_row_the_table_now_holds() {
    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    assert_eq!(row["machine_name"], "my-phone");
    assert!(row["id"].as_str().is_some());
    assert!(row["paired_at"].as_str().is_some());
    assert!(row.get("token_hash").is_none(), "the hash never reaches a published row");
}

#[test]
fn the_list_is_newest_pairing_first() {
    // The order the Python repository publishes and the phone's device list
    // draws: `paired_at` descending.
    let db = Db::open(":memory:").unwrap();
    db.with(|c| {
        c.execute_batch(
            "INSERT INTO devices (id, machine_name, token_hash, paired_at) VALUES
               ('d-old', 'old-phone', 'h1', '2026-08-01T10:00:00.000000+00:00'),
               ('d-new', 'new-phone', 'h2', '2026-08-09T10:00:00.000000+00:00');",
        )
    })
    .unwrap();
    let rows = devices::list_all(&db).unwrap();
    assert_eq!(rows[0]["id"], "d-new");
    assert_eq!(rows[1]["id"], "d-old");
}

#[test]
fn timestamps_are_written_in_the_shape_the_python_daemon_writes() {
    // Both daemons read one set of rows during the migration; a column
    // holding two timestamp shapes is a parser bug waiting in whichever
    // client reads it next. Python writes `datetime.now(timezone.utc)
    // .isoformat()`: a `T` separator, microseconds, `+00:00`.
    let stamp = now_iso();
    assert_eq!(stamp.len(), "2026-08-11T00:00:00.000000+00:00".len(), "{stamp}");
    assert_eq!(stamp.as_bytes()[10], b'T');
    assert!(stamp.ends_with("+00:00"));
    assert_eq!(stamp.as_bytes()[19], b'.');

    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    let paired_at = row["paired_at"].as_str().unwrap();
    assert!(paired_at.ends_with("+00:00"), "stored shape: {paired_at}");
    assert!(paired_at.contains('T'));
}

#[test]
fn touching_last_seen_moves_it() {
    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    let id = row["id"].as_str().unwrap();
    db.with(|c| c.execute("UPDATE devices SET last_seen = NULL WHERE id = ?1", [id]))
        .unwrap();
    devices::touch_last_seen(&db, id).unwrap();
    let row = devices::get(&db, id).unwrap().unwrap();
    assert!(row["last_seen"].as_str().is_some());
}

#[test]
fn deleting_says_whether_anything_was_there() {
    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    let id = row["id"].as_str().unwrap().to_string();
    assert!(devices::delete(&db, &id).unwrap());
    assert!(!devices::delete(&db, &id).unwrap(), "the second delete found nothing");
}
