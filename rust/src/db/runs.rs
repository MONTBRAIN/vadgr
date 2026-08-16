//! The run repository, and the wire mapping the phone reads.

use super::Db;
use serde_json::{Value, json};

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
        s.and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_else(|| json!({}))
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

const COLS: &str =
    "id, title, status, inputs, outputs, provider, model, log_path, started_at, completed_at";

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
        let mut rows = stmt.query_map([run_id], row_to_json)?;
        match rows.next() {
            Some(v) => Ok(Some(v?)),
            None => Ok(None),
        }
    })
}

pub fn create(
    db: &Db,
    task: &str,
    provider: Option<&str>,
    model: Option<&str>,
) -> rusqlite::Result<Value> {
    let id = format!("run-{}", uuid::Uuid::new_v4().simple());
    let inputs = json!({"task": task}).to_string();
    db.with(|connection| {
        connection.execute(
            "INSERT INTO runs (id, title, status, inputs, outputs, provider, model) VALUES (?1, ?2, 'queued', ?3, '{}', ?4, ?5)",
            rusqlite::params![id, task, inputs, provider, model],
        )?;
        Ok(())
    })?;
    get(db, &id)?.ok_or(rusqlite::Error::QueryReturnedNoRows)
}

pub fn set_config(
    db: &Db,
    run_id: &str,
    provider: &str,
    model: &str,
) -> rusqlite::Result<Option<Value>> {
    db.with(|connection| {
        connection.execute(
            "UPDATE runs SET provider = ?1, model = ?2 WHERE id = ?3",
            rusqlite::params![provider, model, run_id],
        )?;
        Ok(())
    })?;
    get(db, run_id)
}

pub fn active(db: &Db) -> rusqlite::Result<Vec<Value>> {
    db.with(|connection| {
        let mut statement = connection.prepare(&format!(
            "SELECT {COLS} FROM runs WHERE status IN ('queued', 'running', 'awaiting_approval') ORDER BY started_at IS NULL, started_at"
        ))?;
        statement
            .query_map([], row_to_json)?
            .collect::<rusqlite::Result<Vec<_>>>()
    })
}

pub fn finish_if_active(
    db: &Db,
    run_id: &str,
    status: &str,
    outputs: &Value,
) -> rusqlite::Result<Option<Value>> {
    let now = super::now_iso();
    let changed = db.with(|connection| {
        connection.execute(
            "UPDATE runs SET status = ?1, outputs = ?2, completed_at = ?3 WHERE id = ?4 AND status IN ('queued', 'running', 'awaiting_approval')",
            rusqlite::params![status, outputs.to_string(), now, run_id],
        )
    })?;
    if changed == 0 {
        Ok(None)
    } else {
        get(db, run_id)
    }
}

/// The status column is free `TEXT`, and this does not promote it to an enum.
///
/// Both daemons run against copies of the same database during the migration,
/// so a row carrying a value this build does not know must round-trip rather
/// than fail. Validation belongs to the writer, and this release has no writer
/// but cancel.
pub fn update_status(db: &Db, run_id: &str, status: &str) -> rusqlite::Result<Option<Value>> {
    let now = super::now_iso();
    db.with(|c| {
        match status {
            // COALESCE so a resume never rewrites when the run first started:
            // the Python repository stamps `started_at` exactly once.
            "running" => c.execute(
                "UPDATE runs SET status = ?1, started_at = COALESCE(started_at, ?2) WHERE id = ?3",
                rusqlite::params![status, now, run_id],
            )?,
            "completed" | "failed" | "cancelled" => c.execute(
                "UPDATE runs SET status = ?1, completed_at = ?2 WHERE id = ?3",
                rusqlite::params![status, now, run_id],
            )?,
            _ => c.execute(
                "UPDATE runs SET status = ?1 WHERE id = ?2",
                rusqlite::params![status, run_id],
            )?,
        };
        Ok(())
    })?;
    get(db, run_id)
}
