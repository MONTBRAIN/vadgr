//! The run repository, and the wire mapping the phone reads.

use super::Db;
use serde_json::{json, Value};

/// One row, shaped for the wire.
///
/// **`agent_name` is the wire key and it carries `runs.title`.** The `0.4.4`
/// deletion removed the agents table and backfilled the title from it
/// (`api/persistence/repositories.py:36`), and the key was deliberately not
/// renamed: the shipped phone reads `agent_name`, and renaming it in the
/// release that deleted its source would have broken the app twice over. It
/// becomes the run's own noun at `0.6.0`, with the conversation.
fn row_to_json(row: &rusqlite::Row) -> rusqlite::Result<Value> {
    let inputs: Option<String> = row.get("inputs")?;
    let outputs: Option<String> = row.get("outputs")?;
    let parse = |s: Option<String>| -> Value {
        s.and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_else(|| json!({}))
    };
    let title: String = row.get("title")?;
    Ok(json!({
        "id": row.get::<_, String>("id")?,
        "agent_name": title,
        "status": row.get::<_, String>("status")?,
        "inputs": parse(inputs),
        "outputs": parse(outputs),
        "provider": row.get::<_, Option<String>>("provider")?,
        "model": row.get::<_, Option<String>>("model")?,
        "log_path": row.get::<_, Option<String>>("log_path")?,
        "started_at": row.get::<_, Option<String>>("started_at")?,
        "completed_at": row.get::<_, Option<String>>("completed_at")?,
    }))
}

const COLS: &str = "id, title, status, inputs, outputs, provider, model, log_path, started_at, completed_at";

pub fn list_all(db: &Db, status: Option<&str>) -> rusqlite::Result<Vec<Value>> {
    db.with(|c| {
        // Ordered by `started_at` descending with nulls last, which is what the
        // Python repository does: a queued run has no `started_at` and belongs
        // nearest the composer rather than at the top of the list.
        let sql = match status {
            Some(_) => format!(
                "SELECT {COLS} FROM runs WHERE status = ?1 ORDER BY started_at IS NULL, started_at DESC"
            ),
            None => format!(
                "SELECT {COLS} FROM runs ORDER BY started_at IS NULL, started_at DESC"
            ),
        };
        let mut stmt = c.prepare(&sql)?;
        let mapped = |r: &rusqlite::Row| row_to_json(r);
        let rows = match status {
            Some(s) => stmt.query_map([s], mapped)?.collect::<rusqlite::Result<Vec<_>>>()?,
            None => stmt.query_map([], mapped)?.collect::<rusqlite::Result<Vec<_>>>()?,
        };
        Ok(rows)
    })
}

pub fn get(db: &Db, run_id: &str) -> rusqlite::Result<Option<Value>> {
    db.with(|c| {
        let mut stmt = c.prepare(&format!("SELECT {COLS} FROM runs WHERE id = ?1"))?;
        let mut rows = stmt.query_map([run_id], |r| row_to_json(r))?;
        match rows.next() {
            Some(v) => Ok(Some(v?)),
            None => Ok(None),
        }
    })
}

/// The status column is free `TEXT`, and this does not promote it to an enum.
///
/// Both daemons run against copies of the same database during the migration,
/// so a row carrying a value this build does not know must round-trip rather
/// than fail. Validation belongs to the writer, and this release has no writer
/// but cancel.
pub fn update_status(db: &Db, run_id: &str, status: &str) -> rusqlite::Result<Option<Value>> {
    db.with(|c| {
        let completed = matches!(status, "completed" | "failed");
        if completed {
            c.execute(
                "UPDATE runs SET status = ?1, completed_at = datetime('now') WHERE id = ?2",
                rusqlite::params![status, run_id],
            )?;
        } else {
            c.execute(
                "UPDATE runs SET status = ?1 WHERE id = ?2",
                rusqlite::params![status, run_id],
            )?;
        }
        Ok(())
    })?;
    get(db, run_id)
}
