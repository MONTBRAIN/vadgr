//! The device repository: paired phones, and the hash their token matches.
//!
//! The single owner of the `devices` table, and token hashes only: the
//! plaintext token is never stored and never compared against anything stored.

use super::{Db, now_iso};
use serde_json::{Value, json};

/// One row, in the shape `GET /api/devices` publishes. The `token_hash`
/// column never enters it.
fn row_to_json(r: &rusqlite::Row) -> rusqlite::Result<Value> {
    let wire_timestamp = |value: Option<String>| {
        value.map(|stamp| {
            stamp
                .strip_suffix("+00:00")
                .map_or(stamp.clone(), |s| format!("{s}Z"))
        })
    };
    Ok(json!({
        "id": r.get::<_, String>("id")?,
        "machine_name": r.get::<_, String>("machine_name")?,
        "paired_at": wire_timestamp(Some(r.get::<_, String>("paired_at")?)),
        "last_seen": wire_timestamp(r.get::<_, Option<String>>("last_seen")?),
    }))
}

const COLS: &str = "id, machine_name, paired_at, last_seen";

pub fn list_all(db: &Db) -> rusqlite::Result<Vec<Value>> {
    db.with(|c| {
        // Newest pairing first, which is the order the phone
        // publishes and the order the phone's device list draws.
        let mut stmt = c.prepare(&format!(
            "SELECT {COLS} FROM devices ORDER BY paired_at DESC"
        ))?;
        let rows = stmt
            .query_map([], row_to_json)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
    })
}

pub fn get(db: &Db, device_id: &str) -> rusqlite::Result<Option<Value>> {
    db.with(|c| {
        let mut stmt = c.prepare(&format!("SELECT {COLS} FROM devices WHERE id = ?1"))?;
        let mut rows = stmt.query_map([device_id], row_to_json)?;
        match rows.next() {
            Some(v) => Ok(Some(v?)),
            None => Ok(None),
        }
    })
}

/// Look a device up by the hash of the presented token.
///
/// The lookup is by hash, so the plaintext token is never compared against
/// anything stored and never has to be: `token_hash` is `UNIQUE` and indexed,
/// and a hash that matches nothing is `INVALID_TOKEN`.
pub fn find_by_token_hash(db: &Db, token_hash: &str) -> rusqlite::Result<Option<String>> {
    db.with(|c| {
        let mut stmt = c.prepare("SELECT id FROM devices WHERE token_hash = ?1")?;
        let mut rows = stmt.query_map([token_hash], |r| r.get::<_, String>("id"))?;
        match rows.next() {
            Some(v) => Ok(Some(v?)),
            None => Ok(None),
        }
    })
}

pub fn touch_last_seen(db: &Db, device_id: &str) -> rusqlite::Result<()> {
    db.with(|c| {
        c.execute(
            "UPDATE devices SET last_seen = ?1 WHERE id = ?2",
            rusqlite::params![now_iso(), device_id],
        )?;
        Ok(())
    })
}

pub fn create(db: &Db, machine_name: &str, token_hash: &str) -> rusqlite::Result<Value> {
    let id = uuid::Uuid::new_v4().to_string();
    let now = now_iso();
    db.with(|c| {
        c.execute(
            "INSERT INTO devices (id, machine_name, token_hash, paired_at, last_seen)
             VALUES (?1, ?2, ?3, ?4, ?4)",
            rusqlite::params![id, machine_name, token_hash, now],
        )?;
        Ok(())
    })?;
    // Read the row back rather than echoing the arguments, rather than the arguments, because a default or a trigger
    // repository: what the caller gets is what the table now says.
    Ok(get(db, &id)?.expect("the row just inserted exists"))
}

pub fn delete(db: &Db, device_id: &str) -> rusqlite::Result<bool> {
    db.with(|c| {
        let n = c.execute("DELETE FROM devices WHERE id = ?1", [device_id])?;
        Ok(n > 0)
    })
}

/// Bind a transport-proven peer identity to a device, in one transaction.
///
/// **The newest claim owns the identity**: any other row holding
/// `(transport, peer_id)` goes first, because one phone pairing twice
/// presents the same proven identity both times and must not fail on the
/// primary key. Taking someone else's binding requires their secret key,
/// which is what makes the take safe.
pub fn bind_peer(db: &Db, device_id: &str, transport: &str, peer_id: &str) -> rusqlite::Result<()> {
    db.with_mut(|c| {
        let tx = c.transaction()?;
        tx.execute(
            "DELETE FROM device_peers WHERE transport = ?1 AND peer_id = ?2",
            rusqlite::params![transport, peer_id],
        )?;
        tx.execute(
            "INSERT INTO device_peers (device_id, transport, peer_id) VALUES (?1, ?2, ?3)",
            rusqlite::params![device_id, transport, peer_id],
        )?;
        tx.commit()
    })
}

/// The device a peer identity is bound to on one transport, or `None`. Read
/// at connection accept, per stream and at gate 1, which is what makes
/// revocation cut the network path: the row goes with the device row.
pub fn peer_device(db: &Db, transport: &str, peer_id: &str) -> rusqlite::Result<Option<String>> {
    db.with(|c| {
        let mut stmt =
            c.prepare("SELECT device_id FROM device_peers WHERE transport = ?1 AND peer_id = ?2")?;
        let mut rows = stmt.query_map(rusqlite::params![transport, peer_id], |r| {
            r.get::<_, String>("device_id")
        })?;
        match rows.next() {
            Some(v) => Ok(Some(v?)),
            None => Ok(None),
        }
    })
}

/// Whether any device holds a binding on one transport. The built-in
/// transport's accept loop asks this to refuse, before any handshake, on a
/// machine that could admit nobody.
pub fn any_peer_bound(db: &Db, transport: &str) -> rusqlite::Result<bool> {
    db.with(|c| {
        let count: i64 = c.query_row(
            "SELECT count(*) FROM device_peers WHERE transport = ?1",
            [transport],
            |r| r.get(0),
        )?;
        Ok(count > 0)
    })
}
