//! The device repository: row shape, ordering, and the timestamps both
//! daemons must be able to read from one table.

use vadgr_daemon::db::{Db, devices, now_iso};

#[test]
fn create_returns_the_row_the_table_now_holds() {
    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    assert_eq!(row["machine_name"], "my-phone");
    assert!(row["id"].as_str().is_some());
    assert!(row["paired_at"].as_str().is_some());
    assert!(
        row.get("token_hash").is_none(),
        "the hash never reaches a published row"
    );
}

#[test]
fn the_list_is_newest_pairing_first() {
    // The order the repository publishes and the phone's device list
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
fn timestamps_are_written_in_the_shape_the_phone_parses() {
    // Both daemons read one set of rows during the migration; a column
    // holding two timestamp shapes is a parser bug waiting in whichever
    // client reads it next. The shipped shape is `datetime.now(timezone.utc)
    // .isoformat()`: a `T` separator, microseconds, `+00:00`.
    let stamp = now_iso();
    assert_eq!(
        stamp.len(),
        "2026-08-11T00:00:00.000000+00:00".len(),
        "{stamp}"
    );
    assert_eq!(stamp.as_bytes()[10], b'T');
    assert!(stamp.ends_with("+00:00"));
    assert_eq!(stamp.as_bytes()[19], b'.');

    let db = Db::open(":memory:").unwrap();
    let row = devices::create(&db, "my-phone", "hash-1").unwrap();
    let paired_at = row["paired_at"].as_str().unwrap();
    assert!(paired_at.ends_with('Z'), "published shape: {paired_at}");
    assert!(paired_at.contains('T'));

    let stored: String = db
        .with(|c| c.query_row("SELECT paired_at FROM devices LIMIT 1", [], |r| r.get(0)))
        .unwrap();
    assert!(stored.ends_with("+00:00"), "stored shape: {stored}");
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
    assert!(
        !devices::delete(&db, &id).unwrap(),
        "the second delete found nothing"
    );
}

// ------------------------------------------------------------- device peers

/// One transport may not hold an identity twice, and the newest claim owns
/// it: one phone pairing twice presents the same proven identity both times.
#[test]
fn the_newest_claim_takes_the_binding_rather_than_failing_on_the_key() {
    let db = Db::open(":memory:").unwrap();
    let first = devices::create(&db, "phone", "h1").unwrap();
    let second = devices::create(&db, "phone again", "h2").unwrap();
    let first_id = first["id"].as_str().unwrap();
    let second_id = second["id"].as_str().unwrap();

    devices::bind_peer(&db, first_id, "iroh", "endpoint-a").unwrap();
    devices::bind_peer(&db, second_id, "iroh", "endpoint-a").unwrap();

    assert_eq!(
        devices::peer_device(&db, "iroh", "endpoint-a").unwrap(),
        Some(second_id.to_string())
    );
}

/// Two transports may hold the same identity string: the primary key is per
/// transport, so a fourth transport's ids cannot collide with this one's.
#[test]
fn the_same_identity_may_be_bound_on_two_transports() {
    let db = Db::open(":memory:").unwrap();
    let device = devices::create(&db, "phone", "h1").unwrap();
    let id = device["id"].as_str().unwrap();
    devices::bind_peer(&db, id, "iroh", "same-string").unwrap();
    devices::bind_peer(&db, id, "future-transport", "same-string").unwrap();
    assert_eq!(
        devices::peer_device(&db, "iroh", "same-string").unwrap(),
        Some(id.to_string())
    );
    assert_eq!(
        devices::peer_device(&db, "future-transport", "same-string").unwrap(),
        Some(id.to_string())
    );
}

/// Revocation cuts the network path with the token: deleting the device
/// drops its peer rows through the foreign key.
#[test]
fn deleting_a_device_drops_its_bindings() {
    let db = Db::open(":memory:").unwrap();
    let device = devices::create(&db, "phone", "h1").unwrap();
    let id = device["id"].as_str().unwrap();
    devices::bind_peer(&db, id, "iroh", "endpoint-a").unwrap();
    assert!(devices::any_peer_bound(&db, "iroh").unwrap());

    assert!(devices::delete(&db, id).unwrap());

    assert_eq!(
        devices::peer_device(&db, "iroh", "endpoint-a").unwrap(),
        None
    );
    assert!(!devices::any_peer_bound(&db, "iroh").unwrap());
}
