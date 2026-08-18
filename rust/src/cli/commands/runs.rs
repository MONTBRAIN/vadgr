//! `vadgr runs`: list, get, cancel, resume.
//!
//! Ported from `cli/commands/runs.py`. Two behaviours here are easy to lose in a
//! port and both are what a person actually uses: **a run id may be a prefix**,
//! and a failed run's row carries the error and the command that resumes it.
//!
//! The run-status to exit-code mapping lives in `stream::Outcome`, which is the
//! only place a watch ends. A second copy here would be the duplicated source of
//! truth the migration standard warns about.

use crate::client::Client;
use crate::error::CliError;
use crate::output;

fn truncate(text: &str, width: usize) -> String {
    // Count characters, not bytes. A task sentence carries accented text and
    // emoji, and slicing by byte splits them into replacement characters.
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= width {
        return text.to_owned();
    }
    let cut: String = chars[..width.saturating_sub(1)].iter().collect();
    format!("{cut}\u{2026}")
}

/// A duration as the two listings print it: whole seconds in the table, one
/// decimal in the detail, and a dash when the daemon sent none.
fn duration_text(value: Option<&serde_json::Value>, decimals: usize) -> String {
    match value.and_then(|v| v.as_f64()) {
        Some(seconds) => format!("{seconds:.decimals$}s"),
        None => value.and_then(|v| v.as_str()).unwrap_or("-").to_owned(),
    }
}

/// Turn a prefix into the full run id.
///
/// **Nobody types a whole run id.** `vadgr runs list` prints the first eight
/// characters and every other command accepts them, so dropping this would make
/// the listing's own output unusable as input.
pub async fn resolve_run_id(client: &Client, run_id: &str) -> Result<String, CliError> {
    if run_id.is_empty() {
        return Err(CliError::Failed("Run ID is required.".to_owned()));
    }
    let runs = client.get("/api/runs").await?;
    let empty = Vec::new();
    let runs = runs.as_array().unwrap_or(&empty);
    if runs.is_empty() {
        return Err(CliError::Failed("No runs found.".to_owned()));
    }
    runs.iter()
        .filter_map(|r| r.get("id").and_then(|v| v.as_str()))
        .find(|id| id.starts_with(run_id))
        .map(str::to_owned)
        .ok_or_else(|| CliError::Failed(format!("No run matching '{run_id}' found.")))
}

pub async fn list(client: &Client, status: Option<&str>) -> Result<(), CliError> {
    let path = match status {
        Some(s) => format!("/api/runs?status={s}"),
        None => "/api/runs".to_owned(),
    };
    let body = client.get(&path).await?;
    let empty = Vec::new();
    let runs = body.as_array().unwrap_or(&empty);
    if runs.is_empty() {
        anstream::println!("{}", output::warning("No runs found."));
        return Ok(());
    }

    let rows: Vec<Vec<String>> = runs
        .iter()
        .map(|r| {
            let id = r.get("id").and_then(|v| v.as_str()).unwrap_or("-");
            // `agent_name` is the run's title, which since `0.4.4` is the task
            // sentence it was started with.
            let task = r
                .get("agent_name")
                .and_then(|v| v.as_str())
                .filter(|t| !t.is_empty())
                .unwrap_or("-");
            let status = r.get("status").and_then(|v| v.as_str()).unwrap_or("?");
            vec![
                id.chars().take(8).collect(),
                truncate(task, 60),
                output::format_status(status),
                duration_text(r.get("duration"), 0),
            ]
        })
        .collect();
    anstream::println!(
        "{}",
        output::render_table(&["Run ID", "Task", "Status", "Duration"], &rows)
    );
    Ok(())
}

pub async fn get(client: &Client, run_id: &str) -> Result<(), CliError> {
    let run_id = resolve_run_id(client, run_id).await?;
    let body = client.get(&format!("/api/runs/{run_id}")).await?;
    if !body.is_object() {
        return Err(CliError::Failed(format!("Run '{run_id}' not found.")));
    }
    let field = |k: &str| {
        body.get(k)
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_owned()
    };
    let status = body
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_owned();

    anstream::println!(
        "{}",
        output::render_kv(&[
            ("Run ID".to_owned(), field("id")),
            (
                "Task".to_owned(),
                body.get("agent_name")
                    .and_then(|v| v.as_str())
                    .filter(|t| !t.is_empty())
                    .unwrap_or("-")
                    .to_owned()
            ),
            ("Status".to_owned(), output::format_status(&status)),
            ("Provider".to_owned(), field("provider")),
            ("Model".to_owned(), field("model")),
            (
                "Duration".to_owned(),
                duration_text(body.get("duration"), 1)
            ),
        ])
    );

    // A failed run is the one a person came to this command for, so it says what
    // went wrong and how to continue rather than leaving them to find out.
    if status == "failed" {
        if let Some(error) = body
            .get("outputs")
            .and_then(|o| o.get("error"))
            .and_then(|v| v.as_str())
        {
            anstream::println!("\nError: {error}");
        }
        let short: String = field("id").chars().take(8).collect();
        anstream::println!("\nResume with: vadgr runs resume {short}");
    }
    Ok(())
}

pub async fn cancel(client: &Client, run_id: &str) -> Result<(), CliError> {
    let run_id = resolve_run_id(client, run_id).await?;
    client
        .post(&format!("/api/runs/{run_id}/cancel"), None)
        .await?;
    anstream::println!("{}", output::success(&format!("Cancelled run {run_id}")));
    Ok(())
}

pub async fn resume(client: &Client, run_id: &str) -> Result<(), CliError> {
    let run_id = resolve_run_id(client, run_id).await?;
    let body = client
        .post(&format!("/api/runs/{run_id}/resume"), None)
        .await?;
    // "Already running" is not a success and not a failure: the daemon is
    // telling the owner the run needed nothing.
    match body.get("message").and_then(|v| v.as_str()) {
        Some(message) if message.contains("Already") => {
            anstream::println!("{}", output::warning(message));
        }
        _ => {
            anstream::println!("{}", output::success(&format!("Resuming run {run_id}")));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Truncation counts characters, because a task sentence is prose.
    #[test]
    fn truncation_does_not_split_a_character() {
        let task = "reinicia el servidor de producción con cuidado";
        let out = truncate(task, 20);
        assert_eq!(out.chars().count(), 20);
        assert!(out.ends_with('\u{2026}'));
        assert!(!out.contains('\u{fffd}'), "no replacement character");
    }

    #[test]
    fn truncation_leaves_a_short_task_alone() {
        assert_eq!(truncate("short", 20), "short");
    }

    #[test]
    fn emoji_survive_truncation_whole() {
        let out = truncate("deploy 🚀🚀🚀 to production now please", 10);
        assert_eq!(out.chars().count(), 10);
        assert!(!out.contains('\u{fffd}'));
    }

    /// The table rounds and the detail keeps a decimal, which is what the two
    /// shipped views print.
    #[test]
    fn a_duration_reads_the_way_each_view_prints_it() {
        let value = serde_json::json!(12.34);
        assert_eq!(duration_text(Some(&value), 0), "12s");
        assert_eq!(duration_text(Some(&value), 1), "12.3s");
        assert_eq!(duration_text(None, 1), "-");
    }
}
