//! The device repository: paired phones, and the hash their token matches.

use super::Db;
use serde_json::{json, Value};

pub fn list_all(db: &Db) -> rusqlite::Result<Vec<Value>> {
    db.with(|c| {
        let mut stmt = c.prepare(
            "SELECT id, machine_name, paired_at, last_seen FROM devices ORDER BY paired_at",
        )?;
        let rows = stmt
            .query_map([], |r| {
                Ok(json!({
                    "id": r.get::<_, String>("id")?,
                    "machine_name": r.get::<_, String>("machine_name")?,
                    "paired_at": r.get::<_, String>("paired_at")?,
                    "last_seen": r.get::<_, Option<String>>("last_seen")?,
                }))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(rows)
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
            "UPDATE devices SET last_seen = datetime('now') WHERE id = ?1",
            [device_id],
        )?;
        Ok(())
    })
}

pub fn create(db: &Db, machine_name: &str, token_hash: &str) -> rusqlite::Result<Value> {
    let id = uuid::Uuid::new_v4().to_string();
    db.with(|c| {
        c.execute(
            "INSERT INTO devices (id, machine_name, token_hash, paired_at, last_seen)
             VALUES (?1, ?2, ?3, datetime('now'), datetime('now'))",
            rusqlite::params![id, machine_name, token_hash],
        )?;
        Ok(())
    })?;
    Ok(json!({ "id": id, "machine_name": machine_name }))
}

pub fn delete(db: &Db, device_id: &str) -> rusqlite::Result<bool> {
    db.with(|c| {
        let n = c.execute("DELETE FROM devices WHERE id = ?1", [device_id])?;
        Ok(n > 0)
    })
}
